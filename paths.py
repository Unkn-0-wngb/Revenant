import ctypes
import os
import re
import uuid
import winreg
from ctypes import wintypes

ROOT = os.path.dirname(os.path.abspath(__file__))
LINESIGHT = os.path.join(ROOT, "linesight")
VENV_PYTHON = os.path.join(ROOT, "venv", "Scripts", "python.exe")
VENV_PYTHONW = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
GAME_FOLDER_NAME = "TrackMania Nations Forever"
HELPER_PORT_OFFSET = 7
FOLLOWER_PORT_OFFSET = 7
BRUTEFORCE_PORT_OFFSET = 8
BENCHMARK_PORT_OFFSET = 9
PORT_BLOCK = 10


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

    def __init__(self, text):
        super().__init__()
        raw = uuid.UUID(text).bytes_le
        ctypes.memmove(ctypes.byref(self), raw, 16)


def known_folder(folder_id):
    path = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    if shell32.SHGetKnownFolderPath(ctypes.byref(GUID(folder_id)), 0, None, ctypes.byref(path)) != 0:
        return None
    result = path.value
    ctypes.windll.ole32.CoTaskMemFree(path)
    return result


DOCUMENTS = known_folder("FDD39AD0-238F-46AF-ADB4-6C85480369C7") or os.path.join(os.path.expanduser("~"), "Documents")
LOCAL_APPDATA = known_folder("F1B32785-6FBA-4FCF-9D55-7B8E7F157091") or os.environ.get("LOCALAPPDATA", "")

TRACKMANIA = os.path.join(DOCUMENTS, "TrackMania")
PROFILES = os.path.join(TRACKMANIA, "Profiles")
SKINS = os.path.join(TRACKMANIA, "Skins")
OFFICIAL_MAPS = os.path.join(TRACKMANIA, "Tracks", "Challenges", "Official Maps")
TMINTERFACE = os.path.join(DOCUMENTS, "TMInterface")
TMI_PLUGIN = os.path.join(TMINTERFACE, "Plugins", "Python_Link.as")
TMI_BUILTIN = os.path.join(TMINTERFACE, "builtin.txt")
TMLOADER = os.path.join(LOCAL_APPDATA, "TMLoader")
TMLOADER_EXE = os.path.join(TMLOADER, "TMLoader.exe")
TMLOADER_GAME = os.path.join(TMLOADER, "database", "TmForever", "products", "TmForever", "settings.yaml")
TMLOADER_PROFILE = os.path.join(TMLOADER, "database", "TmForever", "profiles", "default.yaml")
TMLOADER_PAGE = "https://tomashu.pages.dev/software/tmloader"
STEAM_GAME_PAGE = "steam://install/11020"


def steam_folders():
    folders = []
    for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"), (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
        try:
            with winreg.OpenKey(hive, key) as k:
                for name in ("SteamPath", "InstallPath"):
                    try:
                        folders.append(os.path.normpath(winreg.QueryValueEx(k, name)[0]))
                    except OSError:
                        pass
        except OSError:
            pass
    libraries = []
    for steam in dict.fromkeys(folders):
        libraries.append(steam)
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            with open(vdf, encoding="utf-8", errors="ignore") as f:
                libraries += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', f.read())]
    return list(dict.fromkeys(libraries))


def game_folder():
    if os.path.exists(TMLOADER_GAME):
        with open(TMLOADER_GAME, encoding="utf-8") as f:
            found = re.search(r"install:\s*'(.*)'", f.read())
        if found and os.path.exists(os.path.join(found.group(1), "TmForever.exe")):
            return found.group(1)
    for library in steam_folders():
        candidate = os.path.join(library, "steamapps", "common", GAME_FOLDER_NAME)
        if os.path.exists(os.path.join(candidate, "TmForever.exe")):
            return candidate
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZAB":
        for sub in (r"Program Files (x86)\Steam\steamapps\common", r"SteamLibrary\steamapps\common", r"Steam\steamapps\common", r"Games", r"Program Files (x86)", "Program Files"):
            candidate = os.path.join(f"{drive}:\\", sub, GAME_FOLDER_NAME)
            if os.path.exists(os.path.join(candidate, "TmForever.exe")):
                return candidate
    return None


def game_data():
    folder = game_folder()
    return os.path.join(folder, "GameData") if folder else None
