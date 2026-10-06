#!/usr/bin/env bash
# Install previously downloaded Ollama 0.35.0. Does not change the systemd drop-in.
# Requires sudo (password in a visible terminal). Pin: GitHub release v0.35.0 stable, not RC.
set -euo pipefail

SRC="/srv/ai/cache/ollama-0.35.0/extract"
OVERRIDE="/etc/systemd/system/ollama.service.d/override.conf"
BACKUP_ROOT="${OLLAMA_BACKUP_DIR:-/mnt/ai-archive/backups/runtime-update-pending/ollama}"
WANT_CLIENT="0.35.0"
WANT_OVERRIDE_SHA="7fb44d5fbe5363ca9196bc92a95cb0d23766b4f853c491de19e134efa6d89bf4"
NEW_BIN_SHA="${OLLAMA_0350_BIN_SHA:-}"

file_sha() {
  sha256sum -- "$1" | awk '{print $1}'
}

if [[ ! -x "$SRC/bin/ollama" || ! -d "$SRC/lib/ollama" ]]; then
  printf '%s\n' "ABBRUCH: Extrakt fehlt unter $SRC"
  exit 1
fi
if [[ -n "$NEW_BIN_SHA" && "$(file_sha "$SRC/bin/ollama")" != "$NEW_BIN_SHA" ]]; then
  printf '%s\n' "ABBRUCH: Neue ollama-Binary-SHA stimmt nicht."
  exit 1
fi
if [[ ! -f "$OVERRIDE" ]]; then
  printf '%s\n' "ABBRUCH: Override fehlt: $OVERRIDE"
  exit 1
fi
before_override="$(file_sha "$OVERRIDE")"
if [[ "$before_override" != "$WANT_OVERRIDE_SHA" ]]; then
  printf 'ABBRUCH: Override-SHA unerwartet vor Update.\n  ist  %s\n' "$before_override"
  exit 1
fi
if ! mountpoint -q /mnt/ai-archive; then
  printf '%s\n' "ABBRUCH: /mnt/ai-archive ist nicht eingehängt."
  exit 1
fi

printf '%s\n' "Ollama-Update -> 0.35.0"
printf '%s\n' "sudo-Passwort jetzt im Terminal eingeben."
sudo -v

install -d -m 0755 "$BACKUP_ROOT"
sudo cp -a /usr/local/bin/ollama "$BACKUP_ROOT/ollama"
sudo cp -a /usr/local/lib/ollama "$BACKUP_ROOT/lib-ollama"
sudo cp -a "$OVERRIDE" "$BACKUP_ROOT/override.conf"
sudo cp -a /etc/systemd/system/ollama.service "$BACKUP_ROOT/ollama.service" 2>/dev/null || true
printf '%s\n' "$before_override" | sudo tee "$BACKUP_ROOT/override.sha256" >/dev/null
printf '%s\n' "$(file_sha "$SRC/bin/ollama")" | tee "$BACKUP_ROOT/new-bin.sha256"
/usr/local/bin/ollama --version | tee "$BACKUP_ROOT/old-version.txt"
printf 'Backup %s\n' "$BACKUP_ROOT"

sudo systemctl stop ollama
sudo rm -rf /usr/local/lib/ollama
sudo install -o0 -g0 -m755 -d /usr/local/bin /usr/local/lib/ollama
sudo install -o0 -g0 -m755 "$SRC/bin/ollama" /usr/local/bin/ollama
sudo cp -a "$SRC/lib/ollama/." /usr/local/lib/ollama/
sudo chown -R root:root /usr/local/lib/ollama

after_override="$(file_sha "$OVERRIDE")"
if [[ "$after_override" != "$before_override" ]]; then
  printf '%s\n' "ABBRUCH: Override hat sich geändert. Rolle zurück."
  sudo cp -a "$BACKUP_ROOT/ollama" /usr/local/bin/ollama
  sudo rm -rf /usr/local/lib/ollama
  sudo cp -a "$BACKUP_ROOT/lib-ollama" /usr/local/lib/ollama
  sudo systemctl start ollama
  exit 1
fi

sudo systemctl daemon-reload
sudo systemctl start ollama
sleep 2
sudo systemctl is-active ollama

/usr/local/bin/ollama --version
if ! /usr/local/bin/ollama --version 2>&1 | grep -Fq "$WANT_CLIENT"; then
  printf '%s\n' "ABBRUCH: Client ist nicht $WANT_CLIENT — Rollback"
  sudo systemctl stop ollama
  sudo cp -a "$BACKUP_ROOT/ollama" /usr/local/bin/ollama
  sudo rm -rf /usr/local/lib/ollama
  sudo cp -a "$BACKUP_ROOT/lib-ollama" /usr/local/lib/ollama
  sudo systemctl start ollama
  exit 1
fi
if [[ "$(file_sha "$OVERRIDE")" != "$WANT_OVERRIDE_SHA" ]]; then
  printf '%s\n' "ABBRUCH: Override-SHA nach Start verändert."
  exit 1
fi
grep -E 'OLLAMA_HOST|MAX_LOADED_MODELS|FLASH_ATTENTION|KV_CACHE|KEEP_ALIVE|NUM_PARALLEL' "$OVERRIDE"
printf 'OK Ollama 0.35.0 installiert, Override unverändert. backup=%s\n' "$BACKUP_ROOT"
