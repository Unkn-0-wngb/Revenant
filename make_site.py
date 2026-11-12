"""Refreshes the level times on the website from the training logs.
Run it after training, then deploy the site folder."""
import json
import os
import time

import level_stats

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "site", "assets", "levels.json")


def best_times():
    best, _ = level_stats.Stats("all_levels_run1").read()
    stats = level_stats.Stats("A07_run1")
    for short, value in stats.read()[0].items():
        best[short] = min(best.get(short, 1e9), value)
    return best


def tried_levels():
    events = level_stats.Events("all_levels_run1", "A07_run1")
    return {tag.rsplit("_", 1)[1] for tag in events.update() if "_trained_" in tag}


def main():
    best = best_times()
    tried = tried_levels()
    levels = []
    for level in level_stats.load_levels():
        short = level["short"]
        value = best.get(short)
        if value is not None and value <= level["author"]:
            status = "author"
        elif value is not None:
            status = "finished"
        elif short in tried:
            status = "tried"
        else:
            status = "waiting"
        levels.append({
            "id": short,
            "name": level["name"].split("-", 1)[1],
            "author": round(level["author"], 2),
            "best": round(value, 2) if value is not None else None,
            "status": status,
        })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": time.strftime("%Y-%m-%d"), "levels": levels}, f, separators=(",", ":"))
    finished = sum(level["best"] is not None for level in levels)
    author = sum(level["status"] == "author" for level in levels)
    print(f"{finished} finished, {author} beat author, saved to {OUT}")


if __name__ == "__main__":
    main()
