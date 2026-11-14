import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch

from trackmania_rl import level_schedule, utilities


def make_config(names, focus="", target=0.0):
    return SimpleNamespace(
        levels=[(name, f"{name}.Gbx", f"{name}.npy") for name in names],
        focus_level=focus,
        focus_target_s=target,
        goal_times={name: 30.0 for name in names},
        steps_per_level=1000,
        steps_per_level_with_gold=500,
        max_steps_per_level=100_000,
        min_finishes_per_level=1,
        steps_without_improvement=10_000,
        steps_without_progress=5_000,
    )


def make_stats(index, best=None):
    return {
        "level_index": index,
        "alltime_min_ms": best or {},
        "cumul_number_frames_played": 0,
        "level_start_frames": 0,
    }


class FocusTests(unittest.TestCase):
    def test_target_already_beaten_does_not_focus(self):
        config = make_config(["A01", "D01", "D02"], "D01", 153.26)
        stats = make_stats(2, {"D01": 153240})
        self.assertIsNone(level_schedule.focus_index(stats, config))
        self.assertIsNone(level_schedule.next_level_index(stats, config))

    def test_focus_goes_back_to_the_level_by_name(self):
        config = make_config(["A01", "D01", "D02"], "D01", 140.0)
        stats = make_stats(2, {"D01": 153240})
        self.assertEqual(level_schedule.next_level_index(stats, config), 1)
        self.assertEqual(stats["return_level"], "D02")
        shorter = make_config(["A01", "D02"])
        stats["level_index"] = 0
        self.assertEqual(level_schedule.next_level_index(stats, shorter), 1)
        self.assertNotIn("return_level", stats)

    def test_old_return_index_still_works(self):
        config = make_config(["A01", "B01", "C01"])
        stats = make_stats(0)
        stats["return_index"] = 5
        self.assertEqual(level_schedule.next_level_index(stats, config), 2)


class StalledLevelTests(unittest.TestCase):
    def test_leaves_a_level_that_stopped_getting_further(self):
        config = make_config(["A01", "B01"])
        stats = make_stats(0)
        stats["level_furthest_frames"] = 1_000
        stats["cumul_number_frames_played"] = 5_999
        self.assertIsNone(level_schedule.next_level_index(stats, config))
        stats["cumul_number_frames_played"] = 6_000
        self.assertEqual(level_schedule.next_level_index(stats, config), 1)

    def test_counts_from_the_start_of_the_visit(self):
        config = make_config(["A01", "B01"])
        stats = make_stats(0)
        stats["cumul_number_frames_played"] = 5_000
        self.assertEqual(level_schedule.next_level_index(stats, config), 1)

    def test_a_level_that_is_finishing_stays(self):
        config = make_config(["A01", "B01"])
        stats = make_stats(0)
        stats["level_finishes"] = 3
        stats["cumul_number_frames_played"] = 9_000
        self.assertIsNone(level_schedule.next_level_index(stats, config))


class LevelBrainTests(unittest.TestCase):
    def setUp(self):
        self.online = torch.nn.Linear(2, 2)
        self.target = torch.nn.Linear(2, 2)
        self.optimizer = torch.optim.RAdam(self.online.parameters())
        self.scaler = torch.amp.GradScaler("cuda", enabled=False)

    def save(self, folder, level, brain_level):
        return utilities.save_level_brain(folder, level, brain_level, self.online, self.target, self.optimizer, self.scaler)

    def test_never_saves_another_levels_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "D01"
            folder.mkdir()
            (folder / "weights1.torch").write_bytes(b"real D01 brain")
            self.assertFalse(self.save(folder, "D01", "D02"))
            self.assertEqual((folder / "weights1.torch").read_bytes(), b"real D01 brain")
            self.assertFalse(self.save(folder, "D01", None))
            self.assertEqual((folder / "weights1.torch").read_bytes(), b"real D01 brain")

    def test_keeps_the_previous_brain(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "D01"
            folder.mkdir()
            (folder / "weights1.torch").write_bytes(b"older D01 brain")
            self.assertTrue(self.save(folder, "D01", "D01"))
            self.assertEqual((folder / "weights1.torch.bak").read_bytes(), b"older D01 brain")
            self.assertEqual(torch.load(folder / "weights1.torch", weights_only=False).keys(), self.online.state_dict().keys())


if __name__ == "__main__":
    unittest.main()
