import tkinter as tk

import theme

SERIES = ("A", "B", "C", "D", "E")
KEY = (("Author", theme.TEAL), ("Finished", theme.INK), ("Tried", theme.WARNING), ("Not reached", theme.AXIS))


def show_time(value):
    minutes, rest = divmod(value, 60)
    return f"{int(minutes)}:{rest:05.2f}" if minutes else f"{rest:.2f}"


class LevelsWindow:
    def __init__(self, parent, levels, on_pick):
        self.levels = levels
        self.on_pick = on_pick
        self.window = tk.Toplevel(parent)
        self.window.title("Revenant levels")
        self.window.configure(bg=theme.PAGE)
        self.window.resizable(False, False)
        theme.dark_title(self.window)

        head = tk.Frame(self.window, bg=theme.PAGE)
        head.pack(fill="x", padx=14, pady=(14, 2))
        tk.Label(head, text="OFFICIAL LEVELS", bg=theme.PAGE, fg=theme.INK, font=(theme.DISPLAY, 15)).pack(side="left")
        legend = tk.Frame(head, bg=theme.PAGE)
        legend.pack(side="right")
        for label, colour in KEY:
            tk.Frame(legend, bg=colour, width=10, height=10).pack(side="left", padx=(12, 5))
            tk.Label(legend, text=label, bg=theme.PAGE, fg=theme.INK_2, font=(theme.FONT, 9)).pack(side="left")
        self.summary = tk.Label(self.window, text="", bg=theme.PAGE, fg=theme.MUTED, font=(theme.FONT, 10), anchor="w")
        self.summary.pack(fill="x", padx=14)

        self.grid = tk.Frame(self.window, bg=theme.PAGE)
        self.grid.pack(padx=10, pady=(10, 8))
        tk.Label(self.window, text="Click a level to show it in the dashboard.", bg=theme.PAGE, fg=theme.MUTED, font=(theme.FONT, 9)).pack(pady=(0, 12))
        self.tiles = {}
        for column, series in enumerate(SERIES):
            tk.Label(self.grid, text=series, bg=theme.PAGE, fg=theme.MUTED, font=(theme.CONDENSED, 11)).grid(row=0, column=column, pady=(0, 4))
            row = 1
            for level in levels:
                if level["short"][0] != series:
                    continue
                self.tiles[level["short"]] = self.tile(level, row, column)
                row += 1

    def tile(self, level, row, column):
        frame = tk.Frame(self.grid, bg=theme.SURFACE, width=152, height=46, cursor="hand2")
        frame.grid(row=row, column=column, padx=4, pady=3)
        frame.grid_propagate(False)
        bar = tk.Frame(frame, bg=theme.AXIS, width=3)
        bar.place(x=0, y=0, relheight=1)
        name = tk.Label(frame, text=level["short"], bg=theme.SURFACE, fg=theme.INK, font=(theme.DISPLAY, 12))
        name.place(x=12, y=3)
        time = tk.Label(frame, text="", bg=theme.SURFACE, fg=theme.MUTED, font=(theme.FONT, 9))
        time.place(x=12, y=24)
        parts = (frame, name, time)

        def paint(colour):
            for widget in parts:
                widget.config(bg=colour)

        for widget in parts:
            widget.bind("<Button-1>", lambda _, short=level["short"]: self.on_pick(short))
            widget.bind("<Enter>", lambda _: paint(theme.RAISED))
            widget.bind("<Leave>", lambda _: paint(theme.SURFACE))
        return bar, name, time

    def update(self, best, tried):
        author_count = 0
        for level in self.levels:
            short = level["short"]
            bar, name, time = self.tiles[short]
            value = best.get(short)
            if value is not None and value <= level["author"]:
                colour, text = theme.TEAL, f"{show_time(value)}  author {show_time(level['author'])}"
                author_count += 1
            elif value is not None:
                colour, text = theme.INK, f"{show_time(value)}  +{value - level['author']:.2f}"
            elif short in tried:
                colour, text = theme.WARNING, "no finish yet"
            else:
                colour, text = theme.AXIS, "not reached"
            bar.config(bg=colour)
            time.config(text=text, fg=theme.INK_2 if value is not None else theme.MUTED)
        self.summary.config(text=f"{len(best)} of {len(self.levels)} finished, {author_count} beat the author time")
