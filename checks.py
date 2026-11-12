import filecmp
import glob
import importlib.util
import os
import re
import shutil
import socket
import subprocess
import webbrowser
import zipfile

import controls
import machine
import paths

SAVE = os.path.join(paths.LINESIGHT, "save")
RUN = os.path.join(SAVE, "all_levels_run1")
MODELS = os.path.join(paths.ROOT, "models")
PACKAGES = ("torch", "torchrl", "tminterface", "lzo", "pygbx", "cv2", "scipy", "matplotlib", "psutil", "joblib")


def check_packages():
    missing = [p for p in PACKAGES if importlib.util.find_spec(p) is None]
    return not missing, "installed" if not missing else "missing: " + ", ".join(missing)


def fix_packages():
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(paths.ROOT, "setup.ps1")], cwd=paths.ROOT, creationflags=0x00000010)
    return "Setup is running in its own window. Reopen the dashboard when it finishes."


def check_gpu():
    result = machine.load()
    if result and result.get("benchmark"):
        bench = result["benchmark"]
        return bench.get("cuda", False), bench.get("gpu", "") if bench.get("cuda") else "the GPU can't run the AI (no CUDA)"
    gpu = machine.gpu_from_nvidia_smi()
    if not gpu:
        return False, "no NVIDIA GPU found"
    return True, f"{gpu['name']}, {gpu['vram_gb']} GB (not benchmarked yet)"


def fix_gpu():
    webbrowser.open("https://www.nvidia.com/Download/index.aspx")
    return "Opened NVIDIA's driver page. Revenant needs an NVIDIA card with CUDA."


def check_game():
    folder = paths.game_folder()
    return bool(folder), "installed" if folder else "not installed"


def fix_game():
    os.startfile(paths.STEAM_GAME_PAGE)
    return "Asked Steam to install TrackMania Nations Forever (it's free). Check again when it's done."


def check_tmloader():
    return os.path.exists(paths.TMLOADER_EXE), "installed" if os.path.exists(paths.TMLOADER_EXE) else "not installed"


def fix_tmloader():
    webbrowser.open(paths.TMLOADER_PAGE)
    return "Opened the TMLoader page. Install it to the default folder, then check again."


def tmloader_game_setting():
    if not os.path.exists(paths.TMLOADER_GAME):
        return None
    with open(paths.TMLOADER_GAME, encoding="utf-8") as f:
        found = re.search(r"install:\s*'(.*)'", f.read())
    return found.group(1).replace("''", "'") if found else None


def check_tmloader_game():
    folder = tmloader_game_setting()
    ok = bool(folder) and os.path.exists(os.path.join(folder, "TmForever.exe"))
    return ok, "set up" if ok else "doesn't know where the game is"


def fix_tmloader_game():
    folder = paths.game_folder()
    if not folder:
        return "Install the game first."
    os.makedirs(os.path.dirname(paths.TMLOADER_GAME), exist_ok=True)
    with open(paths.TMLOADER_GAME, "w", encoding="utf-8") as f:
        f.write("install: '" + folder.replace("'", "''") + "'\n")
    return f"Pointed TMLoader at {folder}."


def check_tmloader_profile():
    if not os.path.exists(paths.TMLOADER_PROFILE):
        return False, "no default profile"
    with open(paths.TMLOADER_PROFILE, encoding="utf-8") as f:
        ok = "TMInterface" in f.read()
    return ok, "loads TMInterface" if ok else "the default profile doesn't load TMInterface"


def fix_tmloader_profile():
    os.makedirs(os.path.dirname(paths.TMLOADER_PROFILE), exist_ok=True)
    text = ""
    if os.path.exists(paths.TMLOADER_PROFILE):
        with open(paths.TMLOADER_PROFILE, encoding="utf-8") as f:
            text = f.read()
    if re.search(r"^mods:\s*$", text, re.M):
        text = re.sub(r"^mods:\s*$", "mods:\n  - id: TMInterface", text, count=1, flags=re.M)
        said = "Added TMInterface to your default TMLoader profile."
    else:
        text = "program:\n  id: TmForever\nmods:\n  - id: TMInterface\n"
        said = "Made a TMLoader profile called default that loads TMInterface."
    with open(paths.TMLOADER_PROFILE, "w", encoding="utf-8") as f:
        f.write(text)
    return said + " TMLoader downloads it the first time the game starts."


def check_plugin():
    source = os.path.join(paths.ROOT, "tmi", "Python_Link.as")
    ok = os.path.exists(paths.TMI_PLUGIN) and filecmp.cmp(source, paths.TMI_PLUGIN, shallow=False)
    return ok, "installed" if ok else "missing or out of date"


def fix_plugin():
    os.makedirs(os.path.dirname(paths.TMI_PLUGIN), exist_ok=True)
    shutil.copyfile(os.path.join(paths.ROOT, "tmi", "Python_Link.as"), paths.TMI_PLUGIN)
    if not os.path.exists(paths.TMI_BUILTIN):
        shutil.copyfile(os.path.join(paths.ROOT, "tmi", "builtin.txt"), paths.TMI_BUILTIN)
    return "Installed the TMInterface plugin and settings."


