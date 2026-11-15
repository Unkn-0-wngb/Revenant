#!/usr/bin/env bash
root="$(cd "$(dirname "$0")" && pwd)"
if pgrep -f TmForever.exe >/dev/null 2>&1; then
    echo "Trackmania is running. Close it first: training would force-close it."
    exit 1
fi
maps="$(cd "$root" && venv/bin/python -c 'import paths; print(paths.OFFICIAL_MAPS)')"
needed="$(grep -c '^    (' "$root/linesight/config_files/all_maps.py")"
found="$(ls "$maps"/*.Challenge.Gbx 2>/dev/null | wc -l)"
if [ "$found" -lt "$needed" ]; then
    echo "Only $found of $needed map files found. Run scripts/tools/get_official_maps.py first."
    exit 1
fi
mkdir -p "$root/logs"
log="$root/logs/train_run1.log"
[ -f "$log" ] && cp "$log" "$root/logs/train_before_$(date +%Y%m%d_%H%M%S).log"
cd "$root/linesight" || exit 1
export PYTHONUNBUFFERED=1
export PYTHONPATH="$root/linesight"
exec "$root/venv/bin/python" scripts/train.py >"$log" 2>&1
