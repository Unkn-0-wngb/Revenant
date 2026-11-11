"""
Builds a level's reference line from the most common route, by lining up 10-15 clean replays near Gold and taking
the median position. Shortcuts taken by only a few players get outvoted.
Usage: build_consensus_line.py C09 [C10 ...]   (needs logs/replays_<level>.json; --dry to only report, --max-cp=40 to allow
a checkpoint further than 30m from the line)
"""

import csv
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

base_dir = Path(__file__).resolve().parents[2]
root = base_dir.parent
sys.path.insert(0, str(base_dir))
sys.path.insert(0, str(base_dir / "scripts" / "tools"))
from build_reference_lines import max_metres_per_sample, read_positions, resample
from config_files import config
import trackmania_rl.map_loader as map_loader

map_loader.config_copy = config
headers = {"User-Agent": "tmnf-replay-script"}
max_gap_m = 25
off_route_m = 15
max_cp_m = 30


def align(main, other):
    out = np.full(main.shape, np.nan)
    j = 0
    for i, p in enumerate(main):
        near = other[j : j + 200]
        d = np.linalg.norm(near - p, axis=1)
        k = int(d.argmin())
        if d[k] > max_gap_m:
            near = other[j : j + 2000]
            d = np.linalg.norm(near - p, axis=1)
            k = int(d.argmin())
            if d[k] > max_gap_m:
                continue
        j += k
        out[i] = other[j]
    return out


def off_route(main, other):
    matched = align(main, other)
    gap = np.linalg.norm(matched - main, axis=1)
    return float(np.mean(~(gap <= off_route_m)))


def download(level, name, replays):
    folder = root / "reference_replays_normal"
    folder.mkdir(exist_ok=True)
    lines = []
    for replay in replays:
        if len(lines) >= 15:
            break
        path = folder / f"{name}_{replay['ReplayTime']}ms_{replay['ReplayId']}.Replay.Gbx"
        if not path.exists():
            try:
                request = urllib.request.Request(f"https://tmnf.exchange/recordgbx/{replay['ReplayId']}", headers=headers)
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read()
            except OSError:
                time.sleep(5)
                continue
            time.sleep(1)
            if body[:3] != b"GBX":
                continue
            path.write_bytes(body)
        try:
            ghost, positions = read_positions(str(path))
        except Exception:
            continue
        if len(positions) < 10 or ghost.num_respawns:
            continue
        if np.linalg.norm(np.diff(np.array(positions), axis=0), axis=1).max() > max_metres_per_sample:
            continue
        lines.append((replay["ReplayTime"], resample(positions)))
    return lines


def build(level, dry):
    records = {r["map"][:3]: r for r in csv.DictReader(open(root / "official_records.csv", encoding="utf-8"))}
    name = next(e[1] for e in config.all_maps if e[0] == level)
    line_path = base_dir / "maps" / f"{name}_0.5m_record.npy"
    minutes, _, seconds = records[level]["author_time"].rpartition(":")
    author = (int(minutes or 0) * 60 + float(seconds)) * 1000
    gold = config.gold_times[level] * 1000
    replays = json.load(open(root / "logs" / f"replays_{level}.json", encoding="utf-8"))
    pool = [r for r in replays if 0.97 * author <= r["ReplayTime"] <= 1.05 * gold]
    if len(pool) < 6:
        pool = sorted(replays, key=lambda r: -r["ReplayTime"])[:30]
    step = max(1, len(pool) // 30)
    lines = download(level, name, pool[::step][:30])
    if len(lines) < 5:
        print(f"{level}: only {len(lines)} clean replays, left alone", flush=True)
        return
    scores = [np.mean([off_route(a, b) for _, b in lines if b is not a]) for _, a in lines]
    order = np.argsort(scores)
    main = lines[order[0]][1]
    agree = [lines[i][1] for i in order if scores[i] < 0.5 or i == order[0]]
    matched = np.stack([main] + [align(main, other) for other in agree[1:]])
    counts = np.sum(~np.isnan(matched[:, :, 0]), axis=0)
    median = np.nanmedian(matched, axis=0)
    median[counts < max(2, len(agree) // 2)] = main[counts < max(2, len(agree) // 2)]
    kernel = np.ones(9) / 9
    padded = np.vstack((np.repeat(median[:1], 4, axis=0), median, np.repeat(median[-1:], 4, axis=0)))
    smooth = np.stack([np.convolve(padded[:, k], kernel, mode="valid") for k in range(3)], axis=1)
    smooth[:5] = median[:5]
    smooth[-5:] = median[-5:]
    line = resample(list(smooth))
    old = np.load(line_path)
    old_off = off_route(line, old)
    cps = map_loader.get_checkpoint_positions_from_gbx(f'"Official Maps/{name}.Challenge.Gbx"')
    zones = np.vstack((np.repeat(line[:1], 20, axis=0), line))
    cp_gaps = sorted(round(float(np.linalg.norm(zones - cp, axis=1).min()), 1) for cp in cps)
    print(
        f"{level}: {len(agree)} of {len(lines)} replays share the main route, length {len(line) * 0.5:.0f}m "
        f"(old line {len(old) * 0.5:.0f}m, {old_off:.0%} of the new route is off the old line), checkpoints {cp_gaps}",
        flush=True,
    )
    if dry or max(cp_gaps) > max_cp_m:
        if max(cp_gaps) > max_cp_m:
            print(f"{level}: a checkpoint is over {max_cp_m}m from the line, left alone", flush=True)
        return
    backup = root / "backup" / "record_lines"
    backup.mkdir(parents=True, exist_ok=True)
    if not (backup / line_path.name).exists():
        shutil.copy2(line_path, backup / line_path.name)
    np.save(line_path, line)


def main():
    global max_cp_m
    dry = "--dry" in sys.argv
    for arg in sys.argv[1:]:
        if arg.startswith("--max-cp="):
            max_cp_m = float(arg.split("=")[1])
    for level in [a for a in sys.argv[1:] if not a.startswith("--")]:
        try:
            build(level, dry)
        except Exception as e:
            print(f"{level}: failed, {e}", flush=True)


if __name__ == "__main__":
    main()
