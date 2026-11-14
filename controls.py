import ast
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import uuid

import lzo
import psutil

import paths

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(ROOT, "linesight", "config_files")
CONFIG = os.path.join(CONFIG_DIR, "config.py")
CONFIG_COPY = os.path.join(CONFIG_DIR, "config_copy.py")
USER_CONFIG = os.path.join(CONFIG_DIR, "user_config.py")
ART = os.path.join(ROOT, "art")
WEIGHTS = os.path.join(ROOT, "linesight", "save", "all_levels_run1", "weights1.torch")
PYTHON = paths.VENV_PYTHON
PYTHONW = paths.VENV_PYTHONW
BUILTIN = paths.TMI_BUILTIN
PROFILES = paths.PROFILES
DETACHED = 0x00000008 | 0x00000200 | 0x08000000
AI_PROFILE = "Revenant"
KEYBOARD_ID = b"6f1d2b61-d5a0-11cf-bfc7-444553540000"

TRAINING = ("train.ps1", "scripts\\train.py", "multiprocessing.spawn")
HELPERS = {
    "demo starts": "refeed.py",
    "lap follower": "follow_line.py",
    "bruteforce": "bruteforce.py",
    "clicker": "auto_profile_click.py",
}


def processes(*patterns):
    found = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            line = " ".join(p.info["cmdline"] or [])
            if any(pattern in line for pattern in patterns) and "dashboard.py" not in line:
                found.append(p)
        except psutil.Error:
            pass
    return found


def game_count():
    count = 0
    for p in psutil.process_iter(["name"]):
        try:
            count += (p.info["name"] or "").lower() == "tmforever.exe"
        except psutil.Error:
            pass
    return count


def training_running():
    return bool(processes("scripts\\train.py", "scripts/train.py"))


def helper_running(name):
    return bool(processes(HELPERS[name]))


def kill(found):
    for p in found:
        try:
            p.kill()
        except psutil.Error:
            pass


def close_games():
    for _ in range(3):
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info["name"] or "").lower() in ("tmforever.exe", "tmloader.exe"):
                    p.kill()
            except psutil.Error:
                pass
        time.sleep(2)


def launch(args, hidden=True):
    flags = DETACHED if hidden else 0x00000010
    subprocess.Popen(args, cwd=ROOT, creationflags=flags, close_fds=True)


