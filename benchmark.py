import json
import multiprocessing
import os
import statistics
import sys
import threading
import time
from pathlib import Path

import joblib
import psutil
import torch

ROOT = os.path.dirname(os.path.abspath(__file__))
LINESIGHT = Path(ROOT) / "linesight"
sys.path.insert(0, str(LINESIGHT))
os.chdir(LINESIGHT)

from config_files import config_copy
from config_files.all_maps import all_maps
from trackmania_rl.agents import iqn
from trackmania_rl.map_loader import load_next_map_zone_centers
from trackmania_rl.tmi_interaction import game_instance_manager

import auto_profile_click
import paths

SUITE = ["A07", "A11", "B01", "B10", "C01", "C08", "D01", "D03"]
PORT = config_copy.base_tmi_port + paths.BENCHMARK_PORT_OFFSET
RUN = LINESIGHT / "save" / config_copy.run_name


def games():
    return {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "tmforever.exe"}


def click_until_loaded(tmi, before, stop):
    attempt = 0
    end = time.time() + 300
    while time.time() < end and not stop.is_set():
        time.sleep(8)
        if isinstance(tmi.latest_map_path_requested, str):
            return
        for pid in games() - before:
            auto_profile_click.try_game(pid, attempt)
        attempt += 1


def pick_levels(arg):
    have = [short for short, *_ in all_maps if (RUN / "levels" / short / "weights1.torch").exists()]
    if arg == "suite":
        return [level for level in SUITE if level in have]
    if arg == "all":
        return have
    if arg == "finished":
        best = joblib.load(RUN / "accumulated_stats.joblib")["alltime_min_ms"]
        return [level for level in have if best.get(level, 300000) < 300000]
    return [level.strip().upper() for level in arg.split(",")]


def load_brain(level, brains):
    folder = Path(brains) if brains else RUN / "levels" / level
    network, _ = iqn.make_untrained_iqn_network(False, is_inference=True)
    network.load_state_dict(torch.load(f=folder / "weights1.torch", weights_only=False))
    network.eval()
    inferer = iqn.Inferer(network, config_copy.iqn_k, config_copy.tau_epsilon_boltzmann)
    inferer.epsilon = 0
    inferer.epsilon_boltzmann = 0
    inferer.is_explo = False
    return inferer


def main():
    levels = pick_levels(sys.argv[1] if len(sys.argv) > 1 else "suite")
    laps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    brains = sys.argv[3] if len(sys.argv) > 3 else None
    out = Path(ROOT) / "logs" / f"benchmark_{time.strftime('%Y%m%d_%H%M')}.json"
    out.parent.mkdir(exist_ok=True)
    by_name = {short: (f'"Official Maps/{map_file}.Challenge.Gbx"', line) for short, map_file, line, _ in all_maps}

    tmi = game_instance_manager.GameInstanceManager(
        game_spawning_lock=multiprocessing.Lock(),
        running_speed=config_copy.running_speed,
        run_steps_per_action=config_copy.tm_engine_step_per_action,
        max_overall_duration_ms=config_copy.cutoff_rollout_if_race_not_finished_within_duration_ms,
        max_minirace_duration_ms=config_copy.cutoff_rollout_if_no_vcp_passed_within_duration_ms,
        tmi_port=PORT,
    )
    stop = threading.Event()
    threading.Thread(target=click_until_loaded, args=(tmi, games(), stop), daemon=True).start()

    report = {"when": time.strftime("%Y-%m-%d %H:%M"), "brains": brains or "levels", "laps": laps, "levels": {}}
    try:
        for level in levels:
            if level not in by_name:
                print(f"{level}: not a level")
                continue
            map_path, line = by_name[level]
            inferer = load_brain(level, brains)
            zone_centers = load_next_map_zone_centers(line, LINESIGHT)
            runs = []
            for _ in range(laps):
                results, stats = tmi.rollout(
                    exploration_policy=inferer.get_exploration_action, map_path=map_path, zone_centers=zone_centers, update_network=lambda: None
                )
                runs.append(
                    {
                        "finished": bool(stats.get("race_finished", False)),
                        "time_ms": int(stats["race_time"]),
                        "furthest_zone": int(results["furthest_zone_idx"]),
                        "of_zones": len(zone_centers),
                        "wall_frames": int(sum(bool(w) for w in results["wall_contact"])),
                        "checkpoint_times_ms": [int(t) for t in stats.get("cp_time_ms", [])],
                    }
                )
            done = [r["time_ms"] / 1000 for r in runs if r["finished"]]
            summary = {
                "finish_rate": len(done) / len(runs),
                "best_s": min(done) if done else None,
                "median_s": statistics.median(done) if done else None,
                "furthest_zone": max(r["furthest_zone"] for r in runs),
                "wall_frames_per_lap": statistics.mean(r["wall_frames"] for r in runs),
                "runs": runs,
            }
            report["levels"][level] = summary
            json.dump(report, open(out, "w"), indent=1)
            print(
                f"{level}: {len(done)}/{len(runs)} finished, best {summary['best_s'] or '-'}, median {summary['median_s'] or '-'}, "
                f"furthest zone {summary['furthest_zone']} of {len(zone_centers)}, wall frames {summary['wall_frames_per_lap']:.1f}",
                flush=True,
            )
    finally:
        stop.set()
        try:
            tmi.iface.close()
        except Exception:
            pass
        if tmi.tm_process_id:
            os.system(f"taskkill /PID {tmi.tm_process_id} /T /F >nul 2>&1")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
