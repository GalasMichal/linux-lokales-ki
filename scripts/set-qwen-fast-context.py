#!/usr/bin/env python3
"""Set local-fast contextWindowSize in global Qwen settings. Leave QUALITY alone."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def _atomic_write(settings_path: Path, settings: dict) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="settings.", suffix=".json", dir=settings_path.parent
    )
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


def set_fast_context(settings: dict, size: int) -> dict:
    providers = ((settings.get("modelProviders") or {}).get("openai")) or []
    found = False
    for provider in providers:
        if provider.get("id") != "local-fast":
            continue
        gen = provider.setdefault("generationConfig", {})
        gen["contextWindowSize"] = size
        found = True
    if not found:
        raise SystemExit("ABBRUCH: Provider local-fast fehlt.")
    for provider in providers:
        if provider.get("id") == "local-quality":
            quality = (provider.get("generationConfig") or {}).get("contextWindowSize")
            if quality != 8192:
                raise SystemExit(f"ABBRUCH: QUALITY contextWindowSize ist {quality}, erwartet 8192.")
    if settings.get("model", {}).get("name") != "local-fast":
        raise SystemExit("ABBRUCH: Default-Modell ist nicht local-fast.")
    mcp = (settings.get("mcpServers") or {}).get("local-tools") or {}
    if mcp.get("trust") is not False and mcp.get("trust") != "false":
        raise SystemExit("ABBRUCH: mcpServers.local-tools.trust ist nicht false.")
    return settings


def read_fast_quality(settings: dict) -> tuple[int | None, int | None]:
    fast = quality = None
    for provider in ((settings.get("modelProviders") or {}).get("openai")) or []:
        size = (provider.get("generationConfig") or {}).get("contextWindowSize")
        if provider.get("id") == "local-fast":
            fast = size
        elif provider.get("id") == "local-quality":
            quality = size
    return fast, quality


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--show":
        settings = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        fast, quality = read_fast_quality(settings)
        print(f"local-fast={fast}")
        print(f"local-quality={quality}")
        print(f"model.name={settings.get('model', {}).get('name')}")
        return 0
    if len(sys.argv) != 3:
        print(
            "usage: set-qwen-fast-context.py SETTINGS SIZE\n"
            "       set-qwen-fast-context.py --show SETTINGS",
            file=sys.stderr,
        )
        return 2
    settings_path = Path(sys.argv[1])
    size = int(sys.argv[2])
    if size not in {16384, 24576, 32768}:
        raise SystemExit(f"ABBRUCH: SIZE {size} nicht erlaubt.")
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    _atomic_write(settings_path, set_fast_context(settings, size))
    fast, quality = read_fast_quality(json.loads(settings_path.read_text(encoding="utf-8")))
    print(f"OK local-fast={fast} local-quality={quality}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
