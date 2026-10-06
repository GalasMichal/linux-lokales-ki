#!/usr/bin/env bash
# Toggle "PC wach halten" (block sleep/idle). Desktop one-click switch.
set -euo pipefail

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/keep-awake"
PID_FILE="$STATE_DIR/inhibit.pid"
WHY="${KEEP_AWAKE_WHY:-PC wach halten (Desktop-Schalter)}"
WHO="Keep-Awake-Toggle"

notify() {
  local title="$1" body="$2" icon="$3"
  if command -v notify-send >/dev/null 2>&1; then
    notify-send --app-name="Wach halten" --icon="$icon" "$title" "$body" || true
  fi
  if command -v kdialog >/dev/null 2>&1; then
    # short non-blocking toast if available; ignore failures
    kdialog --title "$title" --passivepopup "$body" 3 2>/dev/null || true
  fi
}

is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' <"$PID_FILE" || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  # still our inhibit?
  local cmd
  cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  [[ "$cmd" == *systemd-inhibit* ]] || return 1
  return 0
}

turn_on() {
  mkdir -p "$STATE_DIR"
  if is_running; then
    notify "Wach halten" "Ist schon AN." "weather-clear"
    printf '%s\n' "AN (bereits aktiv)"
    return 0
  fi
  # stop stale pid file
  rm -f "$PID_FILE"
  nohup systemd-inhibit \
    --what=sleep:idle \
    --who="$WHO" \
    --why="$WHY" \
    --mode=block \
    sleep infinity >/dev/null 2>&1 &
  local pid=$!
  echo "$pid" >"$PID_FILE"
  sleep 0.2
  if is_running; then
    notify "Wach halten: AN" "PC geht nicht in Standby." "weather-clear"
    printf '%s\n' "AN (pid $pid)"
  else
    rm -f "$PID_FILE"
    notify "Wach halten: Fehler" "Konnte Standby nicht blockieren." "dialog-error"
    printf '%s\n' "FEHLER: inhibit startet nicht"
    return 1
  fi
}

turn_off() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(tr -d '[:space:]' <"$PID_FILE" || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      # also kill child sleep if needed
      pkill -P "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
  # cleanup leftover from older sessions with same who/why markers
  pkill -f "systemd-inhibit --what=sleep:idle --who=$WHO" 2>/dev/null || true
  pkill -f "systemd-inhibit --what=sleep:idle --who=Linux-Lokales-KI" 2>/dev/null || true
  notify "Wach halten: AUS" "Normaler Standby wieder erlaubt." "weather-few-clouds-night"
  printf '%s\n' "AUS"
}

status() {
  if is_running; then
    printf '%s\n' "AN"
    return 0
  fi
  printf '%s\n' "AUS"
  return 1
}

cmd="${1:-toggle}"
case "$cmd" in
  on|an|enable) turn_on ;;
  off|aus|disable) turn_off ;;
  status|zustand) status ;;
  toggle|umschalten|"")
    if is_running; then turn_off; else turn_on; fi
    ;;
  *)
    printf '%s\n' "Usage: $0 [toggle|on|off|status]"
    exit 2
    ;;
esac
