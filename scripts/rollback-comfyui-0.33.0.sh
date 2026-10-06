#!/usr/bin/env bash
# Restore the 0.33.0 systemd unit. Does not delete the 0.37 tree/venv or any models.
set -euo pipefail

BACKUP="${1:-}"
UNIT="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/comfyui.service"
OLD_TREE="/srv/ai/apps/ComfyUI"
OLD_VENV="/srv/ai/venvs/comfyui"
WANT_COMMIT="cc0fc21fea7a6a82f568362b15b7fbd713b419c1"

if [[ -z "$BACKUP" || ! -f "$BACKUP/comfyui.service" ]]; then
  printf '%s\n' "usage: rollback-comfyui-0.33.0.sh BACKUPDIR"
  exit 2
fi
if [[ ! -d "$OLD_TREE" || "$(git -C "$OLD_TREE" rev-parse HEAD)" != "$WANT_COMMIT" ]]; then
  printf '%s\n' "ABBRUCH: 0.33.0-Tree fehlt oder Commit stimmt nicht."
  exit 1
fi
if [[ ! -x "$OLD_VENV/bin/python" ]]; then
  printf '%s\n' "ABBRUCH: 0.33-Venv fehlt: $OLD_VENV"
  exit 1
fi

systemctl --user stop comfyui.service 2>/dev/null || true
cp -a "$BACKUP/comfyui.service" "$UNIT"
systemctl --user daemon-reload
if grep -q '/srv/ai/apps/ComfyUI-0.37.0' "$UNIT"; then
  printf '%s\n' "ABBRUCH: Wiederhergestellte Unit zeigt noch auf 0.37.0."
  exit 1
fi
if ! grep -q 'WorkingDirectory=/srv/ai/apps/ComfyUI$' "$UNIT"; then
  printf '%s\n' "ABBRUCH: WorkingDirectory ist nicht der 0.33.0-Tree."
  exit 1
fi
printf 'OK   Unit restored from %s\n' "$BACKUP"
systemctl --user is-enabled comfyui.service || true
systemctl --user is-active comfyui.service || true
