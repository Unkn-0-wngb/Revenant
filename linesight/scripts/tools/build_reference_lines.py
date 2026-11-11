"""
Turns the replays in reference_replays/ into reference lines in maps/, and writes config_files/all_maps.py.
Levels whose replay jumps position are listed as skipped, because the line would have a break in it.
"""

import csv
import glob
import os
from pathlib import Path

import numpy as np
from pygbx import Gbx, GbxType

base_dir = Path(__file__).resolve().parents[2]
root = base_dir.parent
max_metres_per_sample = 40
shortcut_ratio = 0.8


def read_positions(path):
    ghosts = Gbx(path).get_classes_by_ids([GbxType.CTN_GHOST])
    ghost = min(ghosts, key=lambda g: g.race_time)
    keep = round(ghost.race_time / ghost.sample_period)
    positions = [np.array([r.position.x, r.position.y, r.position.z]) for r in ghost.records[:keep]]
    return ghost, positions


def resample(positions, spacing=0.5):
    a = np.array(positions, dtype=float)
    steps = np.linalg.norm(np.diff(a, axis=0), axis=1)
    moving = np.concatenate(([True], steps > 1e-6))
    a = a[moving]
    distance = np.concatenate(([0], np.cumsum(np.linalg.norm(np.diff(a, axis=0), axis=1))))
    marks = np.arange(0, distance[-1], spacing)
    line = np.column_stack([np.interp(marks, distance, a[:, i]) for i in range(3)])
    return np.vstack((line, 2 * a[-1] - line[-1])).round(4)


def main():
    rows = list(csv.DictReader(open(root / "official_records.csv", encoding="utf-8")))
    levels, skipped, shortcuts = [], [], []
    for row in rows:
        name = row["map"]
        short = name[:3]
        record_s = int(row["best_replay_ms"]) / 1000
        replay = glob.glob(str(root / "reference_replays" / f"{name}_*.Replay.Gbx"))[0]
        ghost, positions = read_positions(replay)
        jump = np.linalg.norm(np.diff(np.array(positions), axis=0), axis=1).max()
        if jump > max_metres_per_sample:
            skipped.append((name, f"{ghost.num_respawns} respawns, biggest jump {jump:.0f} m"))
            continue
        line_file = f"{name}_0.5m_record.npy"
        np.save(base_dir / "maps" / line_file, resample(positions))
        levels.append((short, name, line_file, record_s))
        best, author = int(row["best_replay_ms"]), row["author_time"]
        minutes, _, seconds = author.rpartition(":")
        author_ms = (int(minutes or 0) * 60 + float(seconds)) * 1000
        if best / author_ms < shortcut_ratio:
            shortcuts.append(f"{short} {best / author_ms:.2f}")

    with open(base_dir / "config_files" / "all_maps.py", "w", encoding="utf-8") as f:
        f.write("all_maps = [\n")
        for level in levels:
            f.write(f"    {level!r},\n")
        f.write("]\n")
    print("lines ready", len(levels), "of", len(rows))
    print("skipped", skipped)
    print("probable shortcuts, record/author", shortcuts)
    for path in sorted(glob.glob(str(base_dir / "maps" / "*_record.npy")))[:3]:
        line = np.load(path)
        print(os.path.basename(path), line.shape, "max gap", round(float(np.linalg.norm(np.diff(line, axis=0), axis=1).max()), 3))


if __name__ == "__main__":
    main()
