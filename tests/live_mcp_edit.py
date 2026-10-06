#!/usr/bin/env python3
"""One controlled end-to-end edit call through the deployed MCP server."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp import Client


MCP_URL = "http://127.0.0.1:8765/mcp"
SOURCE = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/qwen-image-21-smoke-20260921/input/source.png")


async def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Testdatei fehlt: {SOURCE}")
    arguments = {
        "instruction": "Change only the apple from red to bright green. Keep everything else unchanged.",
        "input_path": str(SOURCE),
        "width": 1024,
        "height": 1024,
        "seed": 42,
        "preserve_alpha": False,
    }
    async with Client(MCP_URL) as client:
        result = await client.call_tool("edit_image", arguments)
        payload = {
            "is_error": result.is_error,
            "structured_content": result.structured_content,
            "content": [item.model_dump(exclude_none=True) for item in result.content],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if result.is_error:
            raise RuntimeError("MCP meldete einen Tool-Fehler.")
        structured = result.structured_content or {}
        actual = structured.get("result", structured)
        if actual.get("ok") is not True:
            raise RuntimeError(f"Edit fehlgeschlagen: {actual}")
        required = (
            "ok",
            "job_id",
            "output_path",
            "manifest_path",
            "workflow_id",
            "runtime_seconds",
            "quantization",
            "output_sha256",
            "input_sha256",
        )
        missing = [key for key in required if key not in actual]
        if missing:
            raise RuntimeError(f"MCP-Antwort unvollständig: {missing}")
        if actual.get("workflow_id") != "qwen-image-21-edit-v1":
            raise RuntimeError(f"Unerwartete workflow_id: {actual.get('workflow_id')}")


if __name__ == "__main__":
    asyncio.run(main())
