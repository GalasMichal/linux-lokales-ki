#!/usr/bin/env bash
# Restore Ollama binary+libs from a runtime backup. Does not touch models.
set -euo pipefail

BACKUP="${1:-}"
if [[ -z "$BACKUP" || ! -x "$BACKUP/ollama" || ! -d "$BACKUP/lib-ollama" ]]; then
  printf '%s\n' "usage: rollback-ollama.sh BACKUPDIR"
  exit 2
fi
OVERRIDE="/etc/systemd/system/ollama.service.d/override.conf"
WANT_OVERRIDE_SHA="7fb44d5fbe5363ca9196bc92a95cb0d23766b4f853c491de19e134efa6d89bf4"

if [[ -n "${SUDO_ASKPASS:-}" ]]; then
  sudo() { command sudo -A "$@"; }
fi

sudo -v
sudo systemctl stop ollama
sudo cp -a "$BACKUP/ollama" /usr/local/bin/ollama
sudo rm -rf /usr/local/lib/ollama
sudo cp -a "$BACKUP/lib-ollama" /usr/local/lib/ollama
if [[ -f "$BACKUP/override.conf" ]]; then
  sudo cp -a "$BACKUP/override.conf" "$OVERRIDE"
fi
sudo systemctl daemon-reload
sudo systemctl start ollama
sleep 2
sudo systemctl is-active ollama
/usr/local/bin/ollama --version
sha256sum "$OVERRIDE"
if [[ "$(sha256sum "$OVERRIDE" | awk '{print $1}')" != "$WANT_OVERRIDE_SHA" ]]; then
  printf '%s\n' "WARNUNG: Override-SHA weicht ab."
fi
printf 'OK restored Ollama from %s\n' "$BACKUP"
