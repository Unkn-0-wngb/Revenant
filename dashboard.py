import collections
import ctypes
import io
import msvcrt
import multiprocessing
import os
import queue
import re
import sys
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import ttk

import joblib
import matplotlib
import numpy as np
import psutil

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from PIL import Image, ImageTk

import checks
import controls
import machine
import theme
from control_window import ControlWindow
from intro import Intro
from levels_window import LevelsWindow
from level_stats import Events, load_levels

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "linesight"))
from config_files.all_maps import all_maps

TB_DIRS = ("A07_run1", "all_levels_run1")
LOG = os.path.join(ROOT, "logs", "train_run1.log")
LAPS_DIR = os.path.join(ROOT, "linesight", "save", "all_levels_run1", "best_laps")
MAPS_DIR = os.path.join(ROOT, "linesight", "maps")
OFFICIAL_A07_LINE = os.path.join(MAPS_DIR, "A07-Race_0.5m_nadeo.npy")
LINE_FILES = {short: line for short, _, line, _ in all_maps}

START_WIDTH = 789
START_HEIGHT = 483
FULL_LAYOUT_WIDTH = 1300
FULL_LAYOUT_HEIGHT = 760
REFRESH_S = 30
MAP_REFRESH_S = 120
MIN_COMMIT_FOR_MAP_GB = 1.0
STALL_S = 600
AUTO = "Follow running level"
GAP = "Gap to author / record"
STEPS = "Training steps"

from theme import AXIS, CONDENSED, CRITICAL, FONT, NUMBERS, GOOD, GRID, INK, INK_2, MUTED, ORANGE, PAGE, SURFACE, TEAL, WARNING
SPEED_MAP = LinearSegmentedColormap.from_list("speed", ["#06302c", "#00796b", "#00c4ac", "#d6f7f2"])
TAG_PREFIXES = ("eval_race_time_finished_", "explo_race_time_finished_", "eval_race_finished_", "explo_race_finished_")


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


def commit_free_gb():
    status = MemoryStatus()
    status.length = ctypes.sizeof(MemoryStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.avail_commit / 2**30


def read_without_blocking_replace(path):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    handle = kernel32.CreateFileW(path, 0x80000000, 7, None, 3, 0, None)
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error())
    with os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY), "rb") as f:
        return f.read()


def load_zones(path):
    z = np.load(path)
    z = np.vstack((z[0] + (z[0] - z[1]) * np.arange(20, 0, -1)[:, None], z, z[-1] + (z[-1] - z[-2]) * np.arange(1, 1001)[:, None]))
    z[5:-5] = 0.5 * (z[:-10] + z[10:])
    return z


def car_position(state_float, zone_idx, zones):
    car = state_float[62:182].reshape(40, 3)
    world = zones[zone_idx : zone_idx + 800 : 20]
    world_mean, car_mean = world.mean(0), car.mean(0)
    a = np.vstack((world - world_mean, [[0, 100, 0]]))
    b = np.vstack((car - car_mean, [100 * state_float[59:62]]))
    u, _, vt = np.linalg.svd(a.T @ b)
    rotation = (u @ np.diag([1, 1, np.sign(np.linalg.det(u @ vt))]) @ vt).T
    return world_mean - rotation.T @ car_mean


def fastest_lap_path(path, zones):
    laps = joblib.load(io.BytesIO(read_without_blocking_replace(path)))
    race_time, lap = laps[0]
    n = len(lap["wall_contact"])
    floats = [np.array(lap["state_float"][i], dtype=float) for i in range(n)]
    return {
        "time": race_time / 1000,
        "position": np.array([car_position(floats[i], lap["current_zone_idx"][i], zones) for i in range(n)]),
        "speed": np.array([np.linalg.norm(f[56:59]) * 3.6 for f in floats]),
        "wall": np.array(lap["wall_contact"], dtype=bool),
        "kept": [t / 1000 for t, _ in laps],
    }


