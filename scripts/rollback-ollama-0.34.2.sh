#!/usr/bin/env bash
# Restore Ollama 0.34.2 from the runtime-update backup. Does not change the systemd drop-in content.
# Requires sudo (password in a visible terminal).
set -euo pipefail

BACKUP_ROOT="${1:-/mnt/ai-archive/backups/runtime-update-20260925-111847}"
OVERRIDE="/etc/systemd/system/ollama.service.d/override.conf"
WANT_CLIENT="0.34.2"
WANT_OVERRIDE_SHA="7fb44d5fbe5363ca9196bc92a95cb0d23766b4f853c491de19e134efa6d89bf4"
WANT_BIN_SHA="ca9f4d3b7538196fab8bad3842bff3aa1352a80bfaaf95391ef7dda28880928b"

file_sha() {
  sha256sum -- "$1" | awk '{print $1}'
}

BIN_SRC="$BACKUP_ROOT/ollama/ollama-0.34.2"
LIB_SRC=""
# Prefer a live-before backup with full lib tree if present
if [[ -d "$BACKUP_ROOT/ollama-live-before-0.34.4-"* ]]; then
  :
fi
# Find newest live-before dir with lib-ollama
shopt -s nullglob
cands=("$BACKUP_ROOT"/ollama-live-before-0.34.4-*)
shopt -u nullglob
if ((${#cands[@]})); then
  LIVE_BACKUP="$(ls -d "${cands[@]}" | sort | tail -1)"
  if [[ -x "$LIVE_BACKUP/ollama" && -d "$LIVE_BACKUP/lib-ollama" ]]; then
    BIN_SRC="$LIVE_BACKUP/ollama"
    LIB_SRC="$LIVE_BACKUP/lib-ollama"
  fi
fi

if [[ ! -x "$BIN_SRC" ]]; then
  printf '%s\n' "ABBRUCH: 0.34.2 Binary fehlt: $BIN_SRC"
  exit 1
fi
if [[ "$(file_sha "$BIN_SRC")" != "$WANT_BIN_SHA" ]]; then
  printf '%s\n' "ABBRUCH: 0.34.2 Binary-SHA stimmt nicht."
  exit 1
fi
if [[ ! -f "$OVERRIDE" ]]; then
  printf '%s\n' "ABBRUCH: Override fehlt: $OVERRIDE"
  exit 1
fi
if [[ "$(file_sha "$OVERRIDE")" != "$WANT_OVERRIDE_SHA" ]]; then
  printf 'WARN: Override-SHA weicht ab (wird nicht überschrieben).\n  ist %s\n' "$(file_sha "$OVERRIDE")"
fi

printf '%s\n' "Ollama-Rollback -> 0.34.2"
printf '%s\n' "sudo-Passwort jetzt im Terminal eingeben."
sudo -v

sudo systemctl stop ollama
sudo install -o0 -g0 -m755 "$BIN_SRC" /usr/local/bin/ollama
if [[ -n "$LIB_SRC" && -d "$LIB_SRC" ]]; then
  sudo rm -rf /usr/local/lib/ollama
  sudo cp -a "$LIB_SRC" /usr/local/lib/ollama
  sudo chown -R root:root /usr/local/lib/ollama
else
  printf '%s\n' "WARN: kein lib-ollama im Backup; nur Binary wiederhergestellt."
fi
sudo systemctl daemon-reload
sudo systemctl start ollama
sleep 2
sudo systemctl is-active ollama
/usr/local/bin/ollama --version
if ! /usr/local/bin/ollama --version 2>&1 | grep -Fq "$WANT_CLIENT"; then
  printf '%s\n' "ABBRUCH: Client ist nicht $WANT_CLIENT"
  exit 1
fi
printf 'OK Ollama 0.34.2 wiederhergestellt. quelle=%s\n' "$BIN_SRC"
