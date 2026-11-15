#!/usr/bin/env bash
prefix="${WINEPREFIX:-$HOME/.wine}"
loader="$prefix/drive_c/users/$USER/AppData/Local/TMLoader/TMLoader.exe"
if [ ! -f "$loader" ]; then
    echo "TMLoader isn't installed in $prefix. Run the Setup tab in the dashboard first." >&2
    exit 1
fi
cd "$(dirname "$loader")" || exit 1
if command -v gamemoderun >/dev/null 2>&1; then
    exec gamemoderun wine "$loader" run TmForever "${2:-default}" /configstring="set custom_port $1"
fi
exec wine "$loader" run TmForever "${2:-default}" /configstring="set custom_port $1"
