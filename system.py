import os
import shutil
import subprocess
import sys
import time
import webbrowser

import psutil

IS_WINDOWS = sys.platform == "win32"
ROOT = os.path.dirname(os.path.abspath(__file__))
LAUNCH_SCRIPT = os.path.join(ROOT, "launch_game.sh")


def open_path(path):
    if IS_WINDOWS:
        os.startfile(path)
    elif path.startswith(("http://", "https://", "steam://")):
        webbrowser.open(path)
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def launch(args, hidden=True, cwd=ROOT):
    if IS_WINDOWS:
        flags = 0x00000008 | 0x00000200 | 0x08000000 if hidden else 0x00000010
        return subprocess.Popen(args, cwd=cwd, creationflags=flags, close_fds=True)
    if not hidden:
        for terminal, flag in (("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"), ("xterm", "-e")):
            if shutil.which(terminal):
                args = [terminal, flag] + args
                break
    return subprocess.Popen(args, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)


def run_quietly(args, **kwargs):
    if IS_WINDOWS:
        kwargs.setdefault("creationflags", 0x08000000)
    return subprocess.run(args, **kwargs)


def commit_free_gb():
    if IS_WINDOWS:
        import ctypes
        from ctypes import wintypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.DWORD),
                ("load", wintypes.DWORD),
                ("total_phys", ctypes.c_ulonglong),
                ("avail_phys", ctypes.c_ulonglong),
                ("total_commit", ctypes.c_ulonglong),
                ("avail_commit", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return status.avail_commit / 2**30
    return (psutil.virtual_memory().available + psutil.swap_memory().free) / 2**30


def read_shared(path):
    if not IS_WINDOWS:
        with open(path, "rb") as f:
            return f.read()
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    handle = kernel32.CreateFileW(path, 0x80000000, 7, None, 3, 0, None)
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error())
    with os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY), "rb") as f:
        return f.read()


def sharp_text():
    if IS_WINDOWS:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def game_pids():
    found = set()
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info["name"] or "").lower() == "tmforever.exe":
                found.add(p.pid)
        except psutil.Error:
            pass
    return found


def start_game(loader, profile, port, timeout_s=90):
    if IS_WINDOWS:
        command = (
            'powershell -executionPolicy bypass -command "& {'
            f" $process = start-process -FilePath '{loader}'"
            " -PassThru -ArgumentList "
            f'\'run TmForever "{profile}" /configstring=\\"set custom_port {port}\\"\';'
            ' echo exit $process.id}"'
        )
        launcher = int(subprocess.check_output(command, cwd=os.path.dirname(loader)).decode().split("\r\n")[1])
        end = time.time() + timeout_s
        while time.time() < end:
            for p in psutil.process_iter(["name", "ppid"]):
                try:
                    if (p.info["name"] or "").lower() == "tmforever.exe" and p.info["ppid"] == launcher:
                        return p.pid
                except psutil.Error:
                    pass
            time.sleep(1)
        raise RuntimeError("the game didn't start")
    before = game_pids()
    subprocess.Popen([LAUNCH_SCRIPT, str(port), profile], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    end = time.time() + timeout_s
    while time.time() < end:
        new = game_pids() - before
        if new:
            return min(new)
        time.sleep(1)
    raise RuntimeError("the game didn't start, check that launch_game.sh works on its own")


def kill_tree(pid):
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.Error:
        pass
