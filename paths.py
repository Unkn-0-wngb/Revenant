import getpass
import os
import re
import sys
import uuid

IS_WINDOWS = sys.platform == "win32"
ROOT = os.path.dirname(os.path.abspath(__file__))
LINESIGHT = os.path.join(ROOT, "linesight")
if IS_WINDOWS:
    VENV_PYTHON = os.path.join(ROOT, "venv", "Scripts", "python.exe")
    VENV_PYTHONW = os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")
else:
    VENV_PYTHON = os.path.join(ROOT, "venv", "bin", "python")
    VENV_PYTHONW = VENV_PYTHON
GAME_FOLDER_NAME = "TrackMania Nations Forever"
HELPER_PORT_OFFSET = 7
FOLLOWER_PORT_OFFSET = 7
BRUTEFORCE_PORT_OFFSET = 8
BENCHMARK_PORT_OFFSET = 9
PORT_BLOCK = 10
WINEPREFIX = os.environ.get("WINEPREFIX") or os.path.join(os.path.expanduser("~"), ".wine")


def known_folder(folder_id):
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

    guid = GUID()
    ctypes.memmove(ctypes.byref(guid), uuid.UUID(folder_id).bytes_le, 16)
    path = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path)) != 0:
        return None
    result = path.value
    ctypes.windll.ole32.CoTaskMemFree(path)
    return result


def wine_to_unix(path):
    path = path.replace("\\", "/")
    if re.match(r"^[zZ]:/", path):
        return path[2:]
    if re.match(r"^[a-zA-Z]:/", path):
        return os.path.join(WINEPREFIX, "drive_c" if path[0].lower() == "c" else f"dosdevices/{path[0].lower()}:", path[3:])
    return path


if IS_WINDOWS:
    DOCUMENTS = known_folder("FDD39AD0-238F-46AF-ADB4-6C85480369C7") or os.path.join(os.path.expanduser("~"), "Documents")
    LOCAL_APPDATA = known_folder("F1B32785-6FBA-4FCF-9D55-7B8E7F157091") or os.environ.get("LOCALAPPDATA", "")
else:
    WINE_USER = os.path.join(WINEPREFIX, "drive_c", "users", getpass.getuser())
    DOCUMENTS = os.path.join(WINE_USER, "Documents")
    LOCAL_APPDATA = os.path.join(WINE_USER, "AppData", "Local")


def unix_to_wine(path):
    drive_c = os.path.join(WINEPREFIX, "drive_c")
    if path.startswith(drive_c):
        return "C:" + path[len(drive_c) :].replace("/", "\\")
    return "Z:" + path.replace("/", "\\")


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


def steam_roots():
    if not IS_WINDOWS:
        home = os.path.expanduser("~")
        return [
            os.path.join(home, ".steam", "steam"),
            os.path.join(home, ".local", "share", "Steam"),
            os.path.join(home, ".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam"),
        ]
    import winreg

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
    return folders


def steam_folders():
    libraries = []
    for steam in dict.fromkeys(steam_roots()):
        if not os.path.isdir(steam):
            continue
        libraries.append(steam)
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            with open(vdf, encoding="utf-8", errors="ignore") as f:
                libraries += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', f.read())]
    return list(dict.fromkeys(os.path.realpath(p) for p in libraries))


def other_places():
    if not IS_WINDOWS:
        drive_c = os.path.join(WINEPREFIX, "drive_c")
        return [os.path.join(drive_c, sub, GAME_FOLDER_NAME) for sub in ("Program Files (x86)", "Program Files", "Games", os.path.join("Program Files (x86)", "Steam", "steamapps", "common"))]
    places = []
    for drive in "CDEFGHIJKLMNOPQRSTUVWXYZAB":
        for sub in (r"Program Files (x86)\Steam\steamapps\common", r"SteamLibrary\steamapps\common", r"Steam\steamapps\common", r"Games", r"Program Files (x86)", "Program Files"):
            places.append(os.path.join(f"{drive}:\\", sub, GAME_FOLDER_NAME))
    return places


def game_folder():
    if os.path.exists(TMLOADER_GAME):
        with open(TMLOADER_GAME, encoding="utf-8") as f:
            found = re.search(r"install:\s*'(.*)'", f.read())
        if found:
            folder = found.group(1).replace("''", "'")
            folder = folder if IS_WINDOWS else wine_to_unix(folder)
            if os.path.exists(os.path.join(folder, "TmForever.exe")):
                return folder
    for library in steam_folders():
        candidate = os.path.join(library, "steamapps", "common", GAME_FOLDER_NAME)
        if os.path.exists(os.path.join(candidate, "TmForever.exe")):
            return candidate
    for candidate in other_places():
        if os.path.exists(os.path.join(candidate, "TmForever.exe")):
            return candidate
    return None


def game_data():
    folder = game_folder()
    return os.path.join(folder, "GameData") if folder else None