"""Strict adapter from MCP tools to the existing local KI workplace API."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


WORKPLACE_URL = "http://127.0.0.1:8790"
WORKFLOW_ID = "flux2-klein-t2i-v1"
ALLOWED_SIZES = {512, 768, 1024}
MAX_PROMPT_CHARS = 4000
IMAGE_TIMEOUT_SECONDS = 300
GPU_CLEANUP_TIMEOUT_SECONDS = 300
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class ToolError(RuntimeError):
    """Expected error that is safe to return to an MCP client."""


def parse_generate_image(
    prompt: str,
    width: int,
    height: int,
    seed: int,
    workflow_id: str,
) -> dict[str, Any]:
    """Validate the only inputs that model clients may control."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ToolError("Der Bildtext darf nicht leer sein.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ToolError(f"Der Bildtext darf höchstens {MAX_PROMPT_CHARS} Zeichen haben.")
    if workflow_id != WORKFLOW_ID:
        raise ToolError(f"Nur Workflow '{WORKFLOW_ID}' ist erlaubt.")
    if width not in ALLOWED_SIZES or height not in ALLOWED_SIZES:
        raise ToolError("Erlaubte Bildgrößen sind 512, 768 oder 1024 Pixel.")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ToolError("Der Seed muss eine ganze Zahl sein.")
    if not 0 <= seed <= 18_446_744_073_709_551_615:
        raise ToolError("Der Seed liegt außerhalb des erlaubten Bereichs.")
    return {
        "prompt": prompt,
        "width": width,
        "height": height,
        "seed": seed,
        "workflow_id": workflow_id,
    }


def _request_json(path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{WORKPLACE_URL}{path}",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "local-ai-tools/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        message = f"KI-Arbeitsplatz antwortete mit HTTP {exc.code}."
        try:
            detail = json.loads(raw).get("error")
            if isinstance(detail, str) and detail:
                message = detail
        except (json.JSONDecodeError, AttributeError):
            pass
        raise ToolError(message) from exc
    except (URLError, TimeoutError) as exc:
        raise ToolError("Der lokale KI-Arbeitsplatz ist nicht erreichbar oder hat zu lange gebraucht.") from exc

    if len(raw) > MAX_RESPONSE_BYTES:
        raise ToolError("Die lokale Antwort war unerwartet groß.")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError("Der lokale KI-Arbeitsplatz lieferte keine gültige JSON-Antwort.") from exc
    if not isinstance(result, dict):
        raise ToolError("Der lokale KI-Arbeitsplatz lieferte ein ungültiges Ergebnis.")
    if result.get("ok") is not True:
        message = result.get("error")
        raise ToolError(message if isinstance(message, str) and message else "Der Bildauftrag ist fehlgeschlagen.")
    return result


async def generate_image_via_workplace(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    seed: int = 42,
    workflow_id: str = WORKFLOW_ID,
) -> dict[str, Any]:
    """Run one validated image job through the existing GPU sequencer."""
    validated = parse_generate_image(prompt, width, height, seed, workflow_id)
    api_payload = {key: validated[key] for key in ("prompt", "width", "height", "seed")}
    image_result: dict[str, Any] | None = None
    image_error: ToolError | None = None
    try:
        image_result = await asyncio.to_thread(
            _request_json,
            "/api/images/generate",
            api_payload,
            IMAGE_TIMEOUT_SECONDS,
        )
    except ToolError as exc:
        image_error = exc

    cleanup_result: dict[str, Any] | None = None
    cleanup_error: ToolError | None = None
    try:
        cleanup_result = await asyncio.to_thread(
            _request_json,
            "/api/gpu/cleanup",
            {},
            GPU_CLEANUP_TIMEOUT_SECONDS,
        )
    except ToolError as exc:
        cleanup_error = exc

    if image_error is not None:
        suffix = f" GPU-Bereinigung fehlgeschlagen: {cleanup_error}" if cleanup_error else ""
        raise ToolError(f"{image_error}{suffix}") from image_error
    if image_result is None:
        raise ToolError("Der Bildauftrag lieferte kein Ergebnis.")

    result = dict(image_result)
    if cleanup_error is not None:
        result["gpu_cleanup"] = {"ok": False, "error": str(cleanup_error)}
    else:
        result["gpu_cleanup"] = cleanup_result
    return result
