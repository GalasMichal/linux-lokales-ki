#!/usr/bin/env bash
# Restore user units from a mcp-boot-cycle backup directory.
set -euo pipefail

BACKUP="${1:-}"
if [[ -z "$BACKUP" || ! -d "$BACKUP" ]]; then
  printf '%s\n' "usage: rollback-mcp-independent-boot.sh BACKUPDIR"
  exit 2
fi
USER_UNITS="/home/mike/.config/systemd/user"
for unit in ki-workplace.service local-tools-mcp.service; do
  if [[ ! -f "$BACKUP/$unit" ]]; then
    printf 'ABBRUCH: %s fehlt im Backup.\n' "$unit"
    exit 1
  fi
  install -m 0644 "$BACKUP/$unit" "$USER_UNITS/$unit"
done
systemctl --user daemon-reload
systemctl --user restart local-tools-mcp.service
systemctl --user restart ki-workplace.service
printf 'OK restored from %s\n' "$BACKUP"
