"""Looks at this PC, benchmarks the AI's network on its GPU and works out settings that suit it.
Run with --benchmark to print the results as JSON (the dashboard does this in the background)."""
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import winreg

import psutil

import paths

RESULTS = os.path.join(paths.ROOT, "machine.json")
CONFIG = os.path.join(paths.LINESIGHT, "config_files", "config.py")
CONFIG_COPY = os.path.join(paths.LINESIGHT, "config_files", "config_copy.py")
GB = 2**30


def make_config_copy():
    if not os.path.exists(CONFIG_COPY):
        shutil.copyfile(CONFIG, CONFIG_COPY)


def cpu_name():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except OSError:
        return platform.processor()


def gpu_from_nvidia_smi():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, creationflags=0x08000000,
        ).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out:
        return None
    name, memory, driver = [part.strip() for part in out[0].split(",")]
    return {"name": name, "vram_gb": round(int(memory) / 1024, 1), "driver": driver}


def hardware():
    memory = psutil.virtual_memory()
    disk = shutil.disk_usage(paths.ROOT)
    return {
        "cpu": cpu_name(),
        "cores": psutil.cpu_count(logical=False) or os.cpu_count(),
        "threads": os.cpu_count(),
        "ram_gb": round(memory.total / GB, 1),
        "ram_free_gb": round(memory.available / GB, 1),
        "disk_free_gb": round(disk.free / GB, 1),
        "gpu": gpu_from_nvidia_smi(),
        "windows": platform.version(),
    }


def benchmark():
    make_config_copy()
    sys.path.insert(0, paths.LINESIGHT)
    import torch

    if not torch.cuda.is_available():
        return {"cuda": False}
    from config_files import config_copy as config
    from trackmania_rl.agents.iqn import make_untrained_iqn_network

    torch.backends.cudnn.benchmark = True
    _, network = make_untrained_iqn_network(False, False)
    network.train()
    optimizer = torch.optim.RAdam(network.parameters(), lr=1e-4)
    scaler = torch.amp.GradScaler("cuda")
    batch = config.batch_size
    frames = torch.randint(0, 255, (batch, 1, config.H_downsized, config.W_downsized), device="cuda", dtype=torch.uint8)
    floats = torch.randn((batch, config.float_input_dim), device="cuda")
    torch.cuda.reset_peak_memory_stats()

    def train_step():
        optimizer.zero_grad(set_to_none=True)
        with torch.amp.autocast("cuda"):
            q, _ = network((frames.float() - 128) / 128, floats, config.iqn_n)
            loss = (q.float() ** 2).mean()
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

    for _ in range(5):
        train_step()
    torch.cuda.synchronize()
    start = time.perf_counter()
    rounds = 30
    for _ in range(rounds):
        train_step()
    torch.cuda.synchronize()
    batch_ms = (time.perf_counter() - start) / rounds * 1000
    peak_gb = torch.cuda.max_memory_allocated() / GB

    network.eval()
    one_frame = frames[:1]
    one_float = floats[:1]
    with torch.no_grad(), torch.amp.autocast("cuda"):
        for _ in range(10):
            network((one_frame.float() - 128) / 128, one_float, config.iqn_k)
        torch.cuda.synchronize()
        start = time.perf_counter()
        for _ in range(100):
            network((one_frame.float() - 128) / 128, one_float, config.iqn_k)
        torch.cuda.synchronize()
    action_ms = (time.perf_counter() - start) / 100 * 1000
    props = torch.cuda.get_device_properties(0)
    return {
        "cuda": True,
        "gpu": props.name,
        "vram_gb": round(props.total_memory / GB, 1),
        "batch_size": batch,
        "train_batch_ms": round(batch_ms, 1),
        "action_ms": round(action_ms, 2),
        "learner_vram_gb": round(peak_gb, 2),
    }


def recommend(hw, bench):
    notes = []
    vram = (bench or {}).get("vram_gb") or ((hw.get("gpu") or {}).get("vram_gb")) or 0
    batch_ms = (bench or {}).get("train_batch_ms")
    learner = (bench or {}).get("learner_vram_gb", 2.0)
    by_cpu = max(1, hw["threads"] // 4)
    by_ram = max(1, int((hw["ram_gb"] - 4) // 3))
    by_vram = max(1, int((vram - learner - 1.0) // 0.6)) if vram else 1
    games = max(1, min(4, by_cpu, by_ram, by_vram))
    limit = min((by_cpu, "CPU cores"), (by_ram, "RAM"), (by_vram, "graphics memory"))[1]
    notes.append(f"{games} game{'s' if games > 1 else ''}, limited by {limit}.")

    if vram >= 6:
        batch = 512
    elif vram >= 4:
        batch = 256
    else:
        batch = 128
    if batch < 512:
        notes.append(f"Batch size {batch} to fit in {vram} GB of graphics memory.")

    spare_ram = hw["ram_gb"] - 4 - games * 2
    memory = int(max(20_000, min(100_000, spare_ram * 0.6 / 0.045 * 1000)) // 5000 * 5000)
    notes.append(f"Replay memory {memory:,} steps for {hw['ram_gb']} GB of RAM.")

    if batch_ms is None:
        reuse = 16
    elif batch_ms < 60:
        reuse = 32
    elif batch_ms < 160:
        reuse = 16
    else:
        reuse = 8
    if batch_ms is not None:
        notes.append(f"A training batch takes {batch_ms} ms here, so each memory is reused {reuse} times.")

    speed = 80 if hw["threads"] >= 8 else 60 if hw["threads"] >= 6 else 40
    if speed < 80:
        notes.append(f"Game speed {speed}x so {hw['threads']} CPU threads can keep up.")
    return {
        "gpu_collectors_count": games,
        "batch_size": batch,
        "memory_size_schedule": [(0, (memory, int(memory * 0.7) // 5000 * 5000))],
        "number_times_single_memory_is_used_before_discard": reuse,
        "running_speed": speed,
    }, notes


def load():
    if os.path.exists(RESULTS):
        with open(RESULTS, encoding="utf-8") as f:
            return json.load(f)
    return None


def run_and_save():
    hw = hardware()
    bench = None
    error = None
    try:
        out = subprocess.run([paths.VENV_PYTHON if os.path.exists(paths.VENV_PYTHON) else sys.executable, os.path.join(paths.ROOT, "machine.py"), "--benchmark"],
                             capture_output=True, text=True, timeout=600, cwd=paths.ROOT, creationflags=0x08000000)
        line = [l for l in out.stdout.splitlines() if l.startswith("{")]
        bench = json.loads(line[-1]) if line else None
        if bench is None:
            error = (out.stderr or out.stdout).strip().splitlines()[-1:] or ["benchmark gave no result"]
            error = error[0]
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        error = str(e)
    settings, notes = recommend(hw, bench)
    result = {"when": time.strftime("%Y-%m-%d %H:%M"), "hardware": hw, "benchmark": bench, "error": error, "recommended": settings, "notes": notes}
    with open(RESULTS, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == "__main__":
    if "--benchmark" in sys.argv:
        print(json.dumps(benchmark()))
    else:
        print(json.dumps(run_and_save(), indent=2))