def rolling(values, window, fn):
    return np.array([fn(values[max(0, i - window + 1) : i + 1]) for i in range(len(values))])


def format_steps(value, _=None):
    return f"{value / 1e6:.2f}M" if value >= 1e6 else f"{value / 1e3:.0f}k"


def format_count(value):
    return format_steps(value) if value >= 1000 else f"{value:.0f}"


def steps_by_level(series):
    runs = []
    for tag, rows in series.items():
        if tag.startswith(("eval_race_finished_", "explo_race_finished_")):
            short = tag.rsplit("_", 1)[1]
            runs.extend((step, short) for step in rows[:, 0])
    totals = collections.Counter()
    previous = 0
    for step, short in sorted(runs):
        totals[short] += step - previous
        previous = step
    return totals


def show_time(value):
    minutes, rest = divmod(value, 60)
    return f"{int(minutes)}:{rest:05.2f}" if minutes else f"{rest:.2f}s"


class Reader:
    def __init__(self, levels):
        self.levels = {level["short"]: level for level in levels}
        self.events = Events(*TB_DIRS)
        self.choice = None
        self.path_key = None
        self.path_time = 0
        self.path = None
        self.step_samples = collections.deque(maxlen=12)

    def series(self):
        rows = self.events.update()
        return {tag: np.array(sorted(v), dtype=float).reshape(-1, 2) for tag, v in rows.items() if tag == "wall_contact_fraction" or tag.startswith(TAG_PREFIXES)}

    def log_state(self):
        if not os.path.exists(LOG):
            return 0, None, float("inf")
        with open(LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 200_000))
            found = re.findall(rb"NMG=(\d+)", f.read())
        steps = int(found[-1]) if found else 0
        now = time.time()
        self.step_samples.append((now, steps))
        rate = None
        first_time, first_steps = self.step_samples[0]
        if now - first_time > 20 and steps >= first_steps:
            rate = (steps - first_steps) / (now - first_time)
        return steps, rate, now - os.path.getmtime(LOG)

    def lap_path(self, short):
        path = os.path.join(LAPS_DIR, f"{short}.joblib")
        if short not in LINE_FILES or not os.path.exists(path):
            self.path, self.path_key = None, None
            return None
        key = (short, os.path.getmtime(path))
        changed_level = self.path_key is None or self.path_key[0] != short
        due = changed_level or time.time() - self.path_time >= MAP_REFRESH_S
        if key != self.path_key and due and commit_free_gb() >= MIN_COMMIT_FOR_MAP_GB:
            zones = load_zones(os.path.join(MAPS_DIR, LINE_FILES[short]))
            self.path = fastest_lap_path(path, zones)
            self.path_key = key
            self.path_time = time.time()
        return self.path if self.path_key and self.path_key[0] == short else None

    def read(self):
        steps, rate, log_age = self.log_state()
        alive = False
        games = 0
        for p in psutil.process_iter(["name", "cmdline"]):
            try:
                name = (p.info["name"] or "").lower()
                games += name == "tmforever.exe"
                alive = alive or ("python" in name and "train.py" in " ".join(p.info["cmdline"] or []))
            except psutil.Error:
                pass
        series = self.series()

        latest, running = -1, None
        best = {}
        tried = set()
        for tag, rows in series.items():
            if tag == "wall_contact_fraction" or not len(rows):
                continue
            short = tag.rsplit("_", 1)[1]
            tried.add(short)
            if rows[-1, 0] > latest:
                latest, running = rows[-1, 0], short
            if "_time_finished_" in tag:
                values = rows[rows[:, 1] > 0, 1]
                if len(values):
                    best[short] = min(best.get(short, 1e9), float(values.min()))

        short = self.choice or running or "A01"
        empty = np.zeros((0, 2))
        laps = series.get(f"eval_race_time_finished_trained_{short}", empty)
        finished = series.get(f"eval_race_finished_trained_{short}", empty)
        explo_finished = series.get(f"explo_race_finished_trained_{short}", empty)
        level_steps = set(finished[:, 0]) | set(explo_finished[:, 0])
        wall = series.get("wall_contact_fraction", empty)
        wall = wall[np.isin(wall[:, 0], list(level_steps))] if level_steps else empty
        return {
            "short": short,
            "running": running,
            "laps": laps[laps[:, 1] > 0],
            "finished": finished,
            "wall": wall,
            "best": best,
            "tried": tried,
            "steps": steps,
            "level_steps": steps_by_level(series)[short],
            "rate": rate,
            "log_age": log_age,
            "alive": alive,
            "games": games,
            "commit": commit_free_gb(),
            "path": self.lap_path(short),
            "read_at": time.strftime("%H:%M:%S"),
        }


