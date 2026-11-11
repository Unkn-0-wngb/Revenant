"""
Replaces a level's reference line with a slower replay, for levels whose record uses a shortcut the AI can't copy.
Usage: swap_reference_line.py A12 18000 19500   (level, then the replay time range in ms)
Needs logs/replays_<level>.json, a list of that level's replays from TMNF Exchange.
"""

import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from pygbx import Gbx, GbxType

base_dir = Path(__file__).resolve().parents[2]
root = base_dir.parent
sys.path.insert(0, str(base_dir))
sys.path.insert(0, str(base_dir / "scripts" / "tools"))
from build_reference_lines import max_metres_per_sample, read_positions, resample
from config_files import config
import trackmania_rl.map_loader as map_loader

map_loader.config_copy = config


def line_is_clean(line, positions, map_path):
    zones = np.vstack((np.repeat(line[:1], 20, axis=0), line))
    checkpoints = map_loader.get_checkpoint_positions_from_gbx(map_path)
    distances = [float(np.linalg.norm(zones - cp, axis=1).min()) for cp in checkpoints]
    jump = float(np.linalg.norm(np.diff(np.array(positions), axis=0), axis=1).max())
    return jump <= max_metres_per_sample, jump, sorted(round(d, 1) for d in distances)


def main():
    level, low, high = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    name = next(entry[1] for entry in config.all_maps if entry[0] == level)
    line_path = base_dir / "maps" / f"{name}_0.5m_record.npy"
    map_path = f'"Official Maps/{name}.Challenge.Gbx"'
    replays = json.load(open(root / "logs" / f"replays_{level}.json", encoding="utf-8"))
    candidates = [r for r in replays if low <= r["ReplayTime"] <= high]
    folder = root / "reference_replays_normal"
    folder.mkdir(exist_ok=True)
    for replay in candidates[:8]:
        path = folder / f"{name}_{replay['ReplayTime']}ms_{replay['ReplayId']}.Replay.Gbx"
        request = urllib.request.Request(f"https://tmnf.exchange/recordgbx/{replay['ReplayId']}", headers={"User-Agent": "tmnf-replay-script"})
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
        if body[:3] != b"GBX":
            continue
        path.write_bytes(body)
        ghost, positions = read_positions(str(path))
        line = resample(positions)
        clean, jump, distances = line_is_clean(line, positions, map_path)
        print(f"{replay['ReplayTime'] / 1000:.2f}s by {replay['User']['Name']}: respawns {ghost.num_respawns}, biggest jump {jump:.0f} m, length {len(line) * 0.5:.0f} m, closest to each checkpoint {distances}")
        if clean and ghost.num_respawns == 0:
            backup = root / "backup" / "record_lines"
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(line_path, backup / line_path.name)
            np.save(line_path, line)
            print("swapped in", path.name)
            return
        time.sleep(1)
    print("no clean replay found")


if __name__ == "__main__":
    main()
