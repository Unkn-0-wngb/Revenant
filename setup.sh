#!/usr/bin/env bash
set -e
root="$(cd "$(dirname "$0")" && pwd)"
cd "$root"

echo "Revenant setup: Python and the AI libraries. The first run downloads about 3 GB."

missing=()
python=""
for candidate in python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)' 2>/dev/null; then
        python="$candidate"
        break
    fi
done
[ -z "$python" ] && missing+=("python3.11 python3.11-venv python3.11-dev")
[ -n "$python" ] && ! "$python" -c 'import tkinter' 2>/dev/null && missing+=("python3-tk")
[ -n "$python" ] && ! "$python" -c 'import venv, ensurepip' 2>/dev/null && missing+=("python3.11-venv")
command -v wine >/dev/null 2>&1 || missing+=("wine")
command -v xdotool >/dev/null 2>&1 || missing+=("xdotool")
ldconfig -p 2>/dev/null | grep -q libxdo.so || missing+=("libxdo3")
ldconfig -p 2>/dev/null | grep -q liblzo2.so || missing+=("liblzo2-dev")

if [ ${#missing[@]} -gt 0 ]; then
    echo
    echo "Install these first, then run this again:"
    echo "  sudo apt install ${missing[*]} build-essential"
    echo "(On Fedora or Arch the package names are similar. Python must be 3.11.)"
    exit 1
fi
echo "Python: $(command -v "$python")"

[ -x venv/bin/python ] || "$python" -m venv venv
v="$root/venv/bin/python"
"$v" -m pip install --upgrade pip --quiet
if [ "${REVENANT_CPU_TORCH:-0}" = "1" ]; then
    "$v" -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
else
    "$v" -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
fi
"$v" -m pip install -c "$root/constraints.txt" torchrl==0.6.0 tensordict==0.6.1 tensorboard
(cd "$root/linesight" && "$v" -m pip install -c "$root/constraints.txt" -e .)
"$v" -m pip install psutil matplotlib python-lzo==1.15 pygbx==0.3 scipy opencv-python pillow joblib
chmod +x "$root/launch_game.sh" "$root/revenant.sh" "$root/train.sh"

"$v" -c "import torch; print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none that CUDA can use')"
echo "Python is ready. ./revenant.sh opens the dashboard, its Setup tab does the rest."
