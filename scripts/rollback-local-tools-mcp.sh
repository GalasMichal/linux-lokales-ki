#!/usr/bin/env bash
# Restore the exact pre-deployment MCP/Qwen/service state without deleting data.
set -euo pipefail

BACKUP="${1:?Bitte den beim Deployment ausgegebenen Sicherungsordner angeben.}"
UNIT="local-tools-mcp.service"
USER_UNITS="/home/mike/.config/systemd/user"
TARGET="/srv/ai/apps/local-tools"
MCP_CONFIG="/srv/ai/configs/mcp"
QWEN_SETTINGS="/home/mike/.qwen/settings.json"
CURRENT_VENV="/srv/ai/venvs/local-tools"
ROLLED_BACK="$BACKUP/rolled-back-$(date +%Y%m%d-%H%M%S)"

if [[ ! -d "$BACKUP" || ! -d "$BACKUP/state" ]]; then
  printf '%s\n' "ABBRUCH: Ungültige Sicherung: $BACKUP"
  exit 1
fi

install -d -m 0755 "$ROLLED_BACK"
systemctl --user disable --now "$UNIT" 2>/dev/null || true

if [[ -d "$TARGET" ]]; then
  mv "$TARGET" "$ROLLED_BACK/local-tools"
fi
if [[ -d "$BACKUP/local-tools" ]]; then
  cp -a "$BACKUP/local-tools" "$TARGET"
fi
if [[ -f "$USER_UNITS/$UNIT" ]]; then
  mv "$USER_UNITS/$UNIT" "$ROLLED_BACK/$UNIT"
fi
if [[ -f "$BACKUP/user-units/$UNIT" ]]; then
  cp -a "$BACKUP/user-units/$UNIT" "$USER_UNITS/$UNIT"
fi
if [[ -d "$MCP_CONFIG" ]]; then
  mv "$MCP_CONFIG" "$ROLLED_BACK/mcp-config"
fi
if [[ -d "$BACKUP/config/mcp" ]]; then
  cp -a "$BACKUP/config/mcp" "$MCP_CONFIG"
else
  install -d -m 0755 "$MCP_CONFIG"
fi
# Restore only local-tools MCP keys so later model defaults (FAST/QUALITY) survive.
# Inline Python so a copied rollback script in the backup folder stays self-contained.
if [[ -f "$BACKUP/config/qwen-settings.json" ]]; then
  if [[ -f "$QWEN_SETTINGS" ]]; then
    python3 - "$QWEN_SETTINGS" "$BACKUP/config/qwen-settings.json" <<'PY'
import json, os, sys, tempfile
from pathlib import Path

settings_path = Path(sys.argv[1])
backup_path = Path(sys.argv[2])
settings = json.loads(settings_path.read_text())
backup = json.loads(backup_path.read_text())

backup_servers = backup.get("mcpServers") or {}
servers = settings.setdefault("mcpServers", {})
if "local-tools" in backup_servers:
    servers["local-tools"] = backup_servers["local-tools"]
else:
    servers.pop("local-tools", None)
    if not servers:
        settings.pop("mcpServers", None)

mcp_settings = settings.setdefault("mcp", {})
allowed = list(mcp_settings.get("allowed") or [])
backup_allowed = (backup.get("mcp") or {}).get("allowed") or []
if "local-tools" in backup_allowed:
    if "local-tools" not in allowed:
        allowed.append("local-tools")
else:
    allowed = [name for name in allowed if name != "local-tools"]
if allowed:
    mcp_settings["allowed"] = allowed
else:
    mcp_settings.pop("allowed", None)
    if not mcp_settings:
        settings.pop("mcp", None)

descriptor, temporary = tempfile.mkstemp(prefix="settings.", suffix=".json", dir=settings_path.parent)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, settings_path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
  else
    cp -a "$BACKUP/config/qwen-settings.json" "$QWEN_SETTINGS"
  fi
fi
if [[ -L "$CURRENT_VENV" ]]; then
  mv "$CURRENT_VENV" "$ROLLED_BACK/local-tools-venv-link"
fi
if [[ -f "$BACKUP/state/previous-venv-target" ]]; then
  ln -s "$(cat "$BACKUP/state/previous-venv-target")" "$CURRENT_VENV"
fi

systemctl --user daemon-reload
if grep -qx enabled "$BACKUP/state/service.enabled" 2>/dev/null; then
  systemctl --user enable "$UNIT"
fi
if grep -qx active "$BACKUP/state/service.active" 2>/dev/null; then
  systemctl --user start "$UNIT"
fi

printf 'ROLLBACK_OK=%s\n' "$BACKUP"
printf 'Der ersetzte Zustand liegt weiterhin unter: %s\n' "$ROLLED_BACK"
