#!/usr/bin/env python3
"""Set local-quality contextWindowSize. Force default model local-fast. Leave FAST ctx alone."""

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


def apply(settings: dict, size: int) -> dict:
    providers = ((settings.get("modelProviders") or {}).get("openai")) or []
    found = False
    for provider in providers:
        if provider.get("id") != "local-quality":
            continue
        gen = provider.setdefault("generationConfig", {})
        extra = gen.setdefault("extra_body", {})
        extra.setdefault("think", False)
        extra.setdefault("enable_thinking", False)
        extra["reasoning_effort"] = "none"
        gen["contextWindowSize"] = size
        found = True
    if not found:
        raise SystemExit("ABBRUCH: Provider local-quality fehlt.")
    for provider in providers:
        if provider.get("id") == "local-fast":
            fast = (provider.get("generationConfig") or {}).get("contextWindowSize")
            if fast != 32768:
                raise SystemExit(f"ABBRUCH: FAST contextWindowSize ist {fast}, erwartet 32768.")
    model = settings.setdefault("model", {})
    model["name"] = "local-fast"
    model.setdefault("baseUrl", "http://127.0.0.1:11434/v1")
    # Compact at 85% of 16k was the hidden QUALITY 2-min generation.
    settings["compactionModel"] = "local-fast"
    context = settings.setdefault("context", {})
    context["autoCompactThreshold"] = 0.95
    tools = settings.setdefault("tools", {})
    if tools.get("approvalMode") not in (None, "default"):
        raise SystemExit(f"ABBRUCH: approvalMode ist {tools.get('approvalMode')}, erwartet default.")
    tools["approvalMode"] = "default"
    mcp = (settings.get("mcpServers") or {}).get("local-tools") or {}
    if mcp.get("trust") is not False and mcp.get("trust") != "false":
        raise SystemExit("ABBRUCH: mcpServers.local-tools.trust ist nicht false.")
    return settings


def read_state(settings: dict) -> dict:
    fast = quality = None
    for provider in ((settings.get("modelProviders") or {}).get("openai")) or []:
        size = (provider.get("generationConfig") or {}).get("contextWindowSize")
        if provider.get("id") == "local-fast":
            fast = size
        elif provider.get("id") == "local-quality":
            quality = size
    mcp = (settings.get("mcpServers") or {}).get("local-tools") or {}
    return {
        "local-fast": fast,
        "local-quality": quality,
        "model.name": (settings.get("model") or {}).get("name"),
        "approvalMode": (settings.get("tools") or {}).get("approvalMode"),
        "trust": mcp.get("trust"),
        "compactionModel": settings.get("compactionModel"),
        "autoCompactThreshold": (settings.get("context") or {}).get("autoCompactThreshold"),
    }


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--show":
        settings = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        state = read_state(settings)
        for key, value in state.items():
            print(f"{key}={value}")
        return 0
    if len(sys.argv) != 3:
        print(
            "usage: set-qwen-quality-context.py SETTINGS SIZE\n"
            "       set-qwen-quality-context.py --show SETTINGS",
            file=sys.stderr,
        )
        return 2
    settings_path = Path(sys.argv[1])
    size = int(sys.argv[2])
    # Allowed productive / historical QUALITY context sizes only.
    if size not in {8192, 16384, 65536, 81920, 90112, 98304}:
        raise SystemExit(f"ABBRUCH: SIZE {size} nicht erlaubt.")
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    _atomic_write(settings_path, apply(settings, size))
    state = read_state(json.loads(settings_path.read_text(encoding="utf-8")))
    print("OK " + " ".join(f"{k}={v}" for k, v in state.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