def read_forever(levels, choice, requests, results):
    reader = Reader(levels)
    reader.choice = choice
    while True:
        try:
            results.put(reader.read())
        except Exception as e:
            results.put(e)
        try:
            reader.choice = requests.get(timeout=REFRESH_S)
            while True:
                reader.choice = requests.get_nowait()
        except queue.Empty:
            pass


class Tile:
    def __init__(self, parent, title):
        self.frame = tk.Frame(parent, bg=SURFACE, padx=14, pady=10)
        self.title = tk.Label(self.frame, text=title.upper(), bg=SURFACE, fg=MUTED, font=(CONDENSED, 9), anchor="w", bd=0, pady=0)
        self.title.pack(fill="x")
        self.value = tk.Label(self.frame, text="-", bg=SURFACE, fg=INK, font=(NUMBERS, 19), anchor="w", bd=0, pady=0)
        self.value.pack(fill="x")
        self.note = tk.Label(self.frame, text=" ", bg=SURFACE, fg=INK_2, font=(FONT, 9), anchor="w", bd=0, pady=0)
        self.note.pack(fill="x")

    def set(self, value, note, color=INK):
        self.value.config(text=value, fg=color)
        self.note.config(text=note)

    def resize(self, compact):
        self.frame.config(padx=8 if compact else 14, pady=2 if compact else 10)
        self.title.config(font=(CONDENSED, 7 if compact else 9))
        self.value.config(font=(NUMBERS, 13 if compact else 19))
        self.note.config(font=(FONT, 7 if compact else 9))


