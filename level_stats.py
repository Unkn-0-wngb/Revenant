import collections
import csv
import glob
import os
import struct

import numpy as np
from tensorboard.compat.proto import event_pb2

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_GOLD_S = 120
SCALARS = (b"race", b"wall_contact", b"single_zone")


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


def read_events(path, start, rows):
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read()
    at = 0
    while at + 12 <= len(data):
        (length,) = struct.unpack_from("<Q", data, at)
        end = at + 12 + length + 4
        if end > len(data):
            break
        body = data[at + 12 : at + 12 + length]
        at = end
        if not any(word in body for word in SCALARS):
            continue
        event = event_pb2.Event.FromString(body)
        for value in event.summary.value:
            number = value.simple_value if value.HasField("simple_value") else (value.tensor.float_val or [0.0])[0]
            rows[value.tag].append((event.step, number))
    return start + at


class Events:
    def __init__(self, *runs):
        self.patterns = [os.path.join(ROOT, "linesight", "tensorboard", run + "*", "events*") for run in runs]
        self.offsets = {}
        self.rows = collections.defaultdict(list)

    def update(self):
        for pattern in self.patterns:
            for path in glob.glob(pattern):
                size = os.path.getsize(path)
                if size < 5000 or self.offsets.get(path, 0) >= size:
                    continue
                self.offsets[path] = read_events(path, self.offsets.get(path, 0), self.rows)
        return self.rows


class Stats:
    def __init__(self, run):
        self.events = Events(run)

    def read(self):
        self.events.update()
        return self.times()

    def stuck_spots(self, window=60, share=0.5):
        spots = {}
        for tag, rows in self.events.rows.items():
            if not tag.startswith("single_zone_reached_trained_"):
                continue
            short = tag.rsplit("_", 1)[1]
            recent = [int(zone) for _, zone in sorted(rows)[-window:]]
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
        for tag, rows in self.events.rows.items():
            if "race_time_finished_" not in tag:
                continue
            short = tag.rsplit("_", 1)[1]
            values = [value for _, value in rows if value > 0]
            if values:
                best[short] = min(best.get(short, 1e9), min(values))
                finishes[short] = finishes.get(short, 0) + len(values)
        return best, finishes
