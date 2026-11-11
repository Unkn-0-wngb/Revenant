"""
Keeps each level's fastest finished laps on disk, one file per level, so memory use does not grow with the number of levels.
"""

import random
from pathlib import Path

import joblib


def lap_file(folder: Path, map_name: str):
    return folder / f"{map_name}.joblib"


def read_laps(folder: Path, map_name: str):
    path = lap_file(folder, map_name)
    return joblib.load(path) if path.exists() else []


def add_lap(folder: Path, map_name: str, rollout_results: dict, kept: int):
    laps = read_laps(folder, map_name)
    race_time = rollout_results["race_time"]
    if len(laps) >= kept and race_time >= laps[-1][0]:
        return None
    laps.append((race_time, rollout_results))
    laps.sort(key=lambda lap: lap[0])
    laps = laps[:kept]
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f"{map_name}.tmp"
    try:
        joblib.dump(laps, temporary)
        temporary.replace(lap_file(folder, map_name))
    except OSError as e:
        print(f" Could not save best laps for {map_name}: {e}")
        return None
    return [lap[0] / 1000 for lap in laps]


def pick_other_lap(folder: Path, map_name: str):
    others = [path.stem for path in folder.glob("*.joblib") if path.stem != map_name]
    return pick_lap(folder, random.choice(others)) if others else None


def pick_lap(folder: Path, map_name: str):
    laps = read_laps(folder, map_name)
    if not laps:
        return None
    race_time, lap = random.choice(laps)
    return map_name, race_time, lap
