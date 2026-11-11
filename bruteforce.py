"""Random-search bruteforce of a level's best AI lap on a third game, using the AI's own 50 ms action steps.
Usage: bruteforce.py A07 [minutes]
Improved action lists go to bruteforce/<level>_<ms>.npy, progress to logs/bruteforce_<level>.log."""
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
from tminterface.structs import CheckpointData, SimStateData

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "linesight"))
from config_files import config_copy, user_config
from trackmania_rl.tmi_interaction.tminterface2 import MessageType, TMInterface

import auto_profile_click

PORT = user_config.base_tmi_port + 2
SPEED = 200

level = sys.argv[1]
minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 120
map_path = next(entry[1] for entry in config_copy.levels if entry[0] == level).replace("/", "\\")
inputs = config_copy.inputs
out_dir = os.path.join(ROOT, "bruteforce")
os.makedirs(out_dir, exist_ok=True)
log_path = os.path.join(ROOT, "logs", f"bruteforce_{level}.log")


def log(message):
    line = f"{time.strftime('%d/%m %H:%M:%S')} {message}"
    print(line, flush=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def start_actions():
    saved = sorted(f for f in os.listdir(out_dir) if f.startswith(level + "_") and f.endswith(".npy"))
    laps = joblib.load(os.path.join(ROOT, "linesight", "save", "all_levels_run1", "best_laps", f"{level}.joblib"))
    race_time, lap = min(laps, key=lambda x: x[0])
    actions = [int(a) for a in lap["actions"] if a == a]
    if saved:
        best_saved = min(saved, key=lambda f: int(f[len(level) + 1 : -4]))
        saved_time = int(best_saved[len(level) + 1 : -4])
        if saved_time < race_time:
            return np.load(os.path.join(out_dir, best_saved)).tolist(), saved_time
    return actions, race_time


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
    if not isinstance(raw, bytes):
        return raw
    state = SimStateData(raw)
    state.cp_data.resize(CheckpointData.cp_states_field, state.cp_data.cp_states_length)
    state.cp_data.resize(CheckpointData.cp_times_field, state.cp_data.cp_times_length)
    return state


def mutate(actions):
    new = list(actions)
    start = random.randrange(0, len(actions) - 1)
    width = random.choice([1, 1, 2, 3, 4, 6, 10, 16])
    end = min(len(actions), start + width)
    changed = False
    while not changed:
        for k in range(start, end):
            if random.random() < 0.5:
                a = random.randrange(len(inputs))
                if a != new[k]:
                    new[k] = a
                    changed = True
    return new, start


def main():
    actions, best = start_actions()
    log(f"start {level} from {best} ms, {len(actions)} actions, {minutes} min")
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

    states = {}
    trial = actions
    trial_start = 0
    trial_states = {}
    checking = True
    finish_target = None
    started = False
    tries = 0
    wins = 0
    end_time = time.time() + minutes * 60
    last_report = time.time()

    def next_trial(it):
        nonlocal trial, trial_start, trial_states, tries
        tries += 1
        trial, trial_start = mutate(actions)
        trial_states = {}
        it.rewind_to_state(full_state(states[trial_start]))
        it.set_input_state(**inputs[trial[trial_start]])

    try:
        while time.time() < end_time:
            msgtype = iface._read_int32()
            if msgtype == int(MessageType.SC_RUN_STEP_SYNC):
                now = iface._read_int32()
                if not started:
                    if now == 0:
                        connected.set()
                        started = True
                        iface.set_timeout(config_copy.timeout_during_run_ms)
                        iface.set_speed(SPEED)
                        states[0] = iface.get_simulation_state()
                        iface.rewind_to_current_state()
                        iface.set_input_state(**inputs[trial[0]])
                        log("race started, checking the saved lap replays exactly")
                elif now >= 0 and now % 50 == 0:
                    k = now // 50
                    if now > best or k >= len(trial):
                        if checking:
                            log(f"saved lap did not finish by {now} ms, replay is not exact, stopping")
                            return
                        next_trial(iface)
                    else:
                        if k > trial_start:
                            trial_states[k] = raw_state(iface)
                            if trial[k] != trial[k - 1]:
                                iface.rewind_to_current_state()
                                iface.set_input_state(**inputs[trial[k]])
                iface._respond_to_call(msgtype)
            elif msgtype == int(MessageType.SC_CHECKPOINT_COUNT_CHANGED_SYNC):
                current = iface._read_int32()
                target = iface._read_int32()
                if started and current == target and (checking or target == finish_target):
                    race_time = iface.get_simulation_state().race_time
                    if not checking and race_time < best * 0.97:
                        log(f"ignored a false finish at {race_time} ms ({current}/{target})")
                    elif checking:
                        checking = False
                        finish_target = target
                        states.update(trial_states)
                        log(f"saved lap replayed in {race_time} ms (expected {best})")
                        if race_time != best:
                            log("replay is not exact, stopping")
                            return
                    elif race_time < best:
                        wins += 1
                        actions = trial
                        best = race_time
                        for k in list(states):
                            if k > trial_start:
                                del states[k]
                        states.update(trial_states)
                        np.save(os.path.join(out_dir, f"{level}_{best}.npy"), np.array(actions))
                        os.makedirs(os.path.join(out_dir, "feed"), exist_ok=True)
                        np.save(os.path.join(out_dir, "feed", f"{level}_new.npy"), np.array(actions))
                        os.replace(os.path.join(out_dir, "feed", f"{level}_new.npy"), os.path.join(out_dir, "feed", f"{level}.npy"))
                        log(f"NEW {best} ms after {tries} tries (changed from step {trial_start})")
                    next_trial(iface)
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
            if time.time() - last_report > 600:
                last_report = time.time()
                log(f"{tries} tries, {wins} improvements, best {best} ms")
    except (socket.timeout, ConnectionError) as e:
        log(f"connection lost: {e}")
    finally:
        log(f"done: {tries} tries, {wins} improvements, best {best} ms")
        try:
            iface.close()
        except OSError:
            pass
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


if __name__ == "__main__":
    main()
