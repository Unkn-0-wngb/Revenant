"""Keeps a demo start queued for one level: the follower's actions cut at a random step, after which the AI drives.
Usage: refeed.py D02 [first_step] [last_step] [seconds]"""
import os
import random
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
level = sys.argv[1]
lap = np.load(os.path.join(ROOT, "bruteforce", f"{level}_follow_partial.npy"))
first = int(sys.argv[2]) if len(sys.argv) > 2 else 300
last = int(sys.argv[3]) if len(sys.argv) > 3 else len(lap) - 50
wait = float(sys.argv[4]) if len(sys.argv) > 4 else 60
feed = os.path.join(ROOT, "bruteforce", "feed")
target = os.path.join(feed, f"{level}_prefix.npy")
log_path = os.path.join(ROOT, "logs", f"refeed_{level}.log")
last = max(first, min(last, len(lap) - 1))
os.makedirs(feed, exist_ok=True)
os.makedirs(os.path.dirname(log_path), exist_ok=True)

while True:
    if not os.path.exists(target) and not os.path.exists(os.path.join(feed, f"{level}.npy")):
        cut = random.randint(first, last)
        np.save(target.replace(".npy", "_new.npy"), lap[:cut])
        os.replace(target.replace(".npy", "_new.npy"), target)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%d/%m %H:%M:%S')} demo start queued, AI takes over at step {cut}\n")
    time.sleep(wait)
