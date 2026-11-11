import csv
import glob
import os

import numpy as np
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_GOLD_S = 120


def seconds(text):
    minutes, _, rest = text.rpartition(":")
    return int(minutes or 0) * 60 + float(rest)


def load_levels():
    with open(os.path.join(ROOT, "official_records.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(os.path.join(ROOT, "official_medals.csv"), encoding="utf-8") as f:
        gold = {row["map"][:3]: seconds(row["gold"]) for row in csv.DictReader(f)}
    lines = glob.glob(os.path.join(ROOT, "linesight", "maps", "*_record.npy"))
    have_line = {os.path.basename(p)[:3] for p in lines} | {"A07"}
    levels = []
    for row in rows:
        short = row["map"][:3]
        record = seconds(row["best_replay_time"])
        note = ""
        if short not in have_line:
            note = "no usable line"
        elif gold[short] > MAX_GOLD_S:
            note = "skipped, Gold over 2 min"
        levels.append({"short": short, "name": row["map"], "author": seconds(row["author_time"]), "record": record, "note": note})
    return levels


class Stats:
    def __init__(self, run):
        self.pattern = os.path.join(ROOT, "linesight", "tensorboard", run + "*", "events*")
        self.accumulators = {}
        self.sizes = {}

    def read(self):
        for path in glob.glob(self.pattern):
            size = os.path.getsize(path)
            if size < 5000 or self.sizes.get(path) == size:
                continue
            self.sizes[path] = size
            if path not in self.accumulators:
                self.accumulators[path] = EventAccumulator(path, size_guidance={"scalars": 0})
            self.accumulators[path].Reload()
        return self.times()

    def stuck_spots(self, window=60, share=0.5):
        zones = {}
        for acc in self.accumulators.values():
            for tag in acc.Tags()["scalars"]:
                if tag.startswith("single_zone_reached_trained_"):
                    short = tag.rsplit("_", 1)[1]
                    zones.setdefault(short, []).extend((e.wall_time, int(e.value)) for e in acc.Scalars(tag))
        spots = {}
        for short, rows in zones.items():
            recent = [zone for _, zone in sorted(rows)[-window:]]
            lines = glob.glob(os.path.join(ROOT, "linesight", "maps", f"{short}-*_0.5m_*.npy"))
            if len(recent) < window or not lines or short == "A07":
                continue
            finish = len(np.load(lines[0])) + 20 - 10
            values = np.array([zone for zone in recent if zone < finish])
            if len(values) == 0:
                continue
            middle = int(np.median(values))
            close = int((np.abs(values - middle) <= 3).sum())
            if close / window >= share:
                spots[short] = (middle, close)
        return spots

    def times(self):
        best, finishes = {}, {}
        for acc in self.accumulators.values():
            for tag in acc.Tags()["scalars"]:
                if "race_time_finished_" not in tag:
                    continue
                short = tag.rsplit("_", 1)[1]
                values = [e.value for e in acc.Scalars(tag) if e.value > 0]
                if values:
                    best[short] = min(best.get(short, 1e9), min(values))
                    finishes[short] = finishes.get(short, 0) + len(values)
        return best, finishes