class Dashboard:
    def __init__(self, snapshot=None, level=None):
        self.snapshot = snapshot
        self.levels = load_levels()
        self.level_by_short = {level_info["short"]: level_info for level_info in self.levels}
        self.root = tk.Tk()
        self.root.title("Revenant")
        self.root.geometry(f"{START_WIDTH}x{START_HEIGHT}")
        self.root.minsize(START_WIDTH, START_HEIGHT)
        self.root.configure(bg=PAGE)

        theme.style(self.root)
        theme.dark_title(self.root)

        logo = Image.open(os.path.join(ROOT, "art", "revenant_logo_256.png"))
        self.icon = ImageTk.PhotoImage(logo.resize((64, 64), Image.LANCZOS))
        self.root.iconphoto(True, self.icon)
        header = Image.open(os.path.join(ROOT, "art", "revenant_header.png"))
        self.header = ImageTk.PhotoImage(header.resize((round(header.width * 24 / header.height), 24), Image.LANCZOS))

        top = tk.Frame(self.root, bg=PAGE)
        top.pack(fill="x", padx=10, pady=(8, 2))
        self.header_label = tk.Label(top, image=self.header, bg=PAGE, bd=0)
        self.header_label.pack(side="left", padx=(0, 18))
        self.picker = ttk.Combobox(top, values=[AUTO] + [level_info["name"] for level_info in self.levels], state="readonly", width=24, font=(FONT, 10))
        self.picker.set(AUTO)
        self.picker.pack(side="left")
        self.picker.bind("<<ComboboxSelected>>", self.on_pick)
        theme.link_button(top, "Controls", self.open_controls, primary=True).pack(side="right")
        theme.link_button(top, "Levels", self.open_levels).pack(side="right", padx=(0, 8))
        self.controls = None
        self.levels_view = None
        self.heading = tk.Label(top, text="", bg=PAGE, fg=INK, font=(FONT, 11, "bold"), anchor="w")
        self.heading.pack(side="left", padx=14, fill="x", expand=True)

        self.tile_row = tk.Frame(self.root, bg=PAGE)
        self.tile_row.pack(fill="x", padx=6, pady=(3, 2))
        names = ("Best lap", "Typical lap", "Finish rate", GAP, "Levels finished", STEPS, "Status", "Memory headroom")
        self.tiles = {name: Tile(self.tile_row, name) for name in names}

        self.footer = tk.Label(self.root, text="Reading training files...", bg=PAGE, fg=INK_2, font=(FONT, 10), anchor="w")
        self.footer.pack(side="bottom", fill="x", padx=10, pady=(0, 3))

        self.figure = Figure(facecolor=PAGE)
        self.grid = self.figure.add_gridspec(2, 3)
        self.ax_laps = self.figure.add_subplot(self.grid[0, 0:2])
        self.ax_finish = self.figure.add_subplot(self.grid[1, 0])
        self.ax_wall = self.figure.add_subplot(self.grid[1, 1])
        self.ax_map = self.figure.add_subplot(self.grid[:, 2])
        self.colorbar_axes = self.figure.add_axes([0.71, 0.075, 0.2, 0.012])
        self.compact = None
        self.latest = None
        self.apply_layout(True)
        self.placeholders()

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.root)
        self.canvas.get_tk_widget().configure(bg=PAGE, highlightthickness=0)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=12)
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)
        self.root.bind("<Configure>", self.on_resize)

        self.line_cache = {}
        self.hover_data = {}
        self.tooltips = {}
        self.results = multiprocessing.Queue()
        self.requests = multiprocessing.Queue()
        multiprocessing.Process(target=read_forever, args=(self.levels, level, self.requests, self.results), daemon=True).start()
        self.root.after(300, self.poll)
        self.after_intro = []
        if not snapshot:
            self.play_intro()

    def play_intro(self):
        art = os.path.join(ROOT, "art", "revenant_header.png")
        Intro(self.root, art, self.header_spot, lambda: self.latest is not None, lambda: [later() for later in self.after_intro])

    def header_spot(self):
        label = self.header_label
        return label.winfo_rootx() - self.root.winfo_rootx(), label.winfo_rooty() - self.root.winfo_rooty(), self.header.height()

    def apply_layout(self, compact):
        self.compact = compact
        self.scale = 0.76 if compact else 1
        columns = 4 if compact else 8
        for i, tile in enumerate(self.tiles.values()):
            tile.resize(compact)
            tile.frame.grid(row=i // columns, column=i % columns, sticky="nsew", padx=2 if compact else 4, pady=2)
        for column in range(8):
            self.tile_row.columnconfigure(column, weight=1 if column < columns else 0, uniform="tile" if column < columns else "")
        self.footer.config(font=(FONT, 7 if compact else 10))
        if compact:
            self.grid.set_width_ratios([1, 1, 1.05])
            self.grid.set_height_ratios([1.3, 1])
            self.grid.update(left=0.042, right=0.99, top=0.92, bottom=0.08, wspace=0.17, hspace=0.42)
        else:
            self.grid.set_width_ratios([1, 1, 1.25])
            self.grid.set_height_ratios([1.45, 1])
            self.grid.update(left=0.045, right=0.985, top=0.95, bottom=0.07, wspace=0.2, hspace=0.3)
        for ax in (self.ax_laps, self.ax_finish, self.ax_wall, self.ax_map):
            ax.set_position(ax.get_subplotspec().get_position(self.figure))
        box = self.ax_map.get_position()
        self.colorbar_axes.set_position([box.x0 + box.width * 0.12, box.y0 + box.height * 0.09, box.width * 0.76, box.height * 0.018])

    def placeholders(self):
        for ax, title in ((self.ax_laps, "Test lap times"), (self.ax_finish, "Test runs finished, last 30 (%)"), (self.ax_wall, "Steps touching a wall (%)"), (self.ax_map, "Fastest kept lap")):
            self.style(ax, title)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.text(0.5, 0.5, "Loading training data...", transform=ax.transAxes, color=MUTED, fontsize=self.pt(10), fontfamily=FONT, ha="center", va="center")
        self.colorbar_axes.set_axis_off()

    def on_resize(self, event):
        if event.widget is not self.root:
            return
        compact = event.width < FULL_LAYOUT_WIDTH or event.height < FULL_LAYOUT_HEIGHT
        if compact != self.compact:
            self.apply_layout(compact)
            if self.latest:
                self.show(self.latest)

    def open_controls(self):
        if self.controls and self.controls.window.winfo_exists():
            self.controls.window.lift()
            return
        self.controls = ControlWindow(self.root)

    def open_levels(self):
        if self.levels_view and self.levels_view.window.winfo_exists():
            self.levels_view.window.lift()
            return
        self.levels_view = LevelsWindow(self.root, self.levels, self.pick_level)
        if self.latest:
            self.levels_view.update(self.latest["best"], self.latest.get("tried", set()))

    def pick_level(self, short):
        level = self.level_by_short.get(short)
        if not level:
            return
        self.picker.set(level["name"])
        self.requests.put(short)
        self.heading.config(text="Loading...")

    def on_pick(self, _):
        name = self.picker.get()
        self.requests.put(None if name == AUTO else name[:3])
        self.picker.selection_clear()
        self.heading.config(text="Loading...")

    def pt(self, size):
        return size * self.scale

    def poll(self):
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            self.root.after(300, self.poll)
            return
        if isinstance(result, Exception):
            self.footer.config(text=f"Could not read training files: {result}", fg=WARNING)
        else:
            self.show(result)
        if self.snapshot:
            self.root.update()
            self.figure.savefig(self.snapshot, facecolor=PAGE, dpi=100)
            self.root.destroy()
            return
        self.root.after(300, self.poll)

    def show(self, d):
        self.latest = d
        if self.levels_view and self.levels_view.window.winfo_exists():
            self.levels_view.update(d["best"], d.get("tried", set()))
        level = self.level_by_short.get(d["short"], self.levels[0])
        short = level["short"]
        laps, finished = d["laps"], d["finished"]
        best = d["best"].get(short)
        recent = laps[-20:, 1]
        typical = float(np.median(recent)) if len(recent) else None

        where = "running now" if d["running"] == short else "not running now"
        self.heading.config(text=f"{level['name']}, {where}" + (f" ({level['note']})" if level["note"] else ""))

        if best is not None:
            self.tiles["Best lap"].set(show_time(best), f"author {show_time(level['author'])}")
            self.tiles[GAP].set(f"{best - level['author']:+.2f} / {best - level['record']:+.2f}s", f"record {show_time(level['record'])} on TMX")
        else:
            self.tiles["Best lap"].set("No finish", f"author {show_time(level['author'])}")
            self.tiles[GAP].set("-", f"record {show_time(level['record'])} on TMX")
        if typical is not None:
            low, high = np.percentile(recent, [25, 75])
            self.tiles["Typical lap"].set(show_time(typical), f"mostly {low:.1f}-{high:.1f}")
        else:
            self.tiles["Typical lap"].set("-", "no test finishes yet")
        if len(finished):
            last = finished[-30:, 1]
            self.tiles["Finish rate"].set(f"{last.mean() * 100:.0f}%", f"last {len(last)} test runs")
        else:
            self.tiles["Finish rate"].set("-", "no test runs yet")

        playable = self.levels
        done = sum(level_info["short"] in d["best"] for level_info in playable)
        medals = sum(d["best"].get(level_info["short"], 1e9) <= level_info["author"] for level_info in playable)
        self.tiles["Levels finished"].set(f"{done} of {len(playable)}", f"{medals} beat author")

        rate = f", {d['rate']:.0f}/s" if d["rate"] is not None and d["alive"] else ""
        self.tiles[STEPS].set(format_steps(d["steps"]), f"{format_count(d['level_steps'])} on {short}{rate}")

        if not d["alive"]:
            self.tiles["Status"].set("Stopped", "training is not running", MUTED)
        elif d["log_age"] > STALL_S:
            self.tiles["Status"].set("Stalled", f"log quiet for {int(d['log_age'] // 60)} min", WARNING)
        elif d["games"] < 2:
            self.tiles["Status"].set("1 game", "second game is missing", WARNING)
        else:
            self.tiles["Status"].set("Training", f"{d['games']} games running", GOOD)

        if d["commit"] < 1:
            self.tiles["Memory headroom"].set(f"{d['commit']:.1f} GB", "very low, close other apps", CRITICAL)
        elif d["commit"] < 2:
            self.tiles["Memory headroom"].set(f"{d['commit']:.1f} GB", "getting low", WARNING)
        else:
            self.tiles["Memory headroom"].set(f"{d['commit']:.1f} GB", "commit memory free")

        self.draw_laps(level, laps)
        self.draw_rate(finished)
        self.draw_wall(d["wall"])
        self.draw_map(level, d["path"])
        self.canvas.draw_idle()

        last_laps = "  ".join(f"{v:.2f}" for v in laps[-10:, 1][::-1]) or "none yet"
        kept = ""
        if d["path"] and not self.compact:
            kept = "     Kept for replay: " + "  ".join(f"{v:.2f}" for v in d["path"]["kept"])
        self.footer.config(text=f"Last test laps, newest first: {last_laps}{kept}     Updated {d['read_at']}", fg=INK_2)

    def style(self, ax, title):
        ax.clear()
        ax.set_facecolor(SURFACE)
        ax.set_title(title, color=INK, fontsize=self.pt(11), fontfamily=FONT, loc="left", pad=self.pt(8))
        ax.grid(True, axis="y", color=GRID, linewidth=0.7)
        ax.set_axisbelow(True)
        for side, spine in ax.spines.items():
            spine.set_visible(side == "bottom")
            spine.set_color(AXIS)
        ax.tick_params(colors=MUTED, labelsize=self.pt(9), length=0, pad=2)
        ax.xaxis.set_major_formatter(FuncFormatter(format_steps))
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4 if self.compact else 6))

    def tooltip(self, ax):
        note = ax.annotate(
            "",
            xy=(0, 0),
            xytext=(10, 10),
            textcoords="offset points",
            color=INK,
            fontsize=self.pt(9),
            fontfamily=FONT,
            bbox={"boxstyle": "round,pad=0.4", "fc": "#000000", "ec": AXIS},
            zorder=20,
            annotation_clip=False,
        )
        note.set_visible(False)
        self.tooltips[ax] = note

    def draw_laps(self, level, laps):
        ax = self.ax_laps
        self.style(ax, "Test lap times")
        references = [(level["record"], f"Best on TMX {level['record']:.2f}", MUTED, 0.9), (level["author"], f"Author {level['author']:.2f}", MUTED, 0.9)]
        low = level["record"] * 0.96
        high = level["author"] * 1.25
        if len(laps):
            low = min(low, float(laps[:, 1].min()) * 0.98)
            high = max(level["author"] * 1.05, min(float(np.percentile(laps[:, 1], 95)) * 1.04, float(np.median(laps[:, 1])) * 1.5))
            start, end = float(laps[0, 0]), float(laps[-1, 0])
            margin = max((end - start) * 0.03, 1000)
            ax.set_xlim(start - margin, end + margin)
        else:
            ax.set_xlim(0, 1)
            ax.set_xticks([])
            ax.text(0.5, 0.86, "No finished test laps yet", transform=ax.transAxes, color=INK_2, fontsize=self.pt(11), fontfamily=FONT, ha="center")
        ax.set_ylim(low, high)
        x0, x1 = ax.get_xlim()
        for value, label, color, width in references:
            ax.axhline(value, color=color, linewidth=width, zorder=2)
            ax.text(x0 + (x1 - x0) * 0.008, value + (high - low) * 0.01, label, color=INK_2, fontsize=self.pt(9), fontfamily=FONT, va="bottom")
        if len(laps):
            ax.scatter(laps[:, 0], laps[:, 1], s=self.pt(30), color=TEAL, alpha=0.85, edgecolors=SURFACE, linewidths=1, label="Finished test lap", zorder=3)
            running = np.minimum.accumulate(laps[:, 1])
            ax.step(laps[:, 0], running, where="post", color=INK, linewidth=2, label="Best test lap so far", zorder=4)
            ax.annotate(f"{running[-1]:.2f}", (laps[-1, 0], running[-1]), xytext=(-6, -14 * self.scale), textcoords="offset points", color=INK, fontsize=self.pt(10), fontfamily=FONT, fontweight="bold", ha="right")
            ax.legend(loc="lower right", bbox_to_anchor=(1, 0.99), ncol=2, frameon=False, labelcolor=INK_2, fontsize=self.pt(9), borderaxespad=0)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}s"))
        self.hover_data[ax] = (laps[:, 0], laps[:, 1], lambda x, y: f"{y:.2f}s at {format_steps(x)} steps")
        self.tooltip(ax)

    def draw_rate(self, finished):
        ax = self.ax_finish
        self.style(ax, "Runs finished, last 30 (%)" if self.compact else "Test runs finished, last 30 (%)")
        rate = rolling(finished[:, 1], 30, np.mean) * 100 if len(finished) else np.array([])
        ax.plot(finished[:, 0], rate, color=TEAL, linewidth=2)
        ax.set_ylim(0, 105)
        if not len(finished):
            ax.set_xticks([])
        self.hover_data[ax] = (finished[:, 0], rate, lambda x, y: f"{y:.0f}% at {format_steps(x)} steps")
        self.tooltip(ax)

    def draw_wall(self, wall):
        ax = self.ax_wall
        self.style(ax, "Wall touches, typical run (%)" if self.compact else "Steps touching a wall, typical run (%)")
        value = rolling(wall[:, 1], 30, np.median) * 100 if len(wall) else np.array([])
        ax.plot(wall[:, 0], value, color=TEAL, linewidth=2)
        ax.set_ylim(0, max(6, float(value.max()) * 1.15) if len(value) else 6)
        if not len(wall):
            ax.set_xticks([])
        self.hover_data[ax] = (wall[:, 0], value, lambda x, y: f"{y:.1f}% at {format_steps(x)} steps")
        self.tooltip(ax)

    def reference_line(self, short):
        if short not in LINE_FILES:
            return None
        path = os.path.join(MAPS_DIR, LINE_FILES[short])
        key = (short, os.path.getmtime(path))
        if key not in self.line_cache:
            self.line_cache[key] = np.load(path)
        return self.line_cache[key]

    def draw_map(self, level, path):
        ax = self.ax_map
        ax.clear()
        ax.set_facecolor(SURFACE)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        line = self.reference_line(level["short"])
        if level["short"] == "A07":
            official = np.load(OFFICIAL_A07_LINE)
            ax.plot(official[:, 0], official[:, 2], color=MUTED, linewidth=1, label="Official line", zorder=2)
        if line is not None:
            ax.plot(line[:, 0], line[:, 2], color=ORANGE, linewidth=1.4, label="Reference line", zorder=3)
        ends = line if line is not None else (path["position"] if path else None)
        if ends is not None:
            start, finish = ends[0], ends[-1]
            ax.scatter([start[0]], [start[2]], marker="o", s=self.pt(70), color=GOOD, edgecolors=SURFACE, linewidths=1.5, label="Start", zorder=6)
            ax.scatter([finish[0]], [finish[2]], marker="s", s=self.pt(60), color=INK, edgecolors=SURFACE, linewidths=1.5, label="Finish", zorder=6)
        self.colorbar_axes.clear()
        if path:
            ax.set_title(f"Fastest kept lap, {path['time']:.2f}s, coloured by speed", color=INK, fontsize=self.pt(11), fontfamily=FONT, loc="left", pad=self.pt(8))
            xy = path["position"][:, [0, 2]]
            segments = np.stack((xy[:-1], xy[1:]), axis=1)
            top = max(300, float(path["speed"].max()))
            lines = LineCollection(segments, cmap=SPEED_MAP, norm=Normalize(100, top), linewidths=2 if self.compact else 3, zorder=4, capstyle="round")
            lines.set_array(path["speed"][:-1])
            ax.add_collection(lines)
            touched = path["position"][path["wall"]]
            if len(touched):
                ax.scatter(touched[:, 0], touched[:, 2], marker="x", s=self.pt(46), color=CRITICAL, linewidths=2, label="Wall touch", zorder=5)
            self.colorbar_axes.set_axis_on()
            self.colorbar_axes.imshow(np.linspace(0, 1, 256)[None, :], aspect="auto", cmap=SPEED_MAP, extent=(100, top, 0, 1))
            self.colorbar_axes.set_yticks([])
            self.colorbar_axes.set_xticks([100, 200, 300])
            self.colorbar_axes.set_xticklabels(["100", "200", "300 km/h"])
            self.colorbar_axes.tick_params(colors=MUTED, labelsize=self.pt(9), length=0, pad=2)
            for spine in self.colorbar_axes.spines.values():
                spine.set_visible(False)
        else:
            ax.set_title("Reference line, no finished lap kept yet" if line is not None else "No reference line", color=INK, fontsize=self.pt(11), fontfamily=FONT, loc="left", pad=self.pt(8))
            self.colorbar_axes.set_axis_off()
        if ends is not None:
            low, high = float(ends[:, 2].min()), float(ends[:, 2].max())
            ax.plot([float(ends[:, 0].mean())], [low - (high - low) * 0.18], alpha=0)
        ax.set_aspect("equal", adjustable="datalim")
        if line is not None:
            ax.legend(loc="upper left", frameon=False, labelcolor=INK_2, fontsize=self.pt(9))

    def on_hover(self, event):
        changed = False
        for ax, note in self.tooltips.items():
            xs, ys, text = self.hover_data.get(ax, ((), (), None))
            show = False
            if event.inaxes is ax and len(xs):
                points = ax.transData.transform(np.column_stack((xs, ys)))
                distance = np.hypot(points[:, 0] - event.x, points[:, 1] - event.y)
                i = int(distance.argmin())
                if distance[i] <= 24:
                    note.xy = (xs[i], ys[i])
                    note.set_text(text(xs[i], ys[i]))
                    show = True
            if show or note.get_visible():
                changed = True
            note.set_visible(show)
        if changed:
            self.canvas.draw_idle()


def main():
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    machine.make_config_copy()
    if controls.profile() != controls.AI_PROFILE and not controls.training_running():
        try:
            controls.use_ai_profile()
        except OSError:
            pass
    dashboard = Dashboard(sys.argv[1] if len(sys.argv) > 1 else None, sys.argv[2] if len(sys.argv) > 2 else None)
    if not all(ok for _, ok, *_ in checks.run_all()):
        dashboard.after_intro.append(dashboard.open_controls)
    dashboard.root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        from tkinter import messagebox

        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        report = os.path.join(ROOT, "logs", "dashboard_error.log")
        with open(report, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        messagebox.showerror("Revenant", f"The dashboard hit an error and closed.\n\nDetails are in {report}")
