import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import checks
import controls
import machine

STATUS_EVERY_MS = 3000
FRIENDLY = {
    "gpu_collectors_count": "Games at once",
    "batch_size": "Training batch size",
    "memory_size_schedule": "Replay memory (max / start)",
    "number_times_single_memory_is_used_before_discard": "Times each memory is reused",
    "running_speed": "Game speed",
}


class ControlWindow:
    def __init__(self, parent, colors, font):
        self.c = colors
        self.font = font
        self.window = tk.Toplevel(parent)
        self.window.title("Revenant controls")
        self.window.geometry("660x720")
        self.window.minsize(600, 600)
        self.window.configure(bg=colors["page"])

        style = ttk.Style(self.window)
        style.configure("TNotebook", background=colors["page"], borderwidth=0)
        style.configure("TNotebook.Tab", background=colors["surface"], foreground=colors["ink_2"], padding=(14, 6), font=(font, 10))
        style.map("TNotebook.Tab", background=[("selected", colors["grid"])], foreground=[("selected", colors["ink"])])
        style.configure("TButton", background=colors["grid"], foreground=colors["ink"], bordercolor=colors["axis"], font=(font, 10), padding=(10, 4))
        style.map("TButton", background=[("active", colors["axis"])])
        style.configure("Treeview", background=colors["surface"], fieldbackground=colors["surface"], foreground=colors["ink"], rowheight=22, font=(font, 10), bordercolor=colors["axis"])
        style.configure("Treeview.Heading", background=colors["grid"], foreground=colors["ink_2"], font=(font, 10))
        style.map("Treeview", background=[("selected", colors["axis"])])
        style.configure("Accent.TButton", background=colors["teal"], foreground=colors["page"], bordercolor=colors["teal"], font=(font, 10, "bold"), padding=(14, 4))
        style.map("Accent.TButton", background=[("disabled", colors["grid"]), ("active", "#5ff0dc")], foreground=[("disabled", colors["muted"])])
        style.map("TButton", foreground=[("disabled", colors["muted"])])

        self.levels = controls.levels()
        self.level_names = [short for short, _ in self.levels]
        self.author = dict(self.levels)

        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.setup_tab = self.frame(self.tabs)
        self.run_tab = self.frame(self.tabs)
        self.machine_tab = self.frame(self.tabs)
        self.settings_tab = self.frame(self.tabs)
        self.profile_tab = self.frame(self.tabs)
        self.tabs.add(self.setup_tab, text="Setup")
        self.tabs.add(self.run_tab, text="Run")
        self.tabs.add(self.machine_tab, text="Machine")
        self.tabs.add(self.settings_tab, text="Settings")
        self.tabs.add(self.profile_tab, text="Profile")

        self.message = tk.Label(self.window, text="Ready.", bg=colors["surface"], fg=colors["ink_2"], font=(font, 10), anchor="w", justify="left", wraplength=620, padx=12, pady=8)
        self.message.pack(fill="x", padx=8, pady=8)

        self.build_setup()
        self.build_run()
        self.build_machine()
        self.build_settings()
        self.build_profile()
        self.refresh_status()
        self.tabs.select(self.setup_tab if not all(ok for _, ok, *_ in checks.run_all()) else self.run_tab)

    def build_setup(self):
        tab = self.setup_tab
        self.label(tab, "Everything Revenant needs on this PC", 11, self.c["ink"], True).pack(fill="x")
        self.setup_summary = self.label(tab, "", 10, self.c["ink_2"])
        self.setup_summary.pack(fill="x", pady=(2, 0))
        self.check_rows = tk.Frame(tab, bg=tab["bg"])
        self.check_rows.pack(fill="x", pady=6)
        buttons = tk.Frame(tab, bg=tab["bg"])
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Check again", command=self.fill_checks).pack(side="left")
        ttk.Button(buttons, text="Fix everything I can", command=self.fix_all).pack(side="left", padx=8)
        ttk.Button(buttons, text="Install models from a folder...", command=self.models_from_folder).pack(side="left")
        self.fill_checks()

    def fill_checks(self):
        for row in self.check_rows.winfo_children():
            row.destroy()
        results = checks.run_all()
        missing = sum(not ok for _, ok, *_ in results)
        if missing:
            self.setup_summary.config(text=f"{missing} thing{'s' if missing > 1 else ''} to sort out. Each one has a button, or try Fix everything I can.", fg=self.c["warning"])
        else:
            self.setup_summary.config(text="All set. Revenant is ready to train on this PC.", fg=self.c["good"])
        for i, (name, ok, detail, fix, label) in enumerate(results):
            mark = tk.Label(self.check_rows, text="✓" if ok else "✗", bg=self.c["page"], fg=self.c["good"] if ok else self.c["warning"], font=(self.font, 12, "bold"), width=2)
            mark.grid(row=i, column=0, sticky="w")
            self.label(self.check_rows, name, 10, self.c["ink"]).grid(row=i, column=1, sticky="w", padx=(0, 10))
            info = self.label(self.check_rows, detail, 9, self.c["muted"])
            info.config(wraplength=300)
            info.grid(row=i, column=2, sticky="w")
            if not ok:
                ttk.Button(self.check_rows, text=label, command=lambda fix=fix: self.run_fix(fix)).grid(row=i, column=3, sticky="e", padx=(8, 0), pady=1)
        self.check_rows.columnconfigure(2, weight=1)

    def run_fix(self, fix):
        self.say(fix())
        self.window.after(800, self.fill_checks)

    def fix_all(self):
        self.say(checks.fix_everything())
        self.fill_checks()

    def models_from_folder(self):
        folder = filedialog.askdirectory(parent=self.window, title="Folder with the Revenant model zips")
        if folder:
            self.say(checks.install_models(folder))
            self.fill_checks()

    def build_machine(self):
        tab = self.machine_tab
        self.label(tab, "This PC", 11, self.c["ink"], True).pack(fill="x")
        self.hardware_text = self.label(tab, "", 10, self.c["ink_2"])
        self.hardware_text.pack(fill="x", pady=(2, 8))
        self.bench_text = self.label(tab, "", 10, self.c["ink_2"])
        self.bench_text.config(wraplength=560)
        self.bench_text.pack(fill="x")
        self.label(tab, "Recommended settings", 11, self.c["ink"], True).pack(fill="x", pady=(10, 2))
        self.advice = ttk.Treeview(tab, columns=("now", "suggested"), show="tree headings", height=5)
        self.advice.heading("#0", text="Setting")
        self.advice.heading("now", text="Now")
        self.advice.heading("suggested", text="For this PC")
        self.advice.column("#0", width=250)
        self.advice.column("now", width=150)
        self.advice.column("suggested", width=150)
        self.advice.pack(fill="x")
        self.notes = self.label(tab, "", 9, self.c["muted"])
        self.notes.config(wraplength=560)
        self.notes.pack(fill="x", pady=6)
        buttons = tk.Frame(tab, bg=tab["bg"])
        buttons.pack(fill="x")
        self.bench_button = ttk.Button(buttons, text="Benchmark this PC", command=self.run_benchmark)
        self.bench_button.pack(side="left")
        ttk.Button(buttons, text="Use these settings", command=self.apply_recommended).pack(side="left", padx=8)
        self.show_machine()

    def show_machine(self):
        result = machine.load()
        if not result:
            self.hardware_text.config(text="Not checked yet. Press Benchmark this PC (takes about a minute, training should be stopped).")
            self.bench_text.config(text="")
            self.advice.delete(*self.advice.get_children())
            self.notes.config(text="")
            return
        hw = result["hardware"]
        gpu = hw.get("gpu") or {}
        self.hardware_text.config(text=(
            f"{hw['cpu']}, {hw['cores']} cores / {hw['threads']} threads\n"
            f"{hw['ram_gb']} GB RAM, {hw['disk_free_gb']} GB free disk\n"
            f"{gpu.get('name', 'no NVIDIA GPU')}{', ' + str(gpu.get('vram_gb')) + ' GB' if gpu else ''}"
        ))
        bench = result.get("benchmark")
        if bench and bench.get("cuda"):
            self.bench_text.config(text=f"Training batch of {bench['batch_size']}: {bench['train_batch_ms']} ms.  One driving decision: {bench['action_ms']} ms.  Learner uses {bench['learner_vram_gb']} GB of graphics memory.  ({result['when']})")
        else:
            self.bench_text.config(text=f"Benchmark failed: {result.get('error') or 'no CUDA GPU'}")
        self.advice.delete(*self.advice.get_children())
        recommended, notes = machine.recommend(hw, bench)
        for name, value in recommended.items():
            now = controls.current(name)
            self.advice.insert("", "end", iid=name, text=FRIENDLY.get(name, name), values=(self.short(now), self.short(value)))
        self.notes.config(text="  ".join(notes))

    def short(self, value):
        if isinstance(value, list) and value and isinstance(value[0], (list, tuple)):
            return f"{value[0][1][0]:,} / {value[0][1][1]:,}"
        return str(value)

    def run_benchmark(self):
        if controls.training_running():
            self.say("Stop training first, the benchmark needs the graphics card to itself.", self.c["warning"])
            return
        self.bench_button.config(state="disabled")
        self.say("Benchmarking... this takes about a minute.")

        def work():
            machine.run_and_save()
            self.window.after(0, lambda: (self.show_machine(), self.bench_button.config(state="normal"), self.say("Benchmark done."), self.fill_checks()))

        threading.Thread(target=work, daemon=True).start()

    def apply_recommended(self):
        result = machine.load()
        if not result:
            self.say("Run the benchmark first.", self.c["warning"])
            return
        said = []
        for name, value in machine.recommend(result["hardware"], result.get("benchmark"))[0].items():
            if name == "gpu_collectors_count" and controls.training_running():
                said.append("The number of games changes on the next start.")
            said.append(controls.set_setting(name, repr(value)))
        self.say(" ".join(said))
        self.show_machine()
        self.fill_settings()

    def frame(self, parent):
        return tk.Frame(parent, bg=self.c["page"], padx=10, pady=10)

    def label(self, parent, text, size=10, color=None, bold=False):
        return tk.Label(parent, text=text, bg=parent["bg"], fg=color or self.c["ink_2"], font=(self.font, size, "bold" if bold else "normal"), anchor="w", justify="left")

    def section(self, parent, title):
        box = tk.Frame(parent, bg=self.c["surface"], padx=12, pady=8)
        box.pack(fill="x", pady=4)
        self.label(box, title, 11, self.c["ink"], True).grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 4))
        return box

    def entry(self, parent, value, width=8):
        field = tk.Entry(parent, width=width, bg=self.c["page"], fg=self.c["ink"], insertbackground=self.c["ink"], relief="flat", font=(self.font, 10))
        field.insert(0, str(value))
        return field

    def picker(self, parent, values, value, width=8):
        box = ttk.Combobox(parent, values=values, state="readonly", width=width, font=(self.font, 10))
        box.set(value)
        return box

    def say(self, text, color=None):
        self.message.config(text=text, fg=color or self.c["ink_2"])

    def build_run(self):
        tab = self.run_tab
        self.state_line = self.label(tab, "Checking...", 12, self.c["ink"], True)
        self.state_line.pack(fill="x")
        self.status = self.label(tab, "", 10, self.c["ink_2"])
        self.status.pack(fill="x", pady=(0, 6))

        box = self.section(tab, "Training")
        self.start_button = ttk.Button(box, text="Start", style="Accent.TButton", command=self.start_training)
        self.start_button.grid(row=1, column=0, padx=(0, 6))
        self.stop_button = ttk.Button(box, text="Stop after next save", command=lambda: (self.say("Stopping after the next save..."), controls.stop_training(self.later)))
        self.stop_button.grid(row=1, column=1, padx=6)
        self.stop_now_button = ttk.Button(box, text="Stop now", command=self.stop_now)
        self.stop_now_button.grid(row=1, column=2, padx=6)
        links = tk.Frame(box, bg=box["bg"])
        links.grid(row=2, column=0, columnspan=8, sticky="w", pady=(6, 0))
        ttk.Button(links, text="Open training log", command=self.open_log).pack(side="left", padx=(0, 6))
        ttk.Button(links, text="Open project folder", command=lambda: os.startfile(controls.ROOT)).pack(side="left")

        box = self.section(tab, "Focus on one level")
        level, target = controls.focus()
        self.focus_level = self.picker(box, ["none"] + self.level_names, level or "none")
        self.focus_level.grid(row=1, column=0, padx=(0, 6))
        self.focus_level.bind("<<ComboboxSelected>>", self.fill_target)
        self.label(box, "until under").grid(row=1, column=1)
        self.focus_target = self.entry(box, target or "")
        self.focus_target.grid(row=1, column=2, padx=6)
        self.label(box, "s").grid(row=1, column=3)
        ttk.Button(box, text="Apply", command=self.apply_focus).grid(row=1, column=4, padx=6)
        self.label(box, "The loop jumps to this level and goes back when the time is beaten.", 9, self.c["muted"]).grid(row=2, column=0, columnspan=8, sticky="w", pady=(4, 0))

        box = self.section(tab, "Demo starts (play the follower's lap, then hand over to the AI)")
        self.demo_level = self.picker(box, self.level_names, level or "D02")
        self.demo_level.grid(row=1, column=0, padx=(0, 6))
        self.label(box, "steps").grid(row=1, column=1)
        self.demo_first = self.entry(box, 300, 6)
        self.demo_first.grid(row=1, column=2, padx=4)
        self.label(box, "to").grid(row=1, column=3)
        self.demo_last = self.entry(box, 780, 6)
        self.demo_last.grid(row=1, column=4, padx=4)
        self.label(box, "every").grid(row=1, column=5)
        self.demo_every = self.entry(box, 60, 5)
        self.demo_every.grid(row=1, column=6, padx=4)
        buttons = tk.Frame(box, bg=box["bg"])
        buttons.grid(row=2, column=0, columnspan=8, sticky="w", pady=(6, 0))
        ttk.Button(buttons, text="Start", command=self.start_demos).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Stop", command=lambda: self.say(controls.stop_helper("demo starts"))).pack(side="left")

        box = self.section(tab, "Lap follower (builds a demo lap on a third game)")
        self.follow_level = self.picker(box, self.level_names, "D02")
        self.follow_level.grid(row=1, column=0, padx=(0, 6))
        self.label(box, "minutes").grid(row=1, column=1)
        self.follow_minutes = self.entry(box, 600, 6)
        self.follow_minutes.grid(row=1, column=2, padx=6)
        ttk.Button(box, text="Start", command=lambda: self.say(controls.start_helper("lap follower", self.follow_level.get(), self.follow_minutes.get()))).grid(row=1, column=3, padx=6)
        ttk.Button(box, text="Stop", command=lambda: self.say(controls.stop_helper("lap follower"))).grid(row=1, column=4)

        box = self.section(tab, "Bruteforce (improves a level's best lap on a third game)")
        self.brute_level = self.picker(box, self.level_names, "A07")
        self.brute_level.grid(row=1, column=0, padx=(0, 6))
        self.label(box, "minutes").grid(row=1, column=1)
        self.brute_minutes = self.entry(box, 240, 6)
        self.brute_minutes.grid(row=1, column=2, padx=6)
        ttk.Button(box, text="Start", command=lambda: self.say(controls.start_helper("bruteforce", self.brute_level.get(), self.brute_minutes.get()))).grid(row=1, column=3, padx=6)
        ttk.Button(box, text="Stop", command=lambda: self.say(controls.stop_helper("bruteforce"))).grid(row=1, column=4)

    def start_training(self):
        message = controls.start_training()
        self.say(message, self.c["warning"] if "first" in message or "already" in message else None)

    def stop_now(self):
        if messagebox.askyesno("Stop now?", "Stop training straight away? Anything since the last save (up to 5 minutes) is lost.", parent=self.window):
            self.say("Stopping...")
            controls.stop_training(self.later, wait=False)

    def open_log(self):
        log = os.path.join(controls.ROOT, "logs", "train_run1.log")
        if os.path.exists(log):
            os.startfile(log)
        else:
            self.say("There's no training log yet. It appears once training has run.")

    def later(self, text):
        self.window.after(0, lambda: self.say(text))

    def fill_target(self, _):
        level = self.focus_level.get()
        self.focus_target.delete(0, "end")
        if level != "none" and self.author.get(level):
            self.focus_target.insert(0, str(self.author[level]))

    def apply_focus(self):
        level = self.focus_level.get()
        if level == "none":
            self.say(controls.set_setting("focus_level", '""'))
            return
        try:
            target = float(self.focus_target.get())
        except ValueError:
            self.say("The target needs to be a time in seconds, like 52.63.", self.c["warning"])
            return
        self.say(controls.set_focus(level, target))

    def start_demos(self):
        try:
            first, last, every = int(self.demo_first.get()), int(self.demo_last.get()), float(self.demo_every.get())
        except ValueError:
            self.say("Steps and seconds need to be numbers.", self.c["warning"])
            return
        level = self.demo_level.get()
        if not os.path.exists(os.path.join(controls.ROOT, "bruteforce", f"{level}_follow_partial.npy")):
            self.say(f"There is no demo lap for {level} yet. Run the lap follower on it first.", self.c["warning"])
            return
        self.say(controls.start_helper("demo starts", level, first, last, every))

    def refresh_status(self):
        if not self.window.winfo_exists():
            return
        s = controls.status()
        helpers = ", ".join(name for name, on in s["helpers"].items() if on and name != "clicker") or "none"
        level, target = s["focus"]
        focus = f"{level} until under {target}s" if level else "off"
        if s["training"]:
            self.state_line.config(text=f"● Training, {s['games']} game{'s' if s['games'] != 1 else ''} running", fg=self.c["good"])
        else:
            self.state_line.config(text="■ Stopped", fg=self.c["muted"])
        self.status.config(text=f"Focus: {focus}     Helpers: {helpers}     Profile: {s['profile']}")
        self.start_button.config(state="disabled" if s["training"] else "normal")
        self.stop_button.config(state="normal" if s["training"] else "disabled")
        self.stop_now_button.config(state="normal" if s["training"] or s["games"] else "disabled")
        self.window.after(STATUS_EVERY_MS, self.refresh_status)

    def build_settings(self):
        tab = self.settings_tab
        top = tk.Frame(tab, bg=tab["bg"])
        top.pack(fill="x")
        self.label(top, "Find").pack(side="left")
        self.search = self.entry(top, "", 24)
        self.search.pack(side="left", padx=6)
        self.search.bind("<KeyRelease>", lambda _: self.fill_settings())
        ttk.Button(top, text="Open config.py", command=lambda: os.startfile(controls.CONFIG)).pack(side="right")

        self.tree = ttk.Treeview(tab, columns=("value",), show="tree headings", height=12)
        self.tree.heading("#0", text="Setting")
        self.tree.heading("value", text="Value")
        self.tree.column("#0", width=230)
        self.tree.column("value", width=330)
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self.pick_setting)

        self.setting_note = self.label(tab, "Pick a setting to change it.", 9, self.c["muted"])
        self.setting_note.pack(fill="x")
        self.editor = tk.Text(tab, height=4, bg=self.c["surface"], fg=self.c["ink"], insertbackground=self.c["ink"], relief="flat", font=("Consolas", 10))
        self.editor.pack(fill="x", pady=4)
        bottom = tk.Frame(tab, bg=tab["bg"])
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Save", command=self.save_setting).pack(side="left")
        self.label(bottom, "Saved settings reach a running AI within a minute; a few only apply after a restart.", 9, self.c["muted"]).pack(side="left", padx=8)
        self.fill_settings()

    def fill_settings(self):
        wanted = self.search.get().lower()
        self.all_settings = {s["name"]: s for s in controls.settings()}
        self.tree.delete(*self.tree.get_children())
        for name, s in self.all_settings.items():
            if wanted in name.lower() or wanted in s["note"].lower():
                self.tree.insert("", "end", iid=name, text=name, values=(" ".join(s["value"].split()),))

    def pick_setting(self, _):
        chosen = self.tree.selection()
        if not chosen:
            return
        s = self.all_settings[chosen[0]]
        self.chosen = s["name"]
        self.setting_note.config(text=f"{s['name']}: {s['note']}" if s["note"] else s["name"])
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", s["value"])

    def save_setting(self):
        if not getattr(self, "chosen", None):
            self.say("Pick a setting first.", self.c["warning"])
            return
        result = controls.set_setting(self.chosen, self.editor.get("1.0", "end").strip())
        self.say(result, self.c["ink_2"] if " set to " in result else self.c["warning"])
        self.fill_settings()
        if self.chosen in self.all_settings:
            self.tree.selection_set(self.chosen)
            self.tree.see(self.chosen)

    def build_profile(self):
        tab = self.profile_tab
        self.label(tab, "Trackmania profile the AI drives with", 11, self.c["ink"], True).pack(fill="x")
        self.profile_now = self.label(tab, "")
        self.profile_now.pack(fill="x", pady=(4, 10))
        row = tk.Frame(tab, bg=tab["bg"])
        row.pack(fill="x")
        self.profile_pick = self.picker(row, controls.profiles(), controls.profile(), 20)
        self.profile_pick.pack(side="left")
        ttk.Button(row, text="Use this profile", command=self.use_profile).pack(side="left", padx=8)
        ttk.Button(row, text="Look again", command=self.reload_profiles).pack(side="left")
        ttk.Button(tab, text=f"Make and use {controls.AI_PROFILE}", command=self.use_ai_profile).pack(anchor="w", pady=(10, 0))
        help_text = (
            f"The dashboard makes a local {controls.AI_PROFILE} profile by itself (no online account) and switches the AI to it "
            "whenever training starts. Its controls and settings are copied from your own profile.\n\n"
            "The clicker presses the first profile in the game's list, so the AI's profile should be first."
        )
        help_label = self.label(tab, help_text, 9, self.c["muted"])
        help_label.config(wraplength=540)
        help_label.pack(fill="x", pady=12)
        self.show_profile()

    def show_profile(self):
        self.profile_now.config(text=f"Now driving as: {controls.profile()}")

    def reload_profiles(self):
        self.profile_pick.config(values=controls.profiles())
        self.say(f"Profiles found: {', '.join(controls.profiles()) or 'none'}")

    def use_ai_profile(self):
        self.say(controls.use_ai_profile())
        self.profile_pick.config(values=controls.profiles())
        self.profile_pick.set(controls.profile())
        self.show_profile()

    def use_profile(self):
        self.say(controls.set_profile(self.profile_pick.get()))
        self.show_profile()
