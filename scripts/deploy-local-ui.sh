#!/usr/bin/env bash
# Deploy the tested local UI. Run only after explicit user approval.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$REPO_ROOT/apps/ki-workplace"
TARGET="/srv/ai/apps/ki-workplace"
USER_UNITS="/home/mike/.config/systemd/user"
LOCAL_APPS="/home/mike/.local/share/applications"
DESKTOP="/home/mike/Schreibtisch"
BACKUP_BASE="/mnt/ai-archive/backups/ki-ui"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_BASE/$STAMP"

if ! mountpoint -q /mnt/ai-archive; then
  printf '%s\n' "ABBRUCH: /mnt/ai-archive ist nicht eingehängt. Keine Änderungen durchgeführt."
  exit 1
fi
if [[ ! -f "$SOURCE/server.py" || ! -f "$SOURCE/www/index.html" ]]; then
  printf '%s\n' "ABBRUCH: Quelldateien fehlen unter $SOURCE"
  exit 1
fi

install -d -m 0755 "$BACKUP" "$BACKUP/user-units" "$BACKUP/unit-state" "$BACKUP/desktop" "$BACKUP/local-applications"

if [[ -d /srv/ai/apps/ki-hub ]]; then
  cp -a /srv/ai/apps/ki-hub "$BACKUP/ki-hub"
fi
if [[ -d "$TARGET" ]]; then
  cp -a "$TARGET" "$BACKUP/ki-workplace"
fi
for unit in ki-hub.service ki-workplace.service qwen-code-web.service; do
  if [[ -f "$USER_UNITS/$unit" ]]; then
    cp -a "$USER_UNITS/$unit" "$BACKUP/user-units/$unit"
  fi
done
for unit in ki-hub.service comfyui.service qwen-code-web.service ki-workplace.service; do
  systemctl --user is-enabled "$unit" >"$BACKUP/unit-state/$unit.enabled" 2>/dev/null || true
  systemctl --user is-active "$unit" >"$BACKUP/unit-state/$unit.active" 2>/dev/null || true
done
for file in KI-Zentrale.desktop KI-Arbeitsplatz.desktop Lokaler-Chat.desktop; do
  if [[ -f "$DESKTOP/$file" ]]; then
    cp -a "$DESKTOP/$file" "$BACKUP/desktop/$file"
  fi
  if [[ -f "$LOCAL_APPS/$file" ]]; then
    cp -a "$LOCAL_APPS/$file" "$BACKUP/local-applications/$file"
  fi
done

install -d -m 0755 "$TARGET/bin" "$TARGET/www" "$TARGET/workflows" "$USER_UNITS" "$LOCAL_APPS" "$DESKTOP" /srv/ai/cache/brave/ki-workplace /srv/ai/cache/brave/local-chat
install -m 0755 "$SOURCE/server.py" "$TARGET/server.py"
install -m 0755 "$SOURCE/bin/open-workplace.sh" "$TARGET/bin/open-workplace.sh"
install -m 0755 "$SOURCE/bin/open-local-chat.sh" "$TARGET/bin/open-local-chat.sh"
install -m 0644 "$SOURCE/www/index.html" "$TARGET/www/index.html"
install -m 0644 "$SOURCE/workflows/flux2-klein-t2i-api-v1.json" "$TARGET/workflows/flux2-klein-t2i-api-v1.json"
install -m 0644 "$SOURCE/systemd/ki-workplace.service" "$USER_UNITS/ki-workplace.service"
install -m 0644 "$SOURCE/systemd/qwen-code-web.service" "$USER_UNITS/qwen-code-web.service"
install -m 0755 "$SOURCE/desktop/KI-Arbeitsplatz.desktop" "$DESKTOP/KI-Arbeitsplatz.desktop"
install -m 0755 "$SOURCE/desktop/Lokaler-Chat.desktop" "$DESKTOP/Lokaler-Chat.desktop"
install -m 0644 "$SOURCE/desktop/KI-Arbeitsplatz.desktop" "$LOCAL_APPS/KI-Arbeitsplatz.desktop"
install -m 0644 "$SOURCE/desktop/Lokaler-Chat.desktop" "$LOCAL_APPS/Lokaler-Chat.desktop"

# The old launcher is moved into the backup so only the two requested icons remain.
if [[ -f "$DESKTOP/KI-Zentrale.desktop" ]]; then
  mv "$DESKTOP/KI-Zentrale.desktop" "$BACKUP/desktop/KI-Zentrale.desktop.moved"
fi
if [[ -f "$LOCAL_APPS/KI-Zentrale.desktop" ]]; then
  mv "$LOCAL_APPS/KI-Zentrale.desktop" "$BACKUP/local-applications/KI-Zentrale.desktop.moved"
fi

systemctl --user daemon-reload
systemctl --user disable --now ki-hub.service 2>/dev/null || true
systemctl --user disable --now comfyui.service 2>/dev/null || true
systemctl --user disable --now qwen-code-web.service 2>/dev/null || true
systemctl --user enable ki-workplace.service
systemctl --user restart ki-workplace.service

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$LOCAL_APPS" >/dev/null 2>&1 || true
fi

install -d -m 0755 /srv/ai/docs /srv/ai/benchmarks
install -m 0644 "$REPO_ROOT/docs/KI_ARBEITSPLATZ.md" /srv/ai/docs/KI_ARBEITSPLATZ.md
install -m 0644 "$REPO_ROOT/docs/CHANGELOG.md" /srv/ai/docs/CHANGELOG.md
install -m 0644 "$REPO_ROOT/benchmarks/ui-integration-20260821.json" /srv/ai/benchmarks/ui-integration-20260821.json
install -m 0755 "$REPO_ROOT/scripts/rollback-local-ui.sh" "$BACKUP/rollback-local-ui.sh"

printf '%s\n' "INSTALLATION_OK"
printf 'Sicherung: %s\n' "$BACKUP"
printf 'Rollback: %q %q\n' "$BACKUP/rollback-local-ui.sh" "$BACKUP"
