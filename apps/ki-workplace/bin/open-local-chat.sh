#!/usr/bin/env bash
# Open Open WebUI in a dedicated local app window and free the GPU first.
set -euo pipefail

URL="http://127.0.0.1:3000"
WORKPLACE_URL="http://127.0.0.1:8790"
BRAVE="/home/mike/.local/bin/brave-browser"
PROFILE="/srv/ai/cache/brave/local-chat"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
APP_LOCK="$RUNTIME_DIR/local-chat-app.lock"
OTHER_LOCK="$RUNTIME_DIR/ki-workplace-app.lock"

exec 9>"$APP_LOCK"
if ! flock -n 9; then
  exit 0
fi

systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE 2>/dev/null || true

# Text mode owns the GPU. ComfyUI is stopped before a chat model can load.
if systemctl --user is-active --quiet comfyui.service; then
  systemctl --user stop comfyui.service
fi
systemctl --user start open-webui.service
systemctl --user start ki-workplace.service

ready=0
for _ in $(seq 1 80); do
  if curl -sf -o /dev/null "$URL"; then
    ready=1
    break
  fi
  sleep 0.25
done

if [[ "$ready" != "1" ]]; then
  if command -v kdialog >/dev/null 2>&1; then
    kdialog --title "Lokaler Chat" --sorry "Der lokale Chat startet nicht.\nStatus: systemctl --user status open-webui.service"
  fi
  exit 1
fi

if [[ ! -x "$BRAVE" ]]; then
  BRAVE="$(command -v brave-browser || command -v brave || true)"
fi
if [[ -z "$BRAVE" ]]; then
  if command -v kdialog >/dev/null 2>&1; then
    kdialog --title "Lokaler Chat" --sorry "Brave Browser wurde nicht gefunden."
  fi
  exit 1
fi

mkdir -p "$PROFILE"
"$BRAVE" \
  --user-data-dir="$PROFILE" \
  --app="$URL" \
  --new-window \
  --no-first-run \
  --disable-background-mode \
  --class=Lokaler-Chat >/dev/null 2>&1 &
browser_pid=$!
wait "$browser_pid" || true

# Keep another open AI window working. Otherwise release the GPU completely.
exec 8>"$OTHER_LOCK"
if flock -n 8; then
  curl -sf --max-time 360 -X POST "$WORKPLACE_URL/api/gpu/cleanup" >/dev/null 2>&1 || true
fi