def start_training():
    if training_running():
        return "Training is already running."
    if game_count():
        return "Close Trackmania first: training would force-close it."
    if profile() != AI_PROFILE:
        use_ai_profile()
    if not helper_running("clicker"):
        launch([PYTHONW, os.path.join(ROOT, "auto_profile_click.py")])
    launch(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Minimized", "-File", os.path.join(ROOT, "train.ps1")], hidden=False)
    return "Training is starting. The games take about a minute to load."


def wait_for_save(limit_s=480):
    if not os.path.exists(WEIGHTS):
        return False
    before = os.path.getmtime(WEIGHTS)
    end = time.time() + limit_s
    while time.time() < end:
        if os.path.getmtime(WEIGHTS) > before:
            time.sleep(5)
            return True
        if not training_running():
            return False
        time.sleep(2)
    return False


def stop_training(report, wait=True):
    def run():
        saved = False
        if wait and training_running():
            report("Waiting for the next save before stopping (up to 8 minutes)...")
            saved = wait_for_save()
        kill(processes(*TRAINING))
        for name in ("demo starts", "lap follower", "bruteforce", "clicker"):
            kill(processes(HELPERS[name]))
        close_games()
        report(f"Training stopped{' right after a save' if saved else ''}.")

    threading.Thread(target=run, daemon=True).start()


def start_helper(name, *args):
    if helper_running(name):
        return f"The {name} are already running." if name.endswith("s") else f"The {name} is already running."
    script = os.path.join(ROOT, HELPERS[name])
    launch([PYTHON, script, *[str(a) for a in args]])
    return f"Started the {name}."


def stop_helper(name):
    found = processes(HELPERS[name])
    kill(found)
    if name in ("lap follower", "bruteforce") and found:
        games = sorted((p for p in psutil.process_iter(["name", "create_time"]) if (p.info["name"] or "").lower() == "tmforever.exe"), key=lambda p: p.info["create_time"])
        keep = current("gpu_collectors_count") or 2 if training_running() else 0
        kill(games[keep:])
    return f"Stopped the {name}." if found else f"The {name} {'were' if name.endswith('s') else 'was'} not running."


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def settings():
    text = read_text(CONFIG)
    lines = text.splitlines()
    found = []
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            source = ast.get_source_segment(text, node.value)
            try:
                ast.literal_eval(node.value)
            except (ValueError, SyntaxError, TypeError):
                continue
            note = ""
            last = lines[node.end_lineno - 1]
            if "#" in last[node.end_col_offset :]:
                note = last[node.end_col_offset :].split("#", 1)[1].strip()
            found.append({"name": node.targets[0].id, "value": source, "note": note})
    return found


def current(name):
    for setting in settings():
        if setting["name"] == name:
            return ast.literal_eval(setting["value"])
    return None


def char_index(lines, lineno, col):
    before = sum(len(line) for line in lines[: lineno - 1])
    return before + len(lines[lineno - 1].encode("utf-8")[:col].decode("utf-8"))


def set_setting(name, new_value):
    try:
        value = ast.literal_eval(new_value)
    except (ValueError, SyntaxError) as e:
        if not isinstance(current(name), str):
            return f"{name} was not changed: {new_value!r} is not a valid value ({e})."
        value = new_value
    text = read_text(CONFIG)
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            lines = text.splitlines(keepends=True)
            start = char_index(lines, node.value.lineno, node.value.col_offset)
            end = char_index(lines, node.value.end_lineno, node.value.end_col_offset)
            text = text[:start] + repr(value) + text[end:]
            write_text(CONFIG, text)
            write_text(CONFIG_COPY, text)
            return f"{name} set to {value!r}."
    return f"There is no setting called {name}."


def levels():
    sys.path.insert(0, os.path.join(ROOT, "linesight"))
    from config_files.all_maps import all_maps
    from config_files.author_times import author_times

    return [(short, author_times.get(short)) for short, *_ in all_maps]


def focus():
    return current("focus_level") or "", current("focus_target_s")


def best_time(level):
    path = os.path.join(os.path.dirname(WEIGHTS), "accumulated_stats.joblib")
    if not os.path.exists(path):
        return None
    import joblib

    ms = joblib.load(path).get("alltime_min_ms", {}).get(level)
    return ms / 1000 if ms and ms < 300000 else None


def set_focus(level, target):
    best = best_time(level)
    if best is not None and float(target) >= best:
        return f"{level}'s best is already {best:.2f} s, so a {float(target):.2f} s target would end the focus straight away. Pick a target under {best:.2f}."
    first = set_setting("focus_target_s", repr(float(target)))
    if "set to" not in first:
        return first
    return set_setting("focus_level", repr(level))


def profile():
    match = re.search(r'^username = "([^"]*)"', read_text(USER_CONFIG), re.M)
    return match.group(1) if match else ""


def profiles():
    if not os.path.isdir(PROFILES):
        return []
    return sorted(f[: -len(".Profile.Gbx")] for f in os.listdir(PROFILES) if f.endswith(".Profile.Gbx"))


def read_profile(path):
    with open(path, "rb") as f:
        data = f.read()
    head = 3 + 2 + 4 + 4
    user_size = struct.unpack_from("<I", data, head)[0]
    sizes_at = head + 4 + user_size + 8
    full_size, packed_size = struct.unpack_from("<II", data, sizes_at)
    body = lzo.decompress(data[sizes_at + 8 : sizes_at + 8 + packed_size], False, full_size)
    return data[:sizes_at], body


def make_profile(name=AI_PROFILE):
    target = os.path.join(PROFILES, f"{name}.Profile.Gbx")
    if os.path.exists(target):
        return f"The {name} profile already exists."
    others = [p for p in profiles() if p != name]
    if others:
        template = others[0]
        template_path = os.path.join(PROFILES, f"{template}.Profile.Gbx")
    else:
        template = AI_PROFILE
        template_path = os.path.join(ART, "Template.Profile.Gbx")
    os.makedirs(PROFILES, exist_ok=True)
    head, body = read_profile(template_path)
    old = struct.pack("<I", len(template)) + template.encode()
    new = struct.pack("<I", len(name)) + name.encode()
    body = body.replace(old, new)
    for found in set(re.findall(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", body)):
        if found != KEYBOARD_ID:
            body = body.replace(found, str(uuid.uuid4()).encode())
    packed = lzo.compress(body, 1, False)
    with open(target, "wb") as f:
        f.write(head + struct.pack("<II", len(body), len(packed)) + packed)
    return f"Made the {name} profile (settings copied from {template if others else 'the built-in template'})."


def swap_string(body, old, new):
    old_full = struct.pack("<I", len(old)) + old
    new_full = struct.pack("<I", len(new)) + new
    delta = len(new_full) - len(old_full)
    spots = []
    at = body.find(old_full)
    while at >= 0:
        spots.append(at)
        at = body.find(old_full, at + 1)
    body = bytearray(body)
    for at in reversed(spots):
        marker = body.find(b"PIKS")
        while marker >= 0:
            size = struct.unpack_from("<I", body, marker + 4)[0]
            if marker + 8 <= at < marker + 8 + size:
                struct.pack_into("<I", body, marker + 4, size + delta)
            marker = body.find(b"PIKS", marker + 1)
        body[at : at + len(old_full)] = new_full
    return bytes(body)


def dress_profile(name=AI_PROFILE):
    path = os.path.join(PROFILES, f"{name}.Profile.Gbx")
    if not os.path.exists(path):
        return f"There is no {name} profile to dress."
    if game_count():
        return "Close Trackmania first, it rewrites the profile when it quits."
    skins = paths.SKINS
    os.makedirs(os.path.join(skins, "Vehicles", "StadiumCar"), exist_ok=True)
    os.makedirs(os.path.join(skins, "Avatars"), exist_ok=True)
    shutil.copyfile(os.path.join(ART, "Revenant.zip"), os.path.join(skins, "Vehicles", "StadiumCar", "Revenant.zip"))
    shutil.copyfile(os.path.join(ART, "Revenant.dds"), os.path.join(skins, "Avatars", "Revenant.dds"))
    head, body = read_profile(path)
    for pattern, new in ((rb"Skins\\Vehicles\\StadiumCar\\[^\x00-\x1f]*?\.zip", rb"Skins\Vehicles\StadiumCar\Revenant.zip"), (rb"Skins\\Avatars\\[^\x00-\x1f]*?\.dds", rb"Skins\Avatars\Revenant.dds")):
        for old in set(re.findall(pattern, body)):
            if old != new:
                body = swap_string(body, old, new)
    car = rb"Skins\Vehicles\StadiumCar\Revenant.zip"
    at = body.find(struct.pack("<I", len(car)) + car)
    if at >= 0:
        start = at + 4 + len(car)
        with open(os.path.join(ART, "Revenant.zip"), "rb") as f:
            body = body[:start] + hashlib.md5(f.read()).digest() + b"\x01" + body[start + 17 :]
    packed = lzo.compress(body, 1, False)
    with open(path, "wb") as f:
        f.write(head + struct.pack("<II", len(body), len(packed)) + packed)
    return f"{name} now uses the Revenant car and logo."


def use_ai_profile():
    made = make_profile()
    dressed = dress_profile()
    used = set_profile(AI_PROFILE)
    return f"{made} {dressed} {used}"


def set_profile(name):
    if name not in profiles():
        return f"There is no {name} profile in Trackmania yet. Create it in the game first (Profiles, New)."
    text = re.sub(r'^username = "[^"]*"', f'username = "{name}"', read_text(USER_CONFIG), flags=re.M)
    write_text(USER_CONFIG, text)
    if os.path.exists(BUILTIN):
        builtin = re.sub(r'set "autologin" "[^"]*";', f'set "autologin" "{name}";', read_text(BUILTIN))
        write_text(BUILTIN, builtin)
    later = " Restart training to use it." if training_running() else ""
    return f"The AI now drives as {name}.{later}"


def status():
    return {
        "training": training_running(),
        "games": game_count(),
        "helpers": {name: helper_running(name) for name in HELPERS},
        "focus": focus(),
        "profile": profile(),
    }
