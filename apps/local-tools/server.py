#!/usr/bin/env python3
"""Local-only MCP gateway shared by Qwen Code and Open WebUI."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from gateway import ToolError, generate_image_via_workplace


SERVER_VERSION = "1.0.0"
WORKFLOW_ID = "flux2-klein-t2i-v1"

mcp = MCPServer(
    "local-ai-tools",
    version=SERVER_VERSION,
    instructions=(
        "Lokale, eng begrenzte Werkzeuge. Version 1 darf ausschließlich den "
        "freigegebenen FLUX.2-klein-Text-zu-Bild-Workflow ausführen."
    ),
)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
async def generate_image(
    prompt: str,
    width: Literal[512, 768, 1024] = 1024,
    height: Literal[512, 768, 1024] = 1024,
    seed: int = 42,
    workflow_id: Literal["flux2-klein-t2i-v1"] = WORKFLOW_ID,
) -> dict[str, Any]:
    """Erzeuge lokal genau ein Bild mit dem freigegebenen FLUX.2-klein-Workflow.

    Der Auftrag läuft mit Batch 1. Ollama wird vorher entladen, ComfyUI wird bei
    Bedarf gestartet, und Ergebnis sowie Manifest werden im Bildarchiv abgelegt.
    Erlaubte Kantenlängen: 512, 768 oder 1024 Pixel.
    """
    try:
        return await generate_image_via_workplace(prompt, width, height, seed, workflow_id)
    except ToolError as exc:
        return {"ok": False, "error": str(exc), "workflow_id": WORKFLOW_ID}


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> Response:
    return JSONResponse(
        {
            "status": "ok",
            "server": "local-ai-tools",
            "version": SERVER_VERSION,
            "tools": ["generate_image"],
            "localhost_only": True,
        }
    )


transport_security = TransportSecuritySettings(
    allowed_hosts=[
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "host.containers.internal",
        "host.containers.internal:*",
    ],
    allowed_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
)

app = mcp.streamable_http_app(
    host="127.0.0.1",
    json_response=True,
    stateless_http=True,
    max_request_body_size=64 * 1024,
    transport_security=transport_security,
)
