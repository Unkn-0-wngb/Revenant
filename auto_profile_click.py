"""Gets newly launched games past the profile screen, so training carries on after the 12 hour game restarts."""
import os
import re
import subprocess
import sys
import time

import psutil

import paths
import system

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "logs", "auto_click.log")
TRAIN_LOG = os.path.join(ROOT, "logs", "train_run1.log")
POLL_S = 5
WAIT_AFTER_LAUNCH_S = 25
CLICK_EVERY_S = 8
GIVE_UP_S = 300
POSTED_ATTEMPTS = 3
PROFILE_X = 320
FIRST_ROW_Y = 148
ROW_SPACING = 57
PROFILES = paths.PROFILES
USER_CONFIG = os.path.join(ROOT, "linesight", "config_files", "user_config.py")
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
VK_MENU = 0x12
KEYUP = 2
MOUSE_DOWN = 2
MOUSE_UP = 4


def write_log(message):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%d/%m %H:%M:%S')} {message}\n")


def base_port():
    try:
        with open(USER_CONFIG, encoding="utf-8") as f:
            return int(re.search(r"^base_tmi_port = (\d+)", f.read(), re.M).group(1))
    except (OSError, AttributeError):
        return None


def training_port(cmdline):
    match = re.search(r"custom_port (\d+)", " ".join(cmdline or []))
    base = base_port()
    if not match or base is None:
        return True
    return base <= int(match.group(1)) < base + paths.HELPER_PORT_OFFSET


def game_pids():
    pids = set()
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower() == "tmforever.exe" and training_port(p.info["cmdline"]):
                pids.add(p.pid)
        except psutil.Error:
            pass
    return pids


def training_alive():
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if "python" in (p.info["name"] or "").lower() and "train.py" in " ".join(p.info["cmdline"] or []):
                return True
        except psutil.Error:
            pass
    return False


def map_loads():
    try:
        with open(TRAIN_LOG, "rb") as f:
            return f.read().count(b"Requested map load")
    except OSError:
        return 0


def profile_y():
    try:
        with open(USER_CONFIG, encoding="utf-8") as f:
            wanted = re.search(r'^username = "([^"]*)"', f.read(), re.M).group(1)
        names = sorted((n[: -len(".Profile.Gbx")] for n in os.listdir(PROFILES) if n.endswith(".Profile.Gbx")), key=str.lower, reverse=True)
        return FIRST_ROW_Y + names.index(wanted) * ROW_SPACING
    except (OSError, AttributeError, ValueError):
        return FIRST_ROW_Y


if system.IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
    user32.VkKeyScanW.restype = ctypes.c_short
    window_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def window_of(pid):
        found = []

        def check(hwnd, _):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                found.append(hwnd)
            return True

        user32.EnumWindows(window_callback(check), 0)
        return found[0] if found else None

    def posted_click(hwnd):
        position = (profile_y() << 16) | PROFILE_X
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, position)
        time.sleep(0.2)
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, position)
        time.sleep(0.12)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, position)

    def bring_forward(hwnd):
        user32.keybd_event(VK_MENU, 0, 0, None)
        user32.keybd_event(VK_MENU, 0, KEYUP, None)
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.4)

    def toggle_console(hwnd):
        bring_forward(hwnd)
        key = user32.VkKeyScanW("`") & 0xFF
        scan = user32.MapVirtualKeyW(key, 0)
        user32.keybd_event(key, scan, 0, None)
        time.sleep(0.12)
        user32.keybd_event(key, scan, KEYUP, None)
        time.sleep(0.6)

    def real_click(hwnd):
        bring_forward(hwnd)
        point = wintypes.POINT(PROFILE_X, profile_y())
        user32.ClientToScreen(hwnd, ctypes.byref(point))
        before = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(before))
        user32.SetCursorPos(point.x, point.y)
        time.sleep(0.3)
        user32.mouse_event(MOUSE_DOWN, 0, 0, 0, None)
        time.sleep(0.12)
        user32.mouse_event(MOUSE_UP, 0, 0, 0, None)
        time.sleep(0.3)
        user32.SetCursorPos(before.x, before.y)

    def screen_size():
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

    def move_window(hwnd, x, y, width, height):
        user32.MoveWindow(hwnd, x, y, width, height, True)

    def minimize_training_terminal():
        found = []

        def check(hwnd, _):
            title = ctypes.create_unicode_buffer(300)
            kind = ctypes.create_unicode_buffer(100)
            user32.GetWindowTextW(hwnd, title, 300)
            user32.GetClassNameW(hwnd, kind, 100)
            if user32.IsWindowVisible(hwnd) and kind.value == "CASCADIA_HOSTING_WINDOW_CLASS" and title.value.lower().endswith("powershell.exe"):
                found.append(hwnd)
            return True

        user32.EnumWindows(window_callback(check), 0)
        for hwnd in found:
            user32.ShowWindow(hwnd, 6)
        write_log(f"minimized {len(found)} terminal windows")