def check_maps():
    needed = [short for short, _ in controls.levels()]
    missing = [short for short in needed if not glob.glob(os.path.join(paths.OFFICIAL_MAPS, f"{short}-*.Challenge.Gbx"))]
    if missing:
        return False, f"{len(needed) - len(missing)} of {len(needed)}, missing {', '.join(missing[:4])}{'...' if len(missing) > 4 else ''}"
    return True, f"all {len(needed)} levels"


def fix_maps():
    script = os.path.join(paths.LINESIGHT, "scripts", "tools", "get_official_maps.py")
    subprocess.Popen([paths.VENV_PYTHON, script], cwd=paths.LINESIGHT, creationflags=0x00000010)
    return "Downloading the official maps in a separate window."


def check_models():
    installed = os.path.exists(os.path.join(RUN, "weights1.torch"))
    levels = len(glob.glob(os.path.join(RUN, "levels", "*", "weights1.torch")))
    zips = glob.glob(os.path.join(MODELS, "*.zip"))
    if installed:
        return True, f"pretrained: main brain and {levels} level brains"
    if zips:
        return False, f"{len(zips)} pretrained zips ready to install"
    return True, "none, starting fresh (pretrained ones are on Releases)"


def install_models(folder=MODELS):
    zips = sorted(glob.glob(os.path.join(folder, "*.zip")))
    if not zips:
        return f"No pretrained zips in {folder}. Download them from the Releases page into that folder."
    os.makedirs(SAVE, exist_ok=True)
    for z in zips:
        with zipfile.ZipFile(z) as archive:
            names = archive.namelist()
            target = SAVE if names and names[0].startswith("all_levels_run1/") else paths.ROOT
            archive.extractall(target)
    return f"Installed {len(zips)} pretrained zips."


def fix_models():
    return install_models()


def check_profile():
    name = controls.AI_PROFILE
    made = name in controls.profiles()
    used = controls.profile() == name
    skin = os.path.exists(os.path.join(paths.SKINS, "Vehicles", "StadiumCar", "Revenant.zip"))
    ok = made and used and skin
    return ok, "made, dressed and in use" if ok else f"{'made' if made else 'not made'}, {'in use' if used else 'not in use'}, {'skin installed' if skin else 'no skin'}"


def fix_profile():
    if controls.game_count():
        return "Close Trackmania first."
    return controls.use_ai_profile()


def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def current_port():
    with open(controls.USER_CONFIG, encoding="utf-8") as f:
        return int(re.search(r"^base_tmi_port = (\d+)", f.read(), re.M).group(1))


def check_ports():
    if controls.training_running() or controls.game_count():
        return True, "in use by Revenant"
    base = current_port()
    busy = [p for p in range(base, base + 3) if not port_free(p)]
    return not busy, f"{base} to {base + 2} free" if not busy else f"port {busy[0]} is taken by another program"


def fix_ports():
    for base in range(8478, 9400, 10):
        if all(port_free(p) for p in range(base, base + 3)):
            text = controls.read_text(controls.USER_CONFIG)
            controls.write_text(controls.USER_CONFIG, re.sub(r"^base_tmi_port = \d+", f"base_tmi_port = {base}", text, flags=re.M))
            return f"Moved Revenant to ports {base} to {base + 2}."
    return "Couldn't find free ports."


def check_benchmark():
    result = machine.load()
    if not result:
        return False, "not run on this PC yet"
    return bool(result.get("benchmark")), f"run {result['when']}" if result.get("benchmark") else f"failed: {result.get('error')}"


def fix_benchmark():
    return "Open the Machine tab and press Benchmark."


def check_config_copy():
    return os.path.exists(machine.CONFIG_COPY), "ready" if os.path.exists(machine.CONFIG_COPY) else "missing"


def fix_config_copy():
    machine.make_config_copy()
    return "Made config_copy.py."


CHECKS = [
    ("Python packages", check_packages, fix_packages, "Run setup"),
    ("NVIDIA graphics card", check_gpu, fix_gpu, "Drivers"),
    ("TrackMania Nations Forever", check_game, fix_game, "Install"),
    ("TMLoader", check_tmloader, fix_tmloader, "Get it"),
    ("TMLoader knows the game", check_tmloader_game, fix_tmloader_game, "Fix"),
    ("TMLoader profile with TMInterface", check_tmloader_profile, fix_tmloader_profile, "Fix"),
    ("TMInterface plugin", check_plugin, fix_plugin, "Install"),
    ("Official maps", check_maps, fix_maps, "Download"),
    ("Trained models", check_models, fix_models, "Install"),
    ("Revenant profile", check_profile, fix_profile, "Make"),
    ("Network ports", check_ports, fix_ports, "Fix"),
    ("Settings file", check_config_copy, fix_config_copy, "Fix"),
    ("Benchmark for this PC", check_benchmark, fix_benchmark, "How"),
]


def run_all():
    results = []
    for name, check, fix, label in CHECKS:
        try:
            ok, detail = check()
        except Exception as e:
            ok, detail = False, f"check failed: {e}"
        results.append((name, ok, detail, fix, label))
    return results


def fix_everything():
    said = []
    for name, ok, detail, fix, label in run_all():
        if not ok and fix in (fix_tmloader_game, fix_tmloader_profile, fix_plugin, fix_config_copy, fix_ports, fix_profile, fix_models):
            said.append(fix())
    return " ".join(said) or "Nothing could be fixed automatically."


if __name__ == "__main__":
    for name, ok, detail, _, _ in run_all():
        print(("OK  " if ok else "FIX ") + f"{name}: {detail}")
