#!/usr/bin/env bash
# Stop the isolated :8189 ComfyUI process. Does not touch comfyui.service.
set -euo pipefail

NEW_TREE="/srv/ai/apps/ComfyUI-0.37.0"
PIDFILE="$NEW_TREE/isolated-8189.pid"

if [[ -f "$PIDFILE" ]]; then
  pid="$(cat "$PIDFILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" || true
    fi
  fi
  rm -f "$PIDFILE"
fi
# Leftover listener
if ss -lntp 2>/dev/null | grep -q '127.0.0.1:8189'; then
  pids="$(ss -lntp | awk '/127.0.0.1:8189/{print}' | grep -oP 'pid=\K[0-9]+' | sort -u)"
  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done
fi
printf '%s\n' "OK   isolated 8189 stopped"