else:

    def xdotool(*args):
        try:
            return subprocess.run(["xdotool", *[str(a) for a in args]], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def window_of(pid):
        found = xdotool("search", "--onlyvisible", "--pid", pid, "--name", ".").split()
        return found[0] if found else None

    def posted_click(window):
        xdotool("mousemove", "--window", window, PROFILE_X, profile_y(), "click", "--window", window, 1)

    def bring_forward(window):
        xdotool("windowmap", window)
        xdotool("windowactivate", "--sync", window)
        time.sleep(0.4)

    def toggle_console(window):
        bring_forward(window)
        xdotool("key", "--window", window, "grave")
        time.sleep(0.6)

    def real_click(window):
        bring_forward(window)
        xdotool("mousemove", "--window", window, PROFILE_X, profile_y(), "click", 1, "mousemove", "restore")

    def screen_size():
        size = xdotool("getdisplaygeometry").split()
        return (int(size[0]), int(size[1])) if len(size) == 2 else (1920, 1080)

    def move_window(window, x, y, width, height):
        xdotool("windowsize", window, width, height, "windowmove", window, x, y)

    def minimize_training_terminal():
        pass


def arrange_games():
    if os.path.exists(os.path.join(ROOT, "logs", "no_arrange")):
        write_log("left game windows at their own size (logs/no_arrange)")
        minimize_training_terminal()
        return
    width, height = (size // 2 for size in screen_size())
    for slot, pid in enumerate(sorted(game_pids())[:2]):
        window = window_of(pid)
        if window:
            move_window(window, slot * width, 0, width, height)
    write_log("arranged games side by side")
    minimize_training_terminal()


def try_game(pid, attempt):
    window = window_of(pid)
    if not window:
        return
    if attempt < POSTED_ATTEMPTS:
        posted_click(window)
        write_log(f"game {pid}: posted click {attempt + 1}")
        return
    if (attempt - POSTED_ATTEMPTS) % 3 == 0:
        toggle_console(window)
        write_log(f"game {pid}: toggled console")
    real_click(window)
    write_log(f"game {pid}: real click, attempt {attempt + 1}")


def main():
    known = game_pids()
    pending = {}
    loads_needed = 0
    missing_training = 0
    write_log(f"started, leaving existing games alone: {sorted(known)}")
    while True:
        now = time.time()
        pids = game_pids()
        new = pids - known
        if new:
            if not pending:
                loads_needed = map_loads()
            loads_needed += len(new)
            for pid in new:
                pending[pid] = {"seen": now, "attempt": 0, "last": 0}
                write_log(f"new game {pid}")
        known = pids
        if pending and map_loads() >= loads_needed:
            write_log(f"maps loaded, finished with {sorted(pending)}")
            pending.clear()
            time.sleep(3)
            arrange_games()
        for pid, game in list(pending.items()):
            if pid not in pids or now - game["seen"] > GIVE_UP_S:
                pending.pop(pid)
                write_log(f"gave up on game {pid}")
            elif now - game["seen"] >= WAIT_AFTER_LAUNCH_S and now - game["last"] >= CLICK_EVERY_S:
                try_game(pid, game["attempt"])
                game["attempt"] += 1
                game["last"] = time.time()
        missing_training = 0 if training_alive() else missing_training + 1
        if missing_training * POLL_S >= 600:
            write_log("training has been gone for 10 minutes, stopping")
            return
        time.sleep(POLL_S)


if __name__ == "__main__":
    if "--list" in sys.argv:
        for pid in sorted(game_pids()):
            print(pid, "window", window_of(pid))
    else:
        main()
