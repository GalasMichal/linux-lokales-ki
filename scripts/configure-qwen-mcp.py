#!/usr/bin/env python3
"""Merge the reviewed local MCP allowlist into Qwen settings."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def _atomic_write(settings_path: Path, settings: dict) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
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


def merge_fragment(settings: dict, fragment: dict) -> dict:
    servers = settings.setdefault("mcpServers", {})
    servers["local-tools"] = fragment["mcpServers"]["local-tools"]
    mcp_settings = settings.setdefault("mcp", {})
    allowed = mcp_settings.setdefault("allowed", [])
    if "local-tools" not in allowed:
        allowed.append("local-tools")
    return settings


def restore_local_tools_from_backup(settings: dict, backup: dict) -> dict:
    """Restore only local-tools MCP keys. Keep model/provider and other settings."""
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
    return settings


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--restore-mcp":
        settings_path = Path(sys.argv[2])
        backup_path = Path(sys.argv[3])
        settings = json.loads(settings_path.read_text())
        backup = json.loads(backup_path.read_text())
        _atomic_write(settings_path, restore_local_tools_from_backup(settings, backup))
        return 0
    if len(sys.argv) != 3:
        print(
            "usage: configure-qwen-mcp.py SETTINGS FRAGMENT\n"
            "       configure-qwen-mcp.py --restore-mcp SETTINGS BACKUP_SETTINGS",
            file=sys.stderr,
        )
        return 2
    settings_path = Path(sys.argv[1])
    fragment_path = Path(sys.argv[2])
    settings = json.loads(settings_path.read_text())
    fragment = json.loads(fragment_path.read_text())
    _atomic_write(settings_path, merge_fragment(settings, fragment))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
