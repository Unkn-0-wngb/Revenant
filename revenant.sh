#!/usr/bin/env bash
root="$(cd "$(dirname "$0")" && pwd)"
cd "$root" || exit 1
if ! [ -x venv/bin/python ] || ! venv/bin/python -c "import torch, matplotlib, tensorboard, psutil, joblib, lzo, PIL, tkinter" 2>/dev/null; then
    bash "$root/setup.sh" || { echo "Setup failed, see the messages above."; exit 1; }
fi
nohup venv/bin/python "$root/dashboard.py" >/dev/null 2>&1 &
