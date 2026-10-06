#!/usr/bin/env bash
# Break the user-unit ordering cycle that dropped local-tools-mcp at boot.
# MCP starts independently. Workplace no longer After=default.target.
# Does not enable Qwen Serve or ComfyUI. No hardening removed.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
USER_UNITS="/home/mike/.config/systemd/user"
BACKUP_BASE="/mnt/ai-archive/backups/mcp-boot-cycle"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_BASE/$STAMP"

install -d -m 0755 "$BACKUP" "$USER_UNITS"
for unit in ki-workplace.service local-tools-mcp.service; do
  if [[ -f "$USER_UNITS/$unit" ]]; then
    cp -a "$USER_UNITS/$unit" "$BACKUP/$unit"
  fi
done
printf '%s\n' "$BACKUP" > "$BACKUP/BACKUP.path"

install -m 0644 "$REPO_ROOT/apps/ki-workplace/systemd/ki-workplace.service" \
  "$USER_UNITS/ki-workplace.service"
install -m 0644 "$REPO_ROOT/apps/local-tools/systemd/local-tools-mcp.service" \
  "$USER_UNITS/local-tools-mcp.service"

systemctl --user daemon-reload
systemd-analyze --user verify \
  "$USER_UNITS/ki-workplace.service" \
  "$USER_UNITS/local-tools-mcp.service"

if grep -E "After=default.target|After=ki-workplace.service|Wants=ki-workplace.service" \
  "$USER_UNITS/ki-workplace.service" "$USER_UNITS/local-tools-mcp.service"; then
  printf '%s\n' "ABBRUCH: Zyklus-Abhängigkeiten noch vorhanden."
  exit 1
fi

systemctl --user enable local-tools-mcp.service ki-workplace.service
systemctl --user restart local-tools-mcp.service
systemctl --user restart ki-workplace.service

for i in $(seq 1 20); do
  curl -sf http://127.0.0.1:8765/health >/dev/null && break
  sleep 0.3
done
curl -sf http://127.0.0.1:8765/health >/dev/null
curl -sf http://127.0.0.1:8790/api/status >/dev/null

printf 'OK backup=%s mcp=independent workplace=After=network.target\n' "$BACKUP"
