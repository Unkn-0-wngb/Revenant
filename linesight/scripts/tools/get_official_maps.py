"""
Downloads the official map files listed in official_records.csv and copies them to the game's Official Maps folder.
"""

import csv
import sys
import shutil
import time
import urllib.request
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
root = base_dir.parent
store = root / "official_maps"
sys.path.insert(0, str(root))
import paths

game_maps = Path(paths.OFFICIAL_MAPS)


def main():
    store.mkdir(exist_ok=True)
    game_maps.mkdir(parents=True, exist_ok=True)
    failed = []
    for row in csv.DictReader(open(root / "official_records.csv", encoding="utf-8")):
        name = f"{row['map']}.Challenge.Gbx"
        path = store / name
        if not path.exists():
            request = urllib.request.Request(
                f"https://tmnf.exchange/trackgbx/{row['tmx_track_id']}",
                headers={"User-Agent": "tmnf-map-script"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
            if body[:3] != b"GBX":
                failed.append(row["map"])
                continue
            path.write_bytes(body)
            time.sleep(1)
        if not (game_maps / name).exists():
            shutil.copyfile(path, game_maps / name)
    print("failed", failed)
    print("maps in game folder", len(list(game_maps.glob("*.Challenge.Gbx"))))


if __name__ == "__main__":
    main()
