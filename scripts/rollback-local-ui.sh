#!/usr/bin/env bash
# Restore the UI state captured by deploy-local-ui.sh.
set -euo pipefail

BACKUP="${1:-}"
USER_UNITS="/home/mike/.config/systemd/user"
LOCAL_APPS="/home/mike/.local/share/applications"
DESKTOP="/home/mike/Schreibtisch"

restore_unit_state() {
  local unit=$1
  local enabled=""
  local active=""
  [[ -f "$BACKUP/unit-state/$unit.enabled" ]] && enabled="$(<"$BACKUP/unit-state/$unit.enabled")"
  [[ -f "$BACKUP/unit-state/$unit.active" ]] && active="$(<"$BACKUP/unit-state/$unit.active")"
  if [[ "$enabled" == "enabled" ]]; then
    systemctl --user enable "$unit" >/dev/null
  else
    systemctl --user disable "$unit" >/dev/null 2>&1 || true
  fi
  if [[ "$active" == "active" ]]; then
    systemctl --user start "$unit"
  else
    systemctl --user stop "$unit" >/dev/null 2>&1 || true
  fi
}

if [[ -z "$BACKUP" || ! -d "$BACKUP" ]]; then
  printf 'Aufruf: %s /mnt/ai-archive/backups/ki-ui/JJJJMMTT-HHMMSS\n' "$0"
  exit 1
fi

systemctl --user disable --now ki-workplace.service 2>/dev/null || true
systemctl --user disable --now qwen-code-web.service 2>/dev/null || true

if [[ -f "$BACKUP/user-units/ki-hub.service" ]]; then
  install -m 0644 "$BACKUP/user-units/ki-hub.service" "$USER_UNITS/ki-hub.service"
fi
if [[ -f "$BACKUP/desktop/KI-Zentrale.desktop.moved" ]]; then
  install -m 0755 "$BACKUP/desktop/KI-Zentrale.desktop.moved" "$DESKTOP/KI-Zentrale.desktop"
elif [[ -f "$BACKUP/desktop/KI-Zentrale.desktop" ]]; then
  install -m 0755 "$BACKUP/desktop/KI-Zentrale.desktop" "$DESKTOP/KI-Zentrale.desktop"
fi
if [[ -f "$BACKUP/local-applications/KI-Zentrale.desktop.moved" ]]; then
  install -m 0644 "$BACKUP/local-applications/KI-Zentrale.desktop.moved" "$LOCAL_APPS/KI-Zentrale.desktop"
elif [[ -f "$BACKUP/local-applications/KI-Zentrale.desktop" ]]; then
  install -m 0644 "$BACKUP/local-applications/KI-Zentrale.desktop" "$LOCAL_APPS/KI-Zentrale.desktop"
fi

install -d -m 0755 "$BACKUP/disabled-new-launchers"
for file in KI-Arbeitsplatz.desktop Lokaler-Chat.desktop; do
  if [[ -f "$DESKTOP/$file" ]]; then
    mv "$DESKTOP/$file" "$BACKUP/disabled-new-launchers/desktop-$file"
  fi
  if [[ -f "$LOCAL_APPS/$file" ]]; then
    mv "$LOCAL_APPS/$file" "$BACKUP/disabled-new-launchers/application-$file"
  fi
done

systemctl --user daemon-reload
restore_unit_state ki-hub.service
restore_unit_state comfyui.service
printf '%s\n' "ROLLBACK_OK: alte KI-Zentrale wieder aktiv. Neue Dateien wurden nicht gelöscht."
