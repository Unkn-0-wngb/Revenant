"""Watches the all-levels run and exits with one line when any level gets a new all-time best, or training has a problem."""
import json
import os
import re
import time

import psutil

from level_stats import Stats, load_levels

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "logs", "train_run1.log")
STATE = os.path.join(ROOT, "logs", "levels_watch_state.json")
POLL_S = 120
STALL_S = 600
A07_BEST = 27.11


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"best": None, "errors": 0}


def report(state, message):
    with open(STATE, "w") as f:
        json.dump(state, f)
    print(message, flush=True)
    raise SystemExit(0)


def training_alive():
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if "python" in (p.info["name"] or "").lower() and "train.py" in " ".join(p.info["cmdline"] or []):
                return True
        except psutil.Error:
            pass
    return False


def describe(level, value, previous):
    if previous is None:
        text = f"{level['short']} first finish {value:.2f}s"
    else:
        text = f"{level['short']} {value:.2f}s (was {previous:.2f}s)"
    if value <= level["record"] and (previous is None or previous > level["record"]):
        text += ", beat TMX best"
    elif value <= level["author"] and (previous is None or previous > level["author"]):
        text += ", author medal"
    return text


def main():
    state = load_state()
    levels = load_levels()
    stats = Stats("all_levels_run1")
    if state.get("best") is None:
        state = {"best": stats.read()[0], "errors": 0}
    state["best"]["A07"] = min(state["best"].get("A07", A07_BEST), A07_BEST)
    while True:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            text = f.read()
        found = re.findall(r"NMG=(\d+)", text)
        steps = int(found[-1]) if found else 0
        errors = text.count("Traceback")
        if errors < state["errors"]:
            state["errors"] = errors
        if errors > state["errors"]:
            state["errors"] = errors
            report(state, f"CRASH: traceback in training log at {steps} steps")
        if not training_alive():
            report(state, f"STOPPED: training process is gone at {steps} steps")
        idle = time.time() - os.path.getmtime(LOG)
        if idle > STALL_S:
            report(state, f"STALLED: log silent for {int(idle // 60)} min at {steps} steps, a game may be on the profile screen")

        best, _ = stats.read()
        improved = []
        for level in levels:
            short = level["short"]
            value = best.get(short)
            previous = state["best"].get(short)
            if value is not None and (previous is None or value < previous - 0.001):
                improved.append(describe(level, value, previous))
                state["best"][short] = value
        if improved:
            report(state, "NEW BEST: " + "; ".join(improved))
        reported = state.setdefault("stuck", [])
        for short, (zone, runs) in stats.stuck_spots().items():
            key = f"{short}:{zone // 200}"
            if key not in reported:
                reported.append(key)
                report(state, f"STUCK: {short} stopped around zone {zone} in {runs} of the last 60 runs")
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
