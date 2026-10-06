#!/usr/bin/env bash
# Install previously downloaded Ollama 0.34.2. Does not change the systemd drop-in.
# Requires sudo. Pin: GitHub release v0.34.2 stable, not RC.
set -euo pipefail

SRC="/srv/ai/cache/ollama-0.34.2/extract"
OVERRIDE="/etc/systemd/system/ollama.service.d/override.conf"
BACKUP_ROOT="/mnt/ai-archive/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${OLLAMA_BACKUP_DIR:-$BACKUP_ROOT/ollama-0.34.0-$STAMP}"
WANT_CLIENT="0.34.2"
WANT_OVERRIDE_SHA="7fb44d5fbe5363ca9196bc92a95cb0d23766b4f853c491de19e134efa6d89bf4"
NEW_BIN_SHA="ca9f4d3b7538196fab8bad3842bff3aa1352a80bfaaf95391ef7dda28880928b"

file_sha() {
  sha256sum -- "$1" | awk '{print $1}'
}

if [[ ! -x "$SRC/bin/ollama" || ! -d "$SRC/lib/ollama" ]]; then
  printf '%s\n' "ABBRUCH: Extrakt fehlt unter $SRC"
  exit 1
fi
if [[ "$(file_sha "$SRC/bin/ollama")" != "$NEW_BIN_SHA" ]]; then
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

if [[ -n "${SUDO_ASKPASS:-}" ]]; then
  sudo() { command sudo -A "$@"; }
fi

printf '%s\n' "Ollama-Update 0.34.0 -> 0.34.2"
if [[ -n "${SUDO_ASKPASS:-}" ]]; then
  printf '%s\n' "Es öffnet sich ein Passwort-Fenster auf dem Desktop."
else
  printf '%s\n' "sudo-Passwort jetzt im Terminal eingeben."
fi
sudo -v

install -d -m 0755 "$BACKUP"
sudo cp -a /usr/local/bin/ollama "$BACKUP/ollama"
sudo cp -a /usr/local/lib/ollama "$BACKUP/lib-ollama"
sudo cp -a "$OVERRIDE" "$BACKUP/override.conf"
sudo cp -a /etc/systemd/system/ollama.service "$BACKUP/ollama.service" 2>/dev/null || true
printf '%s\n' "$before_override" | sudo tee "$BACKUP/override.sha256" >/dev/null
printf 'Backup %s\n' "$BACKUP"

sudo systemctl stop ollama
sudo rm -rf /usr/local/lib/ollama
sudo install -o0 -g0 -m755 -d /usr/local/bin /usr/local/lib/ollama
sudo install -o0 -g0 -m755 "$SRC/bin/ollama" /usr/local/bin/ollama
sudo cp -a "$SRC/lib/ollama/." /usr/local/lib/ollama/
sudo chown -R root:root /usr/local/lib/ollama

after_override="$(file_sha "$OVERRIDE")"
if [[ "$after_override" != "$before_override" ]]; then
  printf '%s\n' "ABBRUCH: Override hat sich geändert. Stelle 0.34.0 wieder her."
  sudo cp -a "$BACKUP/ollama" /usr/local/bin/ollama
  sudo rm -rf /usr/local/lib/ollama
  sudo cp -a "$BACKUP/lib-ollama" /usr/local/lib/ollama
  sudo systemctl start ollama
  exit 1
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
if [[ "$(file_sha "$OVERRIDE")" != "$WANT_OVERRIDE_SHA" ]]; then
  printf '%s\n' "ABBRUCH: Override-SHA nach Start verändert."
  exit 1
fi
grep -E 'OLLAMA_HOST|MAX_LOADED_MODELS|FLASH_ATTENTION|KV_CACHE|KEEP_ALIVE|NUM_PARALLEL' "$OVERRIDE"
printf 'OK Ollama 0.34.2 installiert, Override unverändert. backup=%s\n' "$BACKUP"
