import time
import tkinter as tk

import numpy as np
from PIL import Image, ImageTk

import theme

LEAN = 0.16
HOLD_BADGE_S = 0.6
LETTER_S = 0.13
HOLD_WORD_S = 0.35
LONGEST_WAIT_S = 8
GLIDE_S = 0.7
FADE_S = 0.5
FRAME_MS = 15


def upright_runs(image):
    alpha = np.asarray(image)[..., 3] > 40
    height, width = alpha.shape
    pad = int(LEAN * height) + 2
    upright = np.zeros(width + pad * 2, bool)
    for y in range(height):
        xs = np.nonzero(alpha[y])[0] + int(round(LEAN * (y - height / 2))) + pad
        upright[xs] = True
    runs, start = [], None
    for x, on in enumerate(upright):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append((start - pad, x - pad))
            start = None
    return runs


def ease(t):
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Intro:
    def __init__(self, root, art, target, ready, done):
        self.root = root
        self.target = target
        self.ready = ready
        self.done = done
        self.full = Image.open(art).convert("RGBA")

        self.canvas = tk.Canvas(root, bg=theme.PAGE, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(self.canvas)
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        self.caret = self.canvas.create_polygon(0, 0, 0, 0, 0, 0, fill=theme.TEAL, outline="")
        self.photo = None

        root.update_idletasks()
        self.cap = max(48, min(88, int(root.winfo_height() * 0.11)))
        self.big = self.full.resize((round(self.full.width * self.cap / self.full.height), self.cap), Image.LANCZOS)
        runs = upright_runs(self.big)
        self.cuts = [(a[1] + b[0]) / 2 for a, b in zip(runs, runs[1:])] + [runs[-1][1] + 2]
        self.frames = [self.reveal(count) for count in range(len(self.cuts))]
        self.started = time.perf_counter()
        self.typed_at = None
        self.tick()

    def reveal(self, count):
        height = self.big.height
        ys = np.arange(height)[:, None]
        xs = np.arange(self.big.width)[None, :]
        keep = xs + LEAN * (ys - height / 2) <= self.cuts[count]
        rgba = np.asarray(self.big).copy()
        rgba[..., 3] = rgba[..., 3] * keep
        image = Image.fromarray(rgba, "RGBA")
        right = image.getbbox()[2]
        return ImageTk.PhotoImage(image.crop((0, 0, right, height))), right

    def place(self, photo, x, y):
        self.photo = photo
        self.canvas.itemconfig(self.item, image=photo)
        self.canvas.coords(self.item, round(x), round(y))

    def draw_caret(self, x, y, on):
        if not on:
            self.canvas.coords(self.caret, 0, 0, 0, 0, 0, 0)
            return
        h, w = self.cap, max(3, self.cap * 0.07)
        self.canvas.coords(self.caret, x + LEAN * h, y, x + LEAN * h + w, y, x + w, y + h, x, y + h)

    def tick(self):
        now = time.perf_counter() - self.started
        letters = 0 if now < HOLD_BADGE_S else min(len(self.cuts) - 1, int((now - HOLD_BADGE_S) / LETTER_S) + 1)
        photo, right = self.frames[letters]
        x = (self.root.winfo_width() - right) / 2
        y = (self.root.winfo_height() - self.cap) / 2
        self.place(photo, x, y)
        typing = letters < len(self.cuts) - 1
        blink = int(now / 0.4) % 2 == 0
        self.draw_caret(x + right + self.cap * 0.1, y, (letters > 0 or blink) if typing else blink)
        if typing:
            self.root.after(FRAME_MS, self.tick)
            return
        if self.typed_at is None:
            self.typed_at = now
        if now - self.typed_at >= HOLD_WORD_S and (self.ready() or now - self.typed_at > LONGEST_WAIT_S):
            self.draw_caret(0, 0, False)
            self.root.update_idletasks()
            self.glide_from = (x, y, self.cap)
            self.glide_start = time.perf_counter()
            self.glide()
            return
        self.root.after(FRAME_MS * 2, self.tick)

    def glide(self):
        t = min(1.0, (time.perf_counter() - self.glide_start) / GLIDE_S)
        k = ease(t)
        x0, y0, h0 = self.glide_from
        x1, y1, h1 = self.target()
        h = h0 + (h1 - h0) * k
        size = (max(1, round(self.full.width * h / self.full.height)), max(1, round(h)))
        image = self.full.resize(size, Image.LANCZOS if t >= 1 else Image.BILINEAR)
        self.place(ImageTk.PhotoImage(image), x0 + (x1 - x0) * k, y0 + (y1 - y0) * k)
        if t < 1:
            self.root.after(FRAME_MS, self.glide)
            return
        self.start_fade(image, x1, y1)

    def start_fade(self, image, x, y):
        self.veil = tk.Toplevel(self.root)
        self.veil.withdraw()
        self.veil.overrideredirect(True)
        self.veil.configure(bg=theme.PAGE)
        self.veil.attributes("-alpha", 1.0)
        width, height = self.root.winfo_width(), self.root.winfo_height()
        self.veil.geometry(f"{width}x{height}+{self.root.winfo_rootx()}+{self.root.winfo_rooty()}")
        canvas = tk.Canvas(self.veil, bg=theme.PAGE, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        self.veil_photo = ImageTk.PhotoImage(image)
        canvas.create_image(round(x), round(y), anchor="nw", image=self.veil_photo)
        self.veil.deiconify()
        self.veil.lift(self.root)
        self.veil.update()
        self.canvas.destroy()
        self.fade_start = time.perf_counter()
        self.fade()

    def fade(self):
        t = min(1.0, (time.perf_counter() - self.fade_start) / FADE_S)
        self.veil.attributes("-alpha", 1 - ease(t))
        if t < 1:
            self.root.after(FRAME_MS, self.fade)
            return
        self.veil.destroy()
        self.done()
