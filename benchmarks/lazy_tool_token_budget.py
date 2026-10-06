#!/usr/bin/env python3
"""Token budget of the live local-tools schemas. Uses Ollama tokenize."""
from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

from mcp import Client

MCP_URL = "http://127.0.0.1:8765/mcp"
OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = "local-fast"
OUT = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/lazy-tool-budget-20260922/budget.json")
GROUPS = {
    "memory": ["memory_load", "memory_update"],
    "pdf": [
        "pdf_read",
        "pdf_inspect",
        "pdf_create",
        "pdf_edit",
        "pdf_merge",
        "pdf_split",
        "pdf_ocr",
        "pdf_render",
        "pdf_vision_qa",
    ],
    "image": ["generate_image", "edit_image"],
    "browser": [
        "browser_open",
        "browser_snapshot",
        "browser_click",
        "browser_type",
        "browser_scroll",
        "browser_back",
        "browser_screenshot",
        "browser_close",
    ],
    "desktop": [
        "desktop_snapshot",
        "desktop_focus",
        "desktop_click",
        "desktop_type",
        "desktop_scroll",
        "desktop_key",
        "desktop_screenshot",
        "desktop_close",
    ],
}


def tokenize(text: str) -> int:
    body = json.dumps(
        {
            "model": MODEL,
            "prompt": text,
            "stream": False,
            "raw": True,
            "keep_alive": "2m",
            "options": {"num_predict": 1, "temperature": 0},
        }
    ).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode())
    count = payload.get("prompt_eval_count")
    if not isinstance(count, int):
        raise RuntimeError(f"no prompt_eval_count: {list(payload)}")
    return count


def schema_text(tool) -> str:
    return json.dumps(
        {
            "name": f"mcp__local-tools__{tool.name}",
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def main() -> None:
    async with Client(MCP_URL) as client:
        listing = await client.list_tools()
        loaded = await client.call_tool(
            "memory_load",
            {"workspace": "/home/mike/Projects/Linux Lokales KI"},
        )
    memory_text = json.dumps(
        [block.model_dump() if hasattr(block, "model_dump") else str(block) for block in loaded.content],
        ensure_ascii=False,
    )
    tools = sorted(listing.tools, key=lambda item: item.name)
    per_tool = {}
    for tool in tools:
        per_tool[tool.name] = tokenize(schema_text(tool))
        print(tool.name, per_tool[tool.name], flush=True)
    groups = {
        name: sum(per_tool[tool_name] for tool_name in names)
        for name, names in GROUPS.items()
    }
    report = {
        "method": "Ollama POST /api/generate raw=true num_predict=0 model=local-fast, field prompt_eval_count. This is the model tokenizer, not a character estimate.",
        "model": MODEL,
        "tool_count": len(tools),
        "per_tool": per_tool,
        "groups": groups,
        "all_29": sum(per_tool.values()),
        "memory_load_result": tokenize(memory_text),
        "memory_load_chars": len(memory_text),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"groups": groups, "all_29": report["all_29"], "memory_load_result": report["memory_load_result"], "tools": len(tools)}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
