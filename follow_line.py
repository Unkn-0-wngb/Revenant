"""Builds a finishing lap out of the AI's own 50 ms actions by following a level's record line on a third game.
Each step tries every action for a short look-ahead and keeps the one that stays closest to the line while going
furthest along it. When every choice goes off the line it backs up a few steps and tries again with some randomness.
Usage: follow_line.py D02 [minutes]
The lap goes to bruteforce/<level>_follow_<ms>.npy and bruteforce/feed/<level>.npy, progress to logs/follow_<level>.log."""
import os
import random
import socket
import struct
import subprocess
import sys
import threading
import time

import joblib
import numpy as np
import psutil
from pygbx import Gbx, GbxType
from tminterface.structs import CheckpointData, SimStateData

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "linesight"))
from config_files import config_copy, user_config
from trackmania_rl.contact_materials import physics_behavior_fromint
from trackmania_rl.tmi_interaction.tminterface2 import MessageType, TMInterface

import auto_profile_click

PORT = user_config.base_tmi_port + 2
SPEED = 200
FIRST = 2
SECOND = 6
FAR_OFF = 7.0
STALL_STEPS = 40
STALL_POINTS = 12
CHECK_EVERY = 40

level = sys.argv[1]
minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 240
entry = next(e for e in config_copy.levels if e[0] == level)
map_path = entry[1].replace("/", "\\")
own_line = os.path.join(ROOT, "bruteforce", f"follow_{level}_line.npy")
line = np.load(own_line if os.path.exists(own_line) else os.path.join(ROOT, "linesight", "maps", entry[2]))
line_dir = np.gradient(line, axis=0)
line_dir /= np.linalg.norm(line_dir, axis=1, keepdims=True) + 1e-9
record_file = min(
    (f for f in os.listdir(os.path.join(ROOT, "reference_replays")) if f.startswith(level + "-") and f.endswith(".Replay.Gbx")),
    key=lambda f: int(f.split("_")[-2][:-2]),
)
ghosts = Gbx(os.path.join(ROOT, "reference_replays", record_file)).get_classes_by_ids([GbxType.CTN_GHOST])
ghost = min(ghosts, key=lambda g: g.race_time)
ghost_points = np.array([[r.position.x, r.position.y, r.position.z] for r in ghost.records])
ghost_speed = np.linalg.norm(np.diff(ghost_points, axis=0), axis=1) / (ghost.sample_period / 1000)
ghost_speed = np.convolve(np.append(ghost_speed, ghost_speed[-1]), np.ones(3) / 3, mode="same")
record_speed = np.zeros(len(line))
for j in range(len(line)):
    guess = int(j / len(line) * len(ghost_points))
    lo, hi = max(0, guess - 60), min(len(ghost_points), guess + 60)
    d = np.linalg.norm(ghost_points[lo:hi] - line[j], axis=1)
    r = int(d.argmin())
    record_speed[j] = ghost_speed[lo + r] if d[r] < 15 else 1000
