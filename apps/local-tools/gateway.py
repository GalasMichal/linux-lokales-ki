"""Strict adapter from MCP tools to the existing local KI workplace API."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from errors import ToolError
from paths import resolve_existing_file


WORKPLACE_URL = "http://127.0.0.1:8790"
WORKFLOW_ID = "flux2-klein-t2i-v1"
EDIT_WORKFLOW_ID = "qwen-image-21-edit-v1"
VIDEO_WORKFLOW_ID = "wan22-ti2v-5b-v1"
ALLOWED_SIZES = {512, 768, 1024}
ALLOWED_VIDEO_SIZES = {(704, 1280), (1280, 704), (480, 832), (832, 480)}
ALLOWED_VIDEO_LENGTHS = {49, 81}
MAX_PROMPT_CHARS = 4000
IMAGE_TIMEOUT_SECONDS = 300
EDIT_TIMEOUT_SECONDS = 480
VIDEO_TIMEOUT_SECONDS = 960
GPU_CLEANUP_TIMEOUT_SECONDS = 300
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_EDIT_REFERENCES = 2
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


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
    if isinstance(seed, str) and seed.strip().isdigit():
        seed = int(seed.strip())
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


def _normalize_reference_paths(reference_paths: Any) -> list[str]:
    if reference_paths in (None, ""):
        return []
    if isinstance(reference_paths, str):
        text = reference_paths.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ToolError("reference_paths muss eine Liste von Pfaden sein.") from exc
            if not isinstance(loaded, list):
                raise ToolError("reference_paths muss eine Liste von Pfaden sein.")
            reference_paths = loaded
        else:
            reference_paths = [item.strip() for item in text.split(",") if item.strip()]
    if not isinstance(reference_paths, list):
        raise ToolError("reference_paths muss eine Liste von Pfaden sein.")
    if len(reference_paths) > MAX_EDIT_REFERENCES:
        raise ToolError("Höchstens zwei zusätzliche Referenzbilder sind erlaubt.")
    normalized: list[str] = []
    for item in reference_paths:
        if not isinstance(item, str) or not item.strip():
            raise ToolError("Jeder Referenzpfad muss Text sein.")
        normalized.append(item.strip())
    return normalized


def parse_edit_image(
    instruction: str,
    input_path: str,
    reference_paths: Any = None,
    width: int = 1024,
    height: int = 1024,
    seed: int = 42,
    preserve_alpha: bool = False,
) -> dict[str, Any]:
    if not isinstance(instruction, str) or not instruction.strip():
        raise ToolError("Die Bearbeitungsanweisung darf nicht leer sein.")
    instruction = instruction.strip()
    if len(instruction) > MAX_PROMPT_CHARS:
        raise ToolError(f"Die Anweisung darf höchstens {MAX_PROMPT_CHARS} Zeichen haben.")
    if not isinstance(input_path, str) or not input_path.strip():
        raise ToolError("input_path ist Pflicht.")
    lowered = input_path.strip().lower()
    if "://" in input_path or lowered.startswith("data:"):
        raise ToolError("URLs und Base64-Bilddaten sind nicht erlaubt.")
    source = resolve_existing_file(input_path.strip(), IMAGE_SUFFIXES)
    references = []
    for item in _normalize_reference_paths(reference_paths):
        item_lower = item.lower()
        if "://" in item or item_lower.startswith("data:"):
            raise ToolError("URLs und Base64-Bilddaten sind nicht erlaubt.")
        references.append(str(resolve_existing_file(item, IMAGE_SUFFIXES)))
    if width not in ALLOWED_SIZES or height not in ALLOWED_SIZES:
        raise ToolError("Erlaubte Bildgrößen sind 512, 768 oder 1024 Pixel.")
    if isinstance(seed, str) and seed.strip().isdigit():
        seed = int(seed.strip())
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ToolError("Der Seed muss eine ganze Zahl sein.")
    if not 0 <= seed <= 18_446_744_073_709_551_615:
        raise ToolError("Der Seed liegt außerhalb des erlaubten Bereichs.")
    if isinstance(preserve_alpha, str):
        preserve_alpha = preserve_alpha.strip().lower() in {"1", "true", "yes", "on"}
    if not isinstance(preserve_alpha, bool):
        raise ToolError("preserve_alpha muss wahr oder falsch sein.")
    return {
        "instruction": instruction,
        "input_path": str(source),
        "reference_paths": references,
        "width": width,
        "height": height,
        "seed": seed,
        "preserve_alpha": preserve_alpha,
    }


async def edit_image_via_workplace(
    instruction: str,
    input_path: str,
    reference_paths: Any = None,
    width: int = 1024,
    height: int = 1024,
    seed: int = 42,
    preserve_alpha: bool = False,
) -> dict[str, Any]:
    """Run one validated edit job through the existing workplace sequencer."""
    validated = parse_edit_image(
        instruction, input_path, reference_paths, width, height, seed, preserve_alpha
    )
    result = await asyncio.to_thread(
        _request_json,
        "/api/images/edit",
        validated,
        EDIT_TIMEOUT_SECONDS,
    )
    result.setdefault("workflow_id", EDIT_WORKFLOW_ID)
    return result


def parse_generate_video(
    prompt: str,
    input_path: str,
    width: int = 704,
    height: int = 1280,
    length: int = 49,
    seed: int = 42,
) -> dict[str, Any]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ToolError("Der Videotext darf nicht leer sein.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ToolError(f"Der Videotext darf höchstens {MAX_PROMPT_CHARS} Zeichen haben.")
    if not isinstance(input_path, str) or not input_path.strip():
        raise ToolError("input_path ist Pflicht (Foto für Bild-zu-Video).")
    lowered = input_path.strip().lower()
    if "://" in input_path or lowered.startswith("data:"):
        raise ToolError("URLs und Base64-Bilddaten sind nicht erlaubt.")
    source = resolve_existing_file(input_path.strip(), IMAGE_SUFFIXES)
    try:
        width = int(width)
        height = int(height)
        length = int(length)
    except (TypeError, ValueError) as exc:
        raise ToolError("Breite, Höhe und Länge müssen ganze Zahlen sein.") from exc
    if (width, height) not in ALLOWED_VIDEO_SIZES:
        raise ToolError("Erlaubte Videoformate: 704x1280, 1280x704, 480x832, 832x480.")
    if length not in ALLOWED_VIDEO_LENGTHS:
        raise ToolError("Erlaubte Cliplängen: 49 oder 81 Frames.")
    if isinstance(seed, str) and seed.strip().isdigit():
        seed = int(seed.strip())
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ToolError("Der Seed muss eine ganze Zahl sein.")
    if not 0 <= seed <= 18_446_744_073_709_551_615:
        raise ToolError("Der Seed liegt außerhalb des erlaubten Bereichs.")
    return {
        "prompt": prompt,
        "input_path": str(source),
        "width": width,
        "height": height,
        "length": length,
        "seed": seed,
    }


async def generate_video_via_workplace(
    prompt: str,
    input_path: str,
    width: int = 704,
    height: int = 1280,
    length: int = 49,
    seed: int = 42,
) -> dict[str, Any]:
    """Run one validated Wan 2.2 image-to-video job through the workplace sequencer."""
    validated = parse_generate_video(prompt, input_path, width, height, length, seed)
    result = await asyncio.to_thread(
        _request_json,
        "/api/videos/generate",
        validated,
        VIDEO_TIMEOUT_SECONDS,
    )
    result.setdefault("workflow_id", VIDEO_WORKFLOW_ID)
    return result
