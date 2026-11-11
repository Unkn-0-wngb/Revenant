"""Plays a saved 50 ms action list on a third game and records the game's own frames into a video with the keys shown,
and writes the same lap as a TMInterface .inputs file.
Usage: render_lap.py D02 bruteforce/D02_follow_51230.npy out_folder"""
import os
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
import psutil

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "linesight"))
from config_files import config_copy, user_config
from trackmania_rl.tmi_interaction.tminterface2 import MessageType, TMInterface

import auto_profile_click

PORT = user_config.base_tmi_port + 2
SPEED = 20
W, H = 960, 720
BAR = 90
FPS = 20

level = sys.argv[1]
lap = [int(a) for a in np.load(sys.argv[2])]
out_dir = sys.argv[3]
map_path = next(e[1] for e in config_copy.levels if e[0] == level).replace("/", "\\")
inputs = config_copy.inputs
forward = config_copy.action_forward_idx
font = cv2.FONT_HERSHEY_SIMPLEX


def write_inputs(path):
    keys = [("up", "accelerate"), ("down", "brake"), ("left", "left"), ("right", "right")]
    rows = []
    for name, field in keys:
        start = None
        for step in range(len(lap) + 1):
            on = step < len(lap) and inputs[lap[step]][field]
            if on and start is None:
                start = step
            elif not on and start is not None:
                rows.append((start, f"{start * 0.05:g}-{step * 0.05:g} press {name}"))
                start = None
    rows.sort(key=lambda r: r[0])
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(r[1] for r in rows) + "\n")


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


def key(img, label, x, on):
    colour = (80, 200, 80) if on else (60, 60, 60)
    cv2.rectangle(img, (x, H + 20), (x + 70, H + 70), colour, -1)
    cv2.putText(img, label, (x + 12, H + 54), font, 0.8, (255, 255, 255), 2)


def picture(frame, step, final_ms):
    img = np.zeros((H + BAR, W, 3), np.uint8)
    img[:H] = frame[:, :, :3]
    t = step * 50 / 1000 if final_ms is None else final_ms / 1000
    cv2.putText(img, f"{level}  {t:6.2f}s", (20, 50), font, 1.3, (0, 0, 0), 6)
    cv2.putText(img, f"{level}  {t:6.2f}s", (20, 50), font, 1.3, (255, 255, 255), 2)
    action = inputs[lap[step]] if step < len(lap) else inputs[forward]
    key(img, "<", 20, action["left"])
    key(img, "^", 100, action["accelerate"])
    key(img, "v", 180, action["brake"])
    key(img, ">", 260, action["right"])
    cv2.putText(img, "AI actions, followed from the record line", (360, H + 54), font, 0.7, (200, 200, 200), 2)
    return img


def main():
    os.makedirs(out_dir, exist_ok=True)
    pid = launch_game()
    connected = threading.Event()
    threading.Thread(target=click_profile, args=(pid, connected), daemon=True).start()
    iface = TMInterface(PORT)
    while True:
        try:
            iface.register(config_copy.tmi_protection_timeout_s)
            break
        except ConnectionRefusedError:
            time.sleep(1)

    raw = os.path.join(out_dir, f"{level}_raw.avi")
    writer = cv2.VideoWriter(raw, cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H + BAR))
    started = False
    step = 0
    finish_ms = None
    last = None
    written = -1
    try:
        while finish_ms is None:
            msgtype = iface._read_int32()
            if msgtype == int(MessageType.SC_RUN_STEP_SYNC):
                now = iface._read_int32()
                if not started and now == 0:
                    connected.set()
                    started = True
                    iface.set_timeout(config_copy.timeout_during_run_ms)
                    iface.toggle_interface(False)
                    iface.rewind_to_current_state()
                    iface.set_input_state(**inputs[lap[0]])
                    iface.set_speed(0)
                    iface.request_frame(W, H)
                elif started and now > 0 and now % 50 == 0:
                    step = now // 50
                    if step > len(lap) + 60:
                        break
                    a = lap[step] if step < len(lap) else forward
                    b = lap[step - 1] if step - 1 < len(lap) else forward
                    if a != b:
                        iface.rewind_to_current_state()
                        iface.set_input_state(**inputs[a])
                    iface.set_speed(0)
                    iface.request_frame(W, H)
                iface._respond_to_call(msgtype)
            elif msgtype == int(MessageType.SC_REQUESTED_FRAME_SYNC):
                frame = iface.get_frame(W, H)
                last = frame
                for _ in range(max(1, step - written)):
                    writer.write(picture(frame, step, None))
                written = step
                iface.set_speed(SPEED)
                iface._respond_to_call(msgtype)
            elif msgtype == int(MessageType.SC_CHECKPOINT_COUNT_CHANGED_SYNC):
                current = iface._read_int32()
                target = iface._read_int32()
                if started and current == target:
                    finish_ms = iface.get_simulation_state().race_time
                iface._respond_to_call(msgtype)
            elif msgtype == int(MessageType.SC_LAP_COUNT_CHANGED_SYNC):
                iface._read_int32()
                iface._read_int32()
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
                iface._respond_to_call(msgtype)
            else:
                iface._respond_to_call(msgtype)
        if last is not None:
            for _ in range(FPS * 2):
                writer.write(picture(last, step, finish_ms))
    finally:
        writer.release()
        try:
            iface.close()
        except OSError:
            pass
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)

    name = f"{level}_{finish_ms / 1000:.2f}" if finish_ms else f"{level}_unfinished"
    video = os.path.join(out_dir, name + ".mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", video], check=True)
    os.remove(raw)
    write_inputs(os.path.join(out_dir, name + ".inputs"))
    print(video, finish_ms)


if __name__ == "__main__":
    main()
