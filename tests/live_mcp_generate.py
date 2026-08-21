#!/usr/bin/env python3
"""One controlled end-to-end image call through the deployed MCP server."""

from __future__ import annotations

import asyncio
import json

from mcp import Client


MCP_URL = "http://127.0.0.1:8765/mcp"


async def main() -> None:
    arguments = {
        "prompt": "Ein kleiner roter Würfel auf einem neutralen grauen Hintergrund, Studiofotografie",
        "width": 512,
        "height": 512,
        "seed": 20260821,
        "workflow_id": "flux2-klein-t2i-v1",
    }
    async with Client(MCP_URL) as client:
        result = await client.call_tool("generate_image", arguments)
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
            raise RuntimeError(f"Bildauftrag fehlgeschlagen: {actual}")
        if (actual.get("gpu_cleanup") or {}).get("ok") is not True:
            raise RuntimeError(f"GPU-Bereinigung fehlgeschlagen: {actual.get('gpu_cleanup')}")


if __name__ == "__main__":
    asyncio.run(main())
