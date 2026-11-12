import ctypes
import tkinter as tk
from tkinter import ttk

PAGE = "#0d0d0d"
SURFACE = "#1a1a19"
RAISED = "#232322"
INK = "#f0efec"
INK_2 = "#c3c2b7"
MUTED = "#898781"
GRID = "#2c2c2a"
AXIS = "#383835"
TEAL = "#00c4ac"
TEAL_HOVER = "#33d6c2"
TEAL_DIM = "#00796b"
ORANGE = "#d95926"
GOOD = "#2fbf71"
WARNING = "#fab219"
CRITICAL = "#e5534b"

FONT = "Segoe UI"
DISPLAY = "Bahnschrift SemiBold"
CONDENSED = "Bahnschrift SemiBold SemiConden"
NUMBERS = "Bahnschrift SemiBold Condensed"


def dark_title(window):
    try:
        window.update_idletasks()
        handle = ctypes.windll.user32.GetParent(window.winfo_id())
        on = ctypes.c_int(1)
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, attribute, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        colour = ctypes.c_int(int(PAGE[5:7] + PAGE[3:5] + PAGE[1:3], 16))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 35, ctypes.byref(colour), ctypes.sizeof(colour))
    except (AttributeError, OSError):
        pass


def style(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    flat = {"lightcolor": GRID, "darkcolor": GRID, "bordercolor": AXIS, "focuscolor": GRID}
    s.configure("TButton", background=GRID, foreground=INK, font=(FONT, 10), padding=(12, 5), relief="flat", **flat)
    s.map("TButton", background=[("disabled", RAISED), ("pressed", AXIS), ("active", AXIS)], foreground=[("disabled", MUTED)], bordercolor=[("disabled", RAISED), ("focus", TEAL_DIM)], lightcolor=[("disabled", RAISED), ("active", AXIS)], darkcolor=[("disabled", RAISED), ("active", AXIS)])
    accent = {"lightcolor": TEAL, "darkcolor": TEAL, "bordercolor": TEAL, "focuscolor": TEAL}
    s.configure("Accent.TButton", background=TEAL, foreground=PAGE, font=(FONT, 10, "bold"), padding=(16, 5), **accent)
    s.map(
        "Accent.TButton",
        background=[("disabled", RAISED), ("active", TEAL_HOVER)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("disabled", RAISED), ("active", TEAL_HOVER)],
        lightcolor=[("disabled", RAISED), ("active", TEAL_HOVER)],
        darkcolor=[("disabled", RAISED), ("active", TEAL_HOVER)],
    )
    s.configure("TCombobox", fieldbackground=RAISED, background=RAISED, foreground=INK, arrowcolor=TEAL, bordercolor=AXIS, lightcolor=RAISED, darkcolor=RAISED, padding=(8, 4))
    s.map(
        "TCombobox",
        fieldbackground=[("readonly", "focus", RAISED), ("readonly", RAISED)],
        background=[("readonly", "active", AXIS), ("readonly", RAISED)],
        foreground=[("readonly", INK)],
        selectbackground=[("readonly", RAISED)],
        selectforeground=[("readonly", INK)],
        bordercolor=[("focus", TEAL_DIM)],
    )
    s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=INK, rowheight=24, font=(FONT, 10), bordercolor=GRID, lightcolor=SURFACE, darkcolor=SURFACE)
    s.configure("Treeview.Heading", background=RAISED, foreground=MUTED, font=(FONT, 9, "bold"), relief="flat", bordercolor=GRID, lightcolor=RAISED, darkcolor=RAISED)
    s.map("Treeview", background=[("selected", AXIS)], foreground=[("selected", INK)])
    s.map("Treeview.Heading", background=[("active", AXIS)])
    s.configure("Vertical.TScrollbar", background=GRID, troughcolor=SURFACE, bordercolor=SURFACE, lightcolor=GRID, darkcolor=GRID, arrowcolor=MUTED)
    root.option_add("*TCombobox*Listbox.background", RAISED)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", TEAL_DIM)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))
    return s


def entry(parent, value="", width=8):
    field = tk.Entry(
        parent,
        width=width,
        bg=RAISED,
        fg=INK,
        insertbackground=INK,
        relief="flat",
        font=(FONT, 10),
        highlightthickness=1,
        highlightbackground=AXIS,
        highlightcolor=TEAL_DIM,
    )
    field.insert(0, str(value))
    return field


def link_button(parent, text, command, primary=False):
    bg, fg, hover = (TEAL, PAGE, TEAL_HOVER) if primary else (GRID, INK, AXIS)
    button = tk.Label(parent, text=text, bg=bg, fg=fg, font=(FONT, 10, "bold"), padx=16, pady=5, cursor="hand2")
    button.bind("<Button-1>", lambda _: command())
    button.bind("<Enter>", lambda _: button.config(bg=hover))
    button.bind("<Leave>", lambda _: button.config(bg=bg))
    return button


class Tabs:
    def __init__(self, parent, bg):
        self.bar = tk.Frame(parent, bg=bg)
        self.bar.pack(fill="x", padx=8, pady=(8, 0))
        tk.Frame(parent, bg=GRID, height=1).pack(fill="x", padx=8)
        self.body = tk.Frame(parent, bg=bg)
        self.body.pack(fill="both", expand=True, padx=8)
        self.bg = bg
        self.pages = {}
        self.current = None

    def add(self, name):
        page = tk.Frame(self.body, bg=self.bg, padx=10, pady=12)
        holder = tk.Frame(self.bar, bg=self.bg)
        holder.pack(side="left")
        label = tk.Label(holder, text=name, bg=self.bg, fg=MUTED, font=(FONT, 10, "bold"), padx=14, pady=8, cursor="hand2")
        label.pack()
        line = tk.Frame(holder, bg=self.bg, height=2)
        line.pack(fill="x")
        label.bind("<Button-1>", lambda _: self.select(name))
        label.bind("<Enter>", lambda _: label.config(fg=INK) if self.current != name else None)
        label.bind("<Leave>", lambda _: label.config(fg=MUTED) if self.current != name else None)
        self.pages[name] = (page, label, line)
        if self.current is None:
            self.select(name)
        return page

    def select(self, name):
        for key, (page, label, line) in self.pages.items():
            chosen = key == name
            label.config(fg=INK if chosen else MUTED)
            line.config(bg=TEAL if chosen else self.bg)
            if chosen:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        self.current = name