inputs = config_copy.inputs
forward = config_copy.action_forward_idx
start_steps = config_copy.forced_forward_actions
throttle = [i for i, a in enumerate(inputs) if a["accelerate"] and not a["brake"]]
out_dir = os.path.join(ROOT, "bruteforce")
os.makedirs(os.path.join(out_dir, "feed"), exist_ok=True)
log_path = os.path.join(ROOT, "logs", f"follow_{level}.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
partial_path = os.path.join(out_dir, f"{level}_follow_partial.npy")
save_path = os.path.join(out_dir, f"follow_{level}_progress.joblib")


def log(message):
    text = f"{time.strftime('%d/%m %H:%M:%S')} {message}"
    print(text, flush=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def launch_game():
    command = (
        'powershell -executionPolicy bypass -command "& {'
        f" $process = start-process -FilePath '{user_config.windows_TMLoader_path}'"
        " -PassThru -ArgumentList "
        f'\'run TmForever "{user_config.windows_TMLoader_profile_name}" /configstring=\\"set custom_port {PORT}\\"\';'
        ' echo exit $process.id}"'
    )
    loader = int(subprocess.check_output(command, cwd=os.path.dirname(user_config.windows_TMLoader_path)).decode().split("\r\n")[1])
    while True:
        for p in psutil.process_iter(["name", "ppid"]):
            if (p.info["name"] or "").lower() == "tmforever.exe" and p.info["ppid"] == loader:
                return p.pid
        time.sleep(1)


def click_profile(pid, connected):
    time.sleep(25)
    for _ in range(20):
        if connected.is_set():
            return
        hwnd = auto_profile_click.window_of(pid)
        if hwnd:
            auto_profile_click.posted_click(hwnd)
        time.sleep(8)


def raw_state(iface):
    iface.sock.sendall(struct.pack("i", MessageType.C_GET_SIMULATION_STATE))
    length = iface._read_int32()
    return iface.sock.recv(length, socket.MSG_WAITALL)


def full_state(raw):
    state = SimStateData(raw)
    state.cp_data.resize(CheckpointData.cp_states_field, state.cp_data.cp_states_length)
    state.cp_data.resize(CheckpointData.cp_times_field, state.cp_data.cp_times_length)
    return state


def nearest(position, around):
    lo = max(0, around - 20)
    hi = min(len(line), around + 600)
    d = np.linalg.norm((line[lo:hi] - position) * [1, 0.25, 1], axis=1)
    i = int(d.argmin())
    return lo + i, float(d[i])


def on_grass(state):
    wheels = [state.simulation_wheels[i].real_time_state for i in range(4)]
    return sum(1 for w in wheels if w.has_ground_contact and physics_behavior_fromint.get(w.contact_material_id & 0xFFFF) == 1)


def allowed_off(state):
    wheels = [state.simulation_wheels[i].real_time_state for i in range(4)]
    return FAR_OFF if any(w.has_ground_contact for w in wheels) else 25.0


def score(state, around):
    position = np.array(state.dyna.current_state.position)
    velocity = np.array(state.dyna.current_state.linear_speed)
    i, off = nearest(position, around)
    speed = float(np.linalg.norm(velocity))
    heading = 1 - float(np.dot(velocity, line_dir[i])) / (speed + 1e-6)
    over = max(0.0, speed - 1.05 * record_speed[i])
    under = max(0.0, 0.95 * record_speed[i] - speed) if record_speed[i] < 1000 else 0.0
    cost = -0.5 * i + 0.7 * off + 0.15 * off * off + 6 * heading + 10 * on_grass(state) + 0.5 * over * over + 0.03 * under * under
    if off > allowed_off(state):
        cost += 1000
    return cost


def main():
    log(f"start {level}, line {len(line)} points, {minutes} min")
    pid = launch_game()
    log(f"game pid {pid}")
    connected = threading.Event()
    threading.Thread(target=click_profile, args=(pid, connected), daemon=True).start()

    iface = TMInterface(PORT)
    while True:
        try:
            iface.register(config_copy.tmi_protection_timeout_s)
            break
        except ConnectionRefusedError:
            time.sleep(1)

    actions = [forward] * start_steps
    states = {}
    progress = {}
    fails = {}
    started = False
    mode = "drive"
    k = 0
    candidates = []
    ci = 0
    results = []
    second = SECOND
    noise = 0.0
    best_progress = 0
    lap = None
    lap_time = None
    finish_target = None
    replayed = None
    checked = start_steps
    end_time = time.time() + minutes * 60
    last_report = time.time()

    def set_action(a):
        iface.rewind_to_current_state()
        iface.set_input_state(**inputs[a])

    def start_candidate():
        iface.rewind_to_state(full_state(states[k]))
        iface.rewind_to_current_state()
        iface.set_input_state(**inputs[candidates[ci][0]])

    def plan():
        nonlocal mode, candidates, ci, results, second
        second = SECOND if fails.get(progress[k] // 100, 0) < 4 else 3 * SECOND
        candidates = [(a, b) for a in range(len(inputs)) for b in throttle]
        ci = 0
        results = []
        mode = "eval"
        start_candidate()

    def start_check():
        nonlocal mode
        iface.rewind_to_state(full_state(states[checked]))
        iface.set_input_state(**inputs[actions[checked]])
        mode = "check"

    def save():
        keep = {j: s for j, s in states.items() if j <= k}
        joblib.dump({"actions": actions, "states": keep, "progress": progress, "fails": fails, "checked": checked}, save_path)

    def back_up(why):
        nonlocal k, noise, checked
        here = full_state(states[k]) if k in states else None
        if here is not None:
            dyna = here.dyna.current_state
            touching = sum(here.simulation_wheels[i].real_time_state.has_ground_contact for i in range(4))
            log(f"  at step {k}: car {np.round(dyna.position, 1)}, line {np.round(line[progress[k]], 1)}, {np.linalg.norm(dyna.linear_speed) * 3.6:.0f} km/h, {touching} wheels down")
        region = progress[k] // 100
        fails[region] = fails.get(region, 0) + 1
        tries = fails[region]
        k = max(start_steps, k - 6 - 6 * tries)
        checked = min(checked, k)
        del actions[k:]
        for j in [j for j in states if j > k]:
            del states[j]
        noise = min(40.0, 6.0 * tries)
        log(f"{why} near line point {region * 100}, backing up to step {k} (try {tries} here)")

    try:
        while time.time() < end_time and replayed is None:
            msgtype = iface._read_int32()
            if msgtype == int(MessageType.SC_RUN_STEP_SYNC):
                now = iface._read_int32()
                if not started:
                    if now == 0:
                        connected.set()
                        started = True
                        iface.set_timeout(config_copy.timeout_during_run_ms)
                        iface.set_speed(SPEED)
                        states[0] = raw_state(iface)
                        if os.path.exists(save_path):
                            saved = joblib.load(save_path)
                            actions, states, progress, fails = saved["actions"], saved["states"], saved["progress"], saved["fails"]
                            checked = saved.get("checked", start_steps)
                            k = len(actions)
                            best_progress = progress[k]
                            log(f"race started, carrying on from step {k}, line point {progress[k]}")
                            plan()
                        else:
                            set_action(forward)
                            log("race started")
                elif now >= 0 and now % 50 == 0:
                    step = now // 50
                    if mode == "drive":
                        states[step] = raw_state(iface)
                        if step >= start_steps:
                            k = step
                            progress[k] = nearest(np.array(full_state(states[k]).dyna.current_state.position), 0)[0]
                            plan()
                    elif mode == "eval":
                        if step == k + FIRST:
                            set_action(candidates[ci][1])
                        elif step == k + FIRST + second:
                            cost = score(iface.get_simulation_state(), progress[k])
                            results.append((cost + random.gauss(0, noise), candidates[ci]))
                            ci += 1
                            if ci < len(candidates):
                                start_candidate()
                            else:
                                results.sort(key=lambda r: r[0])
                                if results[0][0] >= 1000 - 3 * noise:
                                    back_up("off the line")
                                    plan()
                                else:
                                    actions.append(results[0][1][0])
                                    iface.rewind_to_state(full_state(states[0]))
                                    iface.set_input_state(**inputs[actions[0]])
                                    mode = "commit"
                    elif mode == "commit" and step < len(actions):
                        if actions[step] != actions[step - 1]:
                            set_action(actions[step])
                    elif mode == "commit":
                        k += 1
                        states[k] = raw_state(iface)
                        now_state = full_state(states[k])
                        position = np.array(now_state.dyna.current_state.position)
                        progress[k], off = nearest(position, progress[k - 1])
                        noise = max(0.0, noise - 0.5)
                        if progress[k] > best_progress + 400:
                            best_progress = progress[k]
                            log(f"step {k}, line point {progress[k]} of {len(line)}, {off:.1f} m off")
                        if now > config_copy.cutoff_rollout_if_race_not_finished_within_duration_ms:
                            log("too slow, giving up")
                            break
                        if off > allowed_off(now_state):
                            back_up("off the line")
                        elif k - STALL_STEPS in progress and progress[k] - progress[k - STALL_STEPS] < STALL_POINTS:
                            back_up("stalled")
                        elif k % 50 == 0:
                            checked = k
                            save()
                        plan()
                    elif mode == "check":
                        raw = raw_state(iface)
                        moved = float(np.linalg.norm(np.array(full_state(raw).dyna.current_state.position) - np.array(full_state(states[step]).dyna.current_state.position)))
                        states[step] = raw
                        if moved > 0.01:
                            log(f"straight replay differs by {moved:.2f} m at step {step}, carrying on from there")
                            k = step
                            checked = step
                            del actions[k:]
                            for j in [j for j in states if j > k]:
                                del states[j]
                            progress[k] = nearest(np.array(full_state(raw).dyna.current_state.position), progress[k - 1])[0]
                            save()
                            plan()
                        elif step >= k:
                            checked = k
                            save()
                            plan()
                        elif actions[step] != actions[step - 1]:
                            set_action(actions[step])
                    elif mode == "verify":
                        if step > len(lap) + 40:
                            log("replay did not finish")
                            break
                        a = lap[step] if step < len(lap) else forward
                        b = lap[step - 1] if step - 1 < len(lap) else forward
                        if a != b:
                            set_action(a)
                iface._respond_to_call(msgtype)
            elif msgtype == int(MessageType.SC_CHECKPOINT_COUNT_CHANGED_SYNC):
                current = iface._read_int32()
                target = iface._read_int32()
                if started and current == target:
                    race_time = iface.get_simulation_state().race_time
                    if mode == "eval" and race_time >= 50 * k and progress[k] > len(line) * 0.8:
                        a, b = candidates[ci]
                        lap = actions + [a] * FIRST + [b] * second
                        lap_time = race_time
                        finish_target = target
                        log(f"finished in {race_time} ms with {len(lap)} actions, checking it replays")
                        iface.rewind_to_state(full_state(states[0]))
                        iface.set_input_state(**inputs[lap[0]])
                        mode = "verify"
                    elif mode == "verify" and target == finish_target:
                        replayed = race_time
                iface._respond_to_call(msgtype)
            elif msgtype == int(MessageType.SC_LAP_COUNT_CHANGED_SYNC):
                iface._read_int32()
                iface._read_int32()
                iface._respond_to_call(msgtype)
            elif msgtype == int(MessageType.SC_REQUESTED_FRAME_SYNC):
                iface._respond_to_call(msgtype)
            elif msgtype == int(MessageType.SC_ON_CONNECT_SYNC):
                iface.execute_command("set countdown_speed 80")
                iface.execute_command(f"set autologin {config_copy.username}")
                iface.execute_command("set unfocused_fps_limit false")
                iface.execute_command("set skip_map_load_screens true")
                iface.execute_command("set autorewind false")
                iface.execute_command("set auto_reload_plugins false")
                iface.set_on_step_period(50)
                iface.execute_command(f"map {map_path}")
                log("connected, loading map")
                iface._respond_to_call(msgtype)
            if time.time() - last_report > 300:
                last_report = time.time()
                log(f"at step {k}, line point {progress.get(k)} of {len(line)}, backups {sum(fails.values())}")

        if replayed is None:
            done = actions[:checked]
            if len(done) > start_steps + 100 and (not os.path.exists(partial_path) or len(np.load(partial_path)) < len(done)):
                np.save(partial_path, np.array(done))
                log(f"no full lap, kept the first {len(done)} checked steps for demo starts")
            else:
                log("no lap saved")
            return
        log(f"replay finished in {replayed} ms (search said {lap_time})")
        np.save(os.path.join(out_dir, f"{level}_follow_{replayed}.npy"), np.array(lap))
        np.save(partial_path, np.array(lap))
        np.save(os.path.join(out_dir, "feed", f"{level}_new.npy"), np.array(lap))
        os.replace(os.path.join(out_dir, "feed", f"{level}_new.npy"), os.path.join(out_dir, "feed", f"{level}.npy"))
        os.remove(save_path)
        log("saved and fed")
    except (socket.timeout, ConnectionError) as e:
        log(f"connection lost: {e}")
    finally:
        try:
            iface.close()
        except OSError:
            pass
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


if __name__ == "__main__":
    main()
