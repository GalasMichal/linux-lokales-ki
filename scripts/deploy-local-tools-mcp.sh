#!/usr/bin/env bash
# Deploy only after package review and explicit approval.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$REPO_ROOT/apps/local-tools"
TARGET="/srv/ai/apps/local-tools"
WHEEL_DIR="${1:-/srv/ai/cache/pip/local-tools-mcp-2.0.0}"
USER_UNITS="/home/mike/.config/systemd/user"
QWEN_SETTINGS="/home/mike/.qwen/settings.json"
MCP_CONFIG="/srv/ai/configs/mcp"
BACKUP_BASE="/mnt/ai-archive/backups/local-tools-mcp"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_BASE/$STAMP"
VERSIONED_VENV="/srv/ai/venvs/local-tools-$STAMP"
CURRENT_VENV="/srv/ai/venvs/local-tools"
UNIT="local-tools-mcp.service"

if ! mountpoint -q /mnt/ai-archive; then
  printf '%s\n' "ABBRUCH: /mnt/ai-archive ist nicht eingehängt."
  exit 1
fi
for required in \
  "$SOURCE/server.py" \
  "$SOURCE/gateway.py" \
  "$SOURCE/systemd/$UNIT" \
  "$SOURCE/config/qwen-mcp.json" \
  "$REPO_ROOT/scripts/configure-qwen-mcp.py" \
  "$WHEEL_DIR/SHA256SUMS"; do
  if [[ ! -f "$required" ]]; then
    printf 'ABBRUCH: Datei fehlt: %s\n' "$required"
    exit 1
  fi
done

(
  cd "$WHEEL_DIR"
  sha256sum -c SHA256SUMS
)

install -d -m 0755 "$BACKUP" "$BACKUP/user-units" "$BACKUP/config" "$BACKUP/state"
if [[ -d "$TARGET" ]]; then
  cp -a "$TARGET" "$BACKUP/local-tools"
fi
if [[ -f "$USER_UNITS/$UNIT" ]]; then
  cp -a "$USER_UNITS/$UNIT" "$BACKUP/user-units/$UNIT"
fi
if [[ -d "$MCP_CONFIG" ]]; then
  cp -a "$MCP_CONFIG" "$BACKUP/config/mcp"
fi
if [[ -f "$QWEN_SETTINGS" ]]; then
  cp -a "$QWEN_SETTINGS" "$BACKUP/config/qwen-settings.json"
fi
if [[ -L "$CURRENT_VENV" ]]; then
  readlink "$CURRENT_VENV" > "$BACKUP/state/previous-venv-target"
elif [[ -e "$CURRENT_VENV" ]]; then
  printf '%s\n' "ABBRUCH: $CURRENT_VENV existiert, ist aber kein Symlink."
  exit 1
fi
systemctl --user is-enabled "$UNIT" > "$BACKUP/state/service.enabled" 2>/dev/null || true
systemctl --user is-active "$UNIT" > "$BACKUP/state/service.active" 2>/dev/null || true

python3 -m venv "$VERSIONED_VENV"
"$VERSIONED_VENV/bin/python" -m pip install \
  --disable-pip-version-check \
  --no-index \
  --find-links "$WHEEL_DIR" \
  "mcp==2.0.0"
"$VERSIONED_VENV/bin/python" -m pip check

install -d -m 0755 "$TARGET" "$MCP_CONFIG" "$USER_UNITS"
install -m 0755 "$SOURCE/server.py" "$TARGET/server.py"
install -m 0644 "$SOURCE/gateway.py" "$TARGET/gateway.py"
install -m 0644 "$SOURCE/requirements.txt" "$TARGET/requirements.txt"
install -m 0644 "$SOURCE/config/qwen-mcp.json" "$MCP_CONFIG/local-tools-qwen.json"
install -m 0644 "$SOURCE/systemd/$UNIT" "$USER_UNITS/$UNIT"
"$VERSIONED_VENV/bin/python" -m pip freeze > "$MCP_CONFIG/local-tools-requirements.lock"
cp -a "$WHEEL_DIR/SHA256SUMS" "$MCP_CONFIG/local-tools-wheel-sha256.txt"

TEMP_LINK="/srv/ai/venvs/.local-tools-$STAMP"
ln -s "$VERSIONED_VENV" "$TEMP_LINK"
mv -T "$TEMP_LINK" "$CURRENT_VENV"

python3 "$REPO_ROOT/scripts/configure-qwen-mcp.py" \
  "$QWEN_SETTINGS" \
  "$SOURCE/config/qwen-mcp.json"

systemctl --user daemon-reload
systemctl --user enable "$UNIT"
systemctl --user restart "$UNIT"

for _ in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:8765/health >/dev/null; then
    break
  fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:8765/health

install -m 0755 "$REPO_ROOT/scripts/rollback-local-tools-mcp.sh" "$BACKUP/rollback-local-tools-mcp.sh"
printf '\nINSTALLATION_OK\n'
printf 'Sicherung: %s\n' "$BACKUP"
printf 'Rollback: %q %q\n' "$BACKUP/rollback-local-tools-mcp.sh" "$BACKUP"
