#!/usr/bin/env python3
"""Read-only live smoke test for the deployed local MCP endpoint."""

from __future__ import annotations

import asyncio
import json

from mcp import Client


MCP_URL = "http://127.0.0.1:8765/mcp"


async def main() -> None:
    async with Client(MCP_URL) as client:
        listing = await client.list_tools()
        tools = listing.tools
        names = [tool.name for tool in tools]
        if names != ["generate_image"]:
            raise RuntimeError(f"Unerwartete MCP-Werkzeuge: {names}")
        schema = tools[0].input_schema
        properties = schema.get("properties", {})
        if properties.get("workflow_id", {}).get("const") != "flux2-klein-t2i-v1":
            raise RuntimeError("Workflow-ID ist im MCP-Schema nicht fest begrenzt.")
        for field in ("width", "height"):
            allowed = properties.get(field, {}).get("enum", [])
            if allowed != [512, 768, 1024]:
                raise RuntimeError(f"{field} ist nicht auf die drei erlaubten Größen begrenzt: {allowed}")
        print(
            json.dumps(
                {
                    "ok": True,
                    "server": str(client.server_info),
                    "tools": names,
                    "workflow_id": properties["workflow_id"]["const"],
                    "widths": properties["width"]["enum"],
                    "heights": properties["height"]["enum"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
