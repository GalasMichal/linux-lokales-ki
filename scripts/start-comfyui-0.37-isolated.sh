#!/usr/bin/env bash
# Start isolated ComfyUI 0.37.0 on 127.0.0.1:8189. Does not touch comfyui.service.
set -euo pipefail

NEW_TREE="/srv/ai/apps/ComfyUI-0.37.0"
VENV_033="/srv/ai/venvs/comfyui"
VENV_037="/srv/ai/venvs/comfyui-0.37"
LOG="$NEW_TREE/isolated-8189.log"
PIDFILE="$NEW_TREE/isolated-8189.pid"
python_bin="$VENV_033/bin/python"
if [[ -x "$VENV_037/bin/python" ]]; then
  python_bin="$VENV_037/bin/python"
fi

if [[ ! -x "$python_bin" || ! -f "$NEW_TREE/main.py" ]]; then
  printf '%s\n' "ABBRUCH: Tree oder Python fehlt."
  exit 1
fi
if ss -lntp 2>/dev/null | grep -q '127.0.0.1:8189'; then
  printf '%s\n' "OK   Port 8189 hört schon."
  exit 0
fi
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  printf '%s\n' "OK   Isolierter Prozess läuft schon."
  exit 0
fi

mkdir -p "$NEW_TREE/output"
: > "$LOG"
cd "$NEW_TREE"
nohup "$python_bin" main.py --listen 127.0.0.1 --port 8189 --output-directory "$NEW_TREE/output" "$@" >>"$LOG" 2>&1 &
echo $! > "$PIDFILE"
printf 'OK   pid %s log %s args=%s\n' "$(cat "$PIDFILE")" "$LOG" "$*"
