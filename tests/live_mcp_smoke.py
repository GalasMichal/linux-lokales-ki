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
        required = {
            "generate_image",
            "edit_image",
            "memory_load",
            "memory_update",
            "knowledge_search",
            "knowledge_get",
            "knowledge_record",
            "pdf_read",
            "pdf_inspect",
            "pdf_create",
            "pdf_edit",
            "pdf_merge",
            "pdf_split",
            "pdf_ocr",
            "pdf_render",
            "pdf_vision_qa",
            "moe_consult",
            "browser_open",
            "browser_snapshot",
            "browser_click",
            "browser_type",
            "browser_scroll",
            "browser_back",
            "browser_screenshot",
            "browser_close",
            "desktop_snapshot",
            "desktop_focus",
            "desktop_click",
            "desktop_type",
            "desktop_scroll",
            "desktop_key",
            "desktop_screenshot",
            "desktop_close",
        }
        missing = sorted(required.difference(names))
        if missing:
            raise RuntimeError(f"MCP-Werkzeuge fehlen: {missing}; vorhanden: {names}")
        extra = sorted(set(names) - required)
        if extra:
            raise RuntimeError(f"Unerwartete MCP-Werkzeuge: {extra}")
        image_tool = next(tool for tool in tools if tool.name == "generate_image")
        schema = image_tool.input_schema
        properties = schema.get("properties", {})
        if properties.get("workflow_id", {}).get("const") != "flux2-klein-t2i-v1":
            raise RuntimeError("Workflow-ID ist im MCP-Schema nicht fest begrenzt.")
        for field in ("width", "height"):
            allowed = properties.get(field, {}).get("enum", [])
            if allowed != [512, 768, 1024]:
                raise RuntimeError(f"{field} ist nicht auf die drei erlaubten Größen begrenzt: {allowed}")
        edit_tool = next(tool for tool in tools if tool.name == "edit_image")
        edit_schema = edit_tool.input_schema
        edit_props = edit_schema.get("properties", {})
        if "workflow_id" in edit_props:
            raise RuntimeError("edit_image darf kein workflow_id-Feld haben.")
        required_edit = set(edit_schema.get("required") or [])
        if not {"instruction", "input_path"}.issubset(required_edit):
            raise RuntimeError(f"edit_image Pflichtfelder fehlen: {required_edit}")
        for field in ("width", "height"):
            allowed = edit_props.get(field, {}).get("enum", [])
            if allowed != [512, 768, 1024]:
                raise RuntimeError(f"edit_image {field} ist nicht begrenzt: {allowed}")
        print(
            json.dumps(
                {
                    "ok": True,
                    "server": str(client.server_info),
                    "tools": names,
                    "workflow_id": properties["workflow_id"]["const"],
                    "widths": properties["width"]["enum"],
                    "heights": properties["height"]["enum"],
                    "edit_required": sorted(required_edit),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
