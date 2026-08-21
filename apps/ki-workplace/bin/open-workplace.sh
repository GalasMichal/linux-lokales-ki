#!/usr/bin/env bash
# Open the local workplace in a dedicated Brave app window.
set -euo pipefail

URL="http://127.0.0.1:8790"
BRAVE="/home/mike/.local/bin/brave-browser"
PROFILE="/srv/ai/cache/brave/ki-workplace"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
APP_LOCK="$RUNTIME_DIR/ki-workplace-app.lock"
OTHER_LOCK="$RUNTIME_DIR/local-chat-app.lock"

exec 9>"$APP_LOCK"
if ! flock -n 9; then
  exit 0
fi

systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE 2>/dev/null || true
systemctl --user start ki-workplace.service

ready=0
for _ in $(seq 1 40); do
  if curl -sf -o /dev/null "$URL"; then
    ready=1
    break
  fi
  sleep 0.25
done

if [[ "$ready" != "1" ]]; then
  if command -v kdialog >/dev/null 2>&1; then
    kdialog --title "KI-Arbeitsplatz" --sorry "Der KI-Arbeitsplatz startet nicht.\nStatus: systemctl --user status ki-workplace.service"
  fi
  exit 1
fi

if [[ ! -x "$BRAVE" ]]; then
  BRAVE="$(command -v brave-browser || command -v brave || true)"
fi
if [[ -z "$BRAVE" ]]; then
  if command -v kdialog >/dev/null 2>&1; then
    kdialog --title "KI-Arbeitsplatz" --sorry "Brave Browser wurde nicht gefunden."
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
  --class=KI-Arbeitsplatz >/dev/null 2>&1 &
browser_pid=$!
wait "$browser_pid" || true

# Only the last closed AI window releases all GPU consumers.
exec 8>"$OTHER_LOCK"
if flock -n 8; then
  curl -sf --max-time 360 -X POST "$URL/api/gpu/cleanup" >/dev/null 2>&1 || true
fi
