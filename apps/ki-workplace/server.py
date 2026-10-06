#!/usr/bin/env python3
"""Local-only desktop control surface for the AI stack.

The public UI binds to 127.0.0.1:8790. A second local-only listener on
127.0.0.1:8791 proxies the installed Qwen Code Web Shell. The proxy keeps
Qwen unmodified and only relaxes its frame policy for the local workplace UI.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import struct
import time
import uuid
import re
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


HOST = "127.0.0.1"
UI_PORT = int(os.environ.get("KI_WORKPLACE_PORT", "8790"))
QWEN_PROXY_PORT = int(os.environ.get("KI_QWEN_PROXY_PORT", "8791"))
QWEN_UPSTREAM = os.environ.get("KI_QWEN_UPSTREAM", "http://127.0.0.1:4170")
COMFY_URL = "http://127.0.0.1:8188"
OLLAMA_URL = "http://127.0.0.1:11434"

ROOT = Path(__file__).resolve().parent
WWW = ROOT / "www"
WORKFLOW_FILE = ROOT / "workflows" / "flux2-klein-t2i-api-v1.json"
EDIT_WORKFLOW_FILE = ROOT / "workflows" / "qwen-image-21-edit-v1.json"
VIDEO_WORKFLOW_FILE = ROOT / "workflows" / "wan22-ti2v-5b-api-v1.json"
COMFY_OUTPUT = Path("/srv/ai/apps/ComfyUI/output")
COMFY_INPUT = Path("/srv/ai/apps/ComfyUI-0.38.0/input")
COMFY_MODELS = Path("/srv/ai/models/comfyui")
ARCHIVE_ROOT = Path("/mnt/ai-archive")
IMAGE_ARCHIVE = ARCHIVE_ROOT / "images" / "inbox"
VIDEO_ARCHIVE = ARCHIVE_ROOT / "ki-videos" / "inbox"
UI_STAGE_DIR = Path("/srv/ai/workspaces/ki-workplace-stage")
UI_STAGE_PREFIX = "ui_stage_"

WORKFLOW_ID = "flux2-klein-t2i-v1"
EDIT_WORKFLOW_ID = "qwen-image-21-edit-v1"
VIDEO_WORKFLOW_ID = "wan22-ti2v-5b-v1"
MODEL_FILES = {
    "diffusion_model": COMFY_MODELS / "diffusion_models" / "flux-2-klein-4b-fp8.safetensors",
    "text_encoder": COMFY_MODELS / "text_encoders" / "qwen_3_4b.safetensors",
    "vae": COMFY_MODELS / "vae" / "flux2-vae.safetensors",
}
EDIT_MODEL_FILES = {
    "diffusion_model": COMFY_MODELS / "diffusion_models" / "qwen_image_2.1_int8_convrot.safetensors",
    "text_encoder": COMFY_MODELS / "text_encoders" / "qwen3vl_8b_w4a8.safetensors",
    "vae": COMFY_MODELS / "vae" / "qwen_image_2.1_vae_bf16.safetensors",
}
VIDEO_MODEL_FILES = {
    "diffusion_model": COMFY_MODELS / "diffusion_models" / "wan2.2_ti2v_5B_fp16.safetensors",
    "text_encoder": COMFY_MODELS / "text_encoders" / "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "vae": COMFY_MODELS / "vae" / "wan2.2_vae.safetensors",
}
ALLOWED_SIZES = {512, 768, 1024}
ALLOWED_VIDEO_SIZES = {(704, 1280), (1280, 704), (480, 832), (832, 480)}
ALLOWED_VIDEO_LENGTHS = {49, 81}
MAX_PROMPT_CHARS = 4000
IMAGE_TIMEOUT_SECONDS = 240
EDIT_TIMEOUT_SECONDS = 420
VIDEO_TIMEOUT_SECONDS = 900
EDIT_STEPS = 25
EDIT_CFG = 1.0
VIDEO_STEPS = 20
VIDEO_CFG = 5.0
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_EDGE = 4096
MAX_EDIT_REFERENCES = 2
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mkv", ".gif", ".webp", ".png"}
ALLOWED_IMAGE_ROOTS = (
    Path("/home/mike/Projects"),
    Path("/srv/ai/workspaces"),
    Path("/mnt/ai-archive"),
    Path("/tmp"),
    Path("/var/tmp"),
)
UNSAFE_PATH_PARTS = {".git", ".ssh", ".gnupg", ".qwen"}
MIN_FREE_ROOT_GIB = 20
MIN_FREE_ARCHIVE_GIB = 5
MIN_RAM_AVAILABLE_GIB = 4
MIN_VRAM_FREE_MIB = 2000
REQUIRED_EDIT_NODES = (
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "TextEncodeQwenImage21",
    "QwenImage21Cache",
    "LoadImage",
    "KSampler",
    "VAEDecode",
    "SaveImage",
)
REQUIRED_VIDEO_NODES = (
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "ModelSamplingSD3",
    "CLIPTextEncode",
    "LoadImage",
    "Wan22ImageToVideoLatent",
    "KSampler",
    "VAEDecode",
    "CreateVideo",
    "SaveVideo",
)
# Official Qwen-Image-2.1 README, Transparent Image Generation (RGBA).
ALPHA_PROMPT_PREFIX = "This is an RGBA image with transparency. "
ALPHA_PROMPT_SUFFIX = " The image has alpha channel and the background is transparent."
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
# Qwen's Express CORS rejects Origin 8790/8791. Do not forward those headers upstream.
DROP_UPSTREAM_REQUEST_HEADERS = {"host", "origin", "referer"}
ALLOWED_QWEN_MODELS = {
    "local-fast",
    "local-fast(openai)",
    "openai:local-fast",
    "local-quality",
    "local-quality(openai)",
    "openai:local-quality",
}


class AppError(RuntimeError):
    """Expected, user-facing application error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@lru_cache(maxsize=8)
def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_image_request(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AppError("Ungültige Anfrage.")

    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise AppError("Bitte einen Bildtext eingeben.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise AppError(f"Der Bildtext darf höchstens {MAX_PROMPT_CHARS} Zeichen haben.")

    try:
        width = int(data.get("width", 1024))
        height = int(data.get("height", 1024))
        seed = int(data.get("seed", 42))
    except (TypeError, ValueError) as exc:
        raise AppError("Breite, Höhe und Seed müssen ganze Zahlen sein.") from exc

    if width not in ALLOWED_SIZES or height not in ALLOWED_SIZES:
        raise AppError("Erlaubte Bildgrößen sind 512, 768 oder 1024 Pixel.")
    if not 0 <= seed <= 18_446_744_073_709_551_615:
        raise AppError("Der Seed liegt außerhalb des erlaubten Bereichs.")

    return {"prompt": prompt, "width": width, "height": height, "seed": seed}


def build_workflow(template: dict[str, Any], request: dict[str, Any], job_id: str) -> dict[str, Any]:
    workflow = deepcopy(template)
    workflow["4"]["inputs"]["text"] = request["prompt"]
    workflow["6"]["inputs"]["width"] = request["width"]
    workflow["6"]["inputs"]["height"] = request["height"]
    workflow["7"]["inputs"]["noise_seed"] = request["seed"]
    workflow["9"]["inputs"]["width"] = request["width"]
    workflow["9"]["inputs"]["height"] = request["height"]
    workflow["13"]["inputs"]["filename_prefix"] = f"ki_arbeitsplatz_{job_id}"
    return workflow


def compose_edit_instruction(instruction: str, preserve_alpha: bool) -> str:
    if not preserve_alpha:
        return instruction
    return f"{ALPHA_PROMPT_PREFIX}{instruction}{ALPHA_PROMPT_SUFFIX}"


def _reject_unsafe_image_path(raw: str) -> None:
    text = raw.strip()
    if not text:
        raise AppError("Bildpfad darf nicht leer sein.")
    lowered = text.lower()
    if "://" in text or lowered.startswith("data:"):
        raise AppError("URLs und Base64-Bilddaten sind nicht erlaubt.")
    if "\n" in text or "\r" in text:
        raise AppError("Ungültiger Bildpfad.")


def assert_allowed_image_path(path: Path) -> Path:
    resolved = path.resolve()
    if any(part in UNSAFE_PATH_PARTS for part in resolved.parts):
        raise AppError("Dieser Pfad ist gesperrt.")
    for root in ALLOWED_IMAGE_ROOTS:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise AppError("Pfad liegt außerhalb der erlaubten Arbeitsbereiche.")


def classify_image_root(path: Path) -> str:
    resolved = path.resolve()
    mapping = {
        Path("/home/mike/Projects"): "projects",
        Path("/srv/ai/workspaces"): "workspaces",
        Path("/mnt/ai-archive"): "archive",
        Path("/tmp"): "tmp",
        Path("/var/tmp"): "var_tmp",
    }
    for root, label in mapping.items():
        try:
            resolved.relative_to(root)
            return label
        except ValueError:
            continue
    return "other"


def _png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AppError("PNG-Datei ist ungültig.")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _jpeg_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\xff\xd8"):
        raise AppError("JPEG-Datei ist ungültig.")
    index = 2
    while index + 9 <= len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return width, height
        if marker in {0xD8, 0xD9}:
            index += 2
            continue
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        index += 2 + length
    raise AppError("JPEG-Abmessungen konnten nicht gelesen werden.")


def _webp_size(data: bytes) -> tuple[int, int]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise AppError("WebP-Datei ist ungültig.")
    kind = data[12:16]
    if kind == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if kind == b"VP8 " and len(data) >= 30:
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return width, height
    if kind == b"VP8L" and len(data) >= 25:
        bits = struct.unpack("<I", data[21:25])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    raise AppError("WebP-Abmessungen konnten nicht gelesen werden.")


def inspect_image_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise AppError("Erlaubt sind nur PNG, JPEG und WebP.")
    size = path.stat().st_size
    if size <= 0:
        raise AppError("Die Bilddatei ist leer.")
    if size > MAX_IMAGE_BYTES:
        raise AppError("Die Bilddatei darf höchstens 25 MiB groß sein.")
    head = path.read_bytes()[:64]
    if suffix == ".png":
        if not head.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AppError("Die Datei ist kein gültiges PNG.")
        width, height = _png_size(path.read_bytes()[:24])
        kind = "png"
    elif suffix in {".jpg", ".jpeg"}:
        if not head.startswith(b"\xff\xd8"):
            raise AppError("Die Datei ist kein gültiges JPEG.")
        with path.open("rb") as handle:
            blob = handle.read(2 * 1024 * 1024)
        width, height = _jpeg_size(blob)
        kind = "jpeg"
    else:
        with path.open("rb") as handle:
            blob = handle.read(64)
        width, height = _webp_size(blob)
        kind = "webp"
    if width < 1 or height < 1 or width > MAX_IMAGE_EDGE or height > MAX_IMAGE_EDGE:
        raise AppError("Die Bildkante darf höchstens 4096 Pixel sein.")
    return {"path": path, "kind": kind, "width": width, "height": height, "bytes": size}


def resolve_edit_image_path(raw: str) -> dict[str, Any]:
    _reject_unsafe_image_path(raw)
    candidate = Path(raw.strip()).expanduser()
    if not candidate.is_absolute():
        raise AppError("Bildpfade müssen absolut sein.")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise AppError("Bilddatei nicht gefunden.") from exc
    if not resolved.is_file():
        raise AppError("Bildpfad ist keine Datei.")
    assert_allowed_image_path(resolved)
    info = inspect_image_file(resolved)
    info["origin"] = classify_image_root(resolved)
    info["name"] = resolved.name
    info["sha256"] = sha256_file(str(resolved))
    return info


def parse_edit_request(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AppError("Ungültige Anfrage.")
    if "workflow_id" in data:
        raise AppError("workflow_id wird nicht entgegengenommen.")
    if "graph" in data or "prompt_graph" in data:
        raise AppError("Ein ComfyUI-Graph darf nicht übergeben werden.")

    instruction = data.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise AppError("Bitte eine Bearbeitungsanweisung eingeben.")
    instruction = instruction.strip()
    if len(instruction) > MAX_PROMPT_CHARS:
        raise AppError(f"Die Anweisung darf höchstens {MAX_PROMPT_CHARS} Zeichen haben.")

    input_raw = data.get("input_path")
    if not isinstance(input_raw, str):
        raise AppError("input_path ist Pflicht.")
    source = resolve_edit_image_path(input_raw)

    references_raw = data.get("reference_paths") or []
    if references_raw in ("", None):
        references_raw = []
    if isinstance(references_raw, str):
        try:
            loaded = json.loads(references_raw)
            references_raw = loaded if isinstance(loaded, list) else [references_raw]
        except json.JSONDecodeError:
            references_raw = [item.strip() for item in references_raw.split(",") if item.strip()]
    if not isinstance(references_raw, list):
        raise AppError("reference_paths muss eine Liste sein.")
    if len(references_raw) > MAX_EDIT_REFERENCES:
        raise AppError("Höchstens zwei zusätzliche Referenzbilder sind erlaubt.")
    references = []
    for item in references_raw:
        if not isinstance(item, str):
            raise AppError("Jeder Referenzpfad muss Text sein.")
        references.append(resolve_edit_image_path(item))

    try:
        width = int(data.get("width", 1024))
        height = int(data.get("height", 1024))
        seed = int(data.get("seed", 42))
    except (TypeError, ValueError) as exc:
        raise AppError("Breite, Höhe und Seed müssen ganze Zahlen sein.") from exc
    if width not in ALLOWED_SIZES or height not in ALLOWED_SIZES:
        raise AppError("Erlaubte Bildgrößen sind 512, 768 oder 1024 Pixel.")
    if not 0 <= seed <= 18_446_744_073_709_551_615:
        raise AppError("Der Seed liegt außerhalb des erlaubten Bereichs.")

    preserve_alpha = data.get("preserve_alpha", False)
    if isinstance(preserve_alpha, str):
        preserve_alpha = preserve_alpha.strip().lower() in {"1", "true", "yes", "on"}
    if not isinstance(preserve_alpha, bool):
        raise AppError("preserve_alpha muss wahr oder falsch sein.")

    return {
        "instruction": instruction,
        "composed_instruction": compose_edit_instruction(instruction, preserve_alpha),
        "input": source,
        "references": references,
        "width": width,
        "height": height,
        "seed": seed,
        "preserve_alpha": preserve_alpha,
        "resolution": max(width, height),
    }


def build_edit_workflow(
    template: dict[str, Any], request: dict[str, Any], job_id: str, staged_names: list[str]
) -> dict[str, Any]:
    if not staged_names:
        raise AppError("Interner Fehler: keine bereitgestellten Eingabebilder.")
    workflow = deepcopy(template)
    workflow["5"]["inputs"]["image"] = staged_names[0]
    workflow["6"]["inputs"]["prompt"] = request["composed_instruction"]
    workflow["6"]["inputs"]["resolution"] = request["resolution"]
    workflow["7"]["inputs"]["seed"] = request["seed"]
    workflow["7"]["inputs"]["steps"] = EDIT_STEPS
    workflow["7"]["inputs"]["cfg"] = EDIT_CFG
    workflow["7"]["inputs"]["sampler_name"] = "euler"
    workflow["7"]["inputs"]["scheduler"] = "simple"
    workflow["9"]["inputs"]["filename_prefix"] = f"ki_arbeitsplatz_{job_id}"
    next_id = 10
    for index, name in enumerate(staged_names[1:], start=2):
        node_id = str(next_id)
        workflow[node_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
        workflow["6"]["inputs"][f"images.image_{index}"] = [node_id, 0]
        next_id += 1
    return workflow


def validate_png_output(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AppError(f"ComfyUI-Ausgabe fehlt: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise AppError("Die Ausgabe ist leer.")
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AppError("Die Ausgabe ist kein gültiges PNG.")
    width, height = struct.unpack(">II", data[16:24])
    if width < 1 or height < 1:
        raise AppError("Die Ausgabe hat ungültige Pixelmaße.")
    return {"width": width, "height": height, "bytes": size, "sha256": hashlib.sha256(data).hexdigest()}


def parse_comfy_version(raw: Any) -> tuple[int, int, int]:
    text = str(raw or "").strip()
    parts: list[int] = []
    for item in text.split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        if digits == "":
            break
        parts.append(int(digits))
        if len(parts) == 3:
            break
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def preflight_edit_storage() -> None:
    if not os.path.ismount(ARCHIVE_ROOT):
        raise AppError("Archiv-HDD ist nicht eingehängt. Bild wird nicht in den falschen Datenträger geschrieben.")
    root_free = shutil.disk_usage("/").free / 1024**3
    archive_free = shutil.disk_usage(ARCHIVE_ROOT).free / 1024**3
    if root_free < MIN_FREE_ROOT_GIB:
        raise AppError("Auf der Systemplatte sind weniger als 20 GiB frei.")
    if archive_free < MIN_FREE_ARCHIVE_GIB:
        raise AppError("Auf der Archiv-HDD sind weniger als 5 GiB frei.")
    mem = memory_status()
    available = mem["total_gib"] - mem["used_gib"]
    if available < MIN_RAM_AVAILABLE_GIB:
        raise AppError("Es sind weniger als 4 GiB RAM verfügbar.")


def preflight_video_storage() -> None:
    if not os.path.ismount(ARCHIVE_ROOT):
        raise AppError("Archiv-HDD ist nicht eingehängt. Video wird nicht in den falschen Datenträger geschrieben.")
    root_free = shutil.disk_usage("/").free / 1024**3
    archive_free = shutil.disk_usage(ARCHIVE_ROOT).free / 1024**3
    if root_free < MIN_FREE_ROOT_GIB:
        raise AppError("Auf der Systemplatte sind weniger als 20 GiB frei.")
    if archive_free < MIN_FREE_ARCHIVE_GIB:
        raise AppError("Auf der Archiv-HDD sind weniger als 5 GiB frei.")
    mem = memory_status()
    available = mem["total_gib"] - mem["used_gib"]
    if available < MIN_RAM_AVAILABLE_GIB:
        raise AppError("Es sind weniger als 4 GiB RAM verfügbar.")


def missing_edit_models() -> list[str]:
    return [str(path) for path in EDIT_MODEL_FILES.values() if not path.is_file()]


async def stage_edit_inputs(job_id: str, images: list[dict[str, Any]]) -> list[str]:
    COMFY_INPUT.mkdir(parents=True, exist_ok=True)
    staged: list[str] = []
    try:
        for index, info in enumerate(images, start=1):
            suffix = info["path"].suffix.lower()
            name = f"ki_edit_{job_id}_{index}{suffix}"
            target = COMFY_INPUT / name
            await asyncio.to_thread(shutil.copy2, info["path"], target)
            staged.append(name)
    except Exception:
        cleanup_staged_inputs(staged)
        raise
    return staged


def cleanup_staged_inputs(names: list[str]) -> None:
    for name in names:
        if Path(name).name != name:
            continue
        path = COMFY_INPUT / name
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def is_ui_stage_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved.relative_to(UI_STAGE_DIR.resolve())
    except (ValueError, OSError, FileNotFoundError):
        return False
    return resolved.name.startswith(UI_STAGE_PREFIX)


def cleanup_ui_stage_paths(paths: list[Path]) -> None:
    for path in paths:
        if not is_ui_stage_path(path):
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def sweep_old_ui_stage(max_age_seconds: int = 7200) -> None:
    if not UI_STAGE_DIR.is_dir():
        return
    cutoff = time.time() - max_age_seconds
    for path in UI_STAGE_DIR.glob(f"{UI_STAGE_PREFIX}*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def find_job_output(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", job_id):
        raise AppError("Ungültige Job-ID.")
    if not IMAGE_ARCHIVE.is_dir():
        raise AppError("Kein Archivverzeichnis.")
    matches = list(IMAGE_ARCHIVE.glob(f"*/{job_id}/ki_arbeitsplatz_{job_id}*.png"))
    if not matches:
        matches = list(IMAGE_ARCHIVE.glob(f"*/{job_id}/*.png"))
    if not matches:
        raise AppError("Ausgabe nicht gefunden.")
    matches.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    candidate = matches[0].resolve()
    root = IMAGE_ARCHIVE.resolve()
    if candidate != root and root not in candidate.parents:
        raise AppError("Ausgabepfad ungültig.")
    return candidate


def public_image_ref(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "origin": info.get("origin"),
        "name": info.get("name"),
        "sha256": info.get("sha256"),
        "kind": info.get("kind"),
        "width": info.get("width"),
        "height": info.get("height"),
        "bytes": info.get("bytes"),
    }


def safe_comfy_output(filename: str, subfolder: str) -> Path:
    if Path(filename).name != filename:
        raise AppError("ComfyUI lieferte einen ungültigen Dateinamen.")
    relative = Path(subfolder) / filename if subfolder else Path(filename)
    candidate = (COMFY_OUTPUT / relative).resolve()
    root = COMFY_OUTPUT.resolve()
    if candidate != root and root not in candidate.parents:
        raise AppError("ComfyUI-Ausgabepfad liegt außerhalb des erlaubten Ordners.")
    return candidate


def collect_comfy_media(outputs: dict[str, Any] | None, node_id: str) -> list[dict[str, Any]]:
    node = (outputs or {}).get(node_id) or {}
    items: list[dict[str, Any]] = []
    for key in ("images", "gifs", "videos"):
        for item in node.get(key) or []:
            if isinstance(item, dict) and item.get("filename"):
                items.append(item)
    return items


def missing_video_models() -> list[str]:
    return [str(path) for path in VIDEO_MODEL_FILES.values() if not path.is_file()]


def parse_video_request(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AppError("Ungültige Anfrage.")
    if "workflow_id" in data:
        raise AppError("workflow_id wird nicht entgegengenommen.")
    if "graph" in data or "prompt_graph" in data:
        raise AppError("Ein ComfyUI-Graph darf nicht übergeben werden.")

    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise AppError("Bitte einen Videotext eingeben.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise AppError(f"Der Videotext darf höchstens {MAX_PROMPT_CHARS} Zeichen haben.")

    input_raw = data.get("input_path")
    if not isinstance(input_raw, str) or not input_raw.strip():
        raise AppError("input_path ist Pflicht (Foto für Bild-zu-Video / TikTok).")
    source = resolve_edit_image_path(input_raw)

    try:
        width = int(data.get("width", 704))
        height = int(data.get("height", 1280))
        seed = int(data.get("seed", 42))
        length = int(data.get("length", 49))
    except (TypeError, ValueError) as exc:
        raise AppError("Breite, Höhe, Länge und Seed müssen ganze Zahlen sein.") from exc
    if (width, height) not in ALLOWED_VIDEO_SIZES:
        raise AppError("Erlaubte Videoformate: 704x1280, 1280x704, 480x832, 832x480.")
    if length not in ALLOWED_VIDEO_LENGTHS:
        raise AppError("Erlaubte Cliplängen: 49 oder 81 Frames.")
    if not 0 <= seed <= 18_446_744_073_709_551_615:
        raise AppError("Der Seed liegt außerhalb des erlaubten Bereichs.")

    return {
        "prompt": prompt,
        "input": source,
        "width": width,
        "height": height,
        "length": length,
        "seed": seed,
    }


def build_video_workflow(
    template: dict[str, Any],
    request: dict[str, Any],
    job_id: str,
    staged_name: str,
) -> dict[str, Any]:
    workflow = deepcopy(template)
    workflow["6"]["inputs"]["text"] = request["prompt"]
    workflow["55"]["inputs"]["width"] = request["width"]
    workflow["55"]["inputs"]["height"] = request["height"]
    workflow["55"]["inputs"]["length"] = request["length"]
    workflow["3"]["inputs"]["seed"] = request["seed"]
    workflow["3"]["inputs"]["steps"] = VIDEO_STEPS
    workflow["3"]["inputs"]["cfg"] = VIDEO_CFG
    workflow["56"]["inputs"]["image"] = staged_name
    workflow["58"]["inputs"]["filename_prefix"] = f"video/wan22_{job_id}"
    return workflow


async def stage_video_input(job_id: str, image: dict[str, Any]) -> str:
    COMFY_INPUT.mkdir(parents=True, exist_ok=True)
    suffix = image["path"].suffix.lower()
    name = f"ki_video_{job_id}{suffix}"
    target = COMFY_INPUT / name
    try:
        await asyncio.to_thread(shutil.copy2, image["path"], target)
    except Exception:
        cleanup_staged_inputs([name])
        raise
    return name


def filter_local_qwen_providers(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AppError("Qwen lieferte einen ungültigen Provider-Status.")
    result = deepcopy(payload)
    safe_providers = []
    for provider in result.get("providers") or []:
        if not isinstance(provider, dict) or provider.get("authType") != "openai":
            continue
        safe_models = []
        for model in provider.get("models") or []:
            model_id = model.get("modelId") if isinstance(model, dict) else None
            base_url = model.get("baseUrl") if isinstance(model, dict) else None
            if model_id in ALLOWED_QWEN_MODELS and base_url == f"{OLLAMA_URL}/v1":
                safe_models.append(model)
        if safe_models:
            clean = deepcopy(provider)
            clean["models"] = safe_models
            safe_providers.append(clean)
    result["providers"] = safe_providers
    current = result.get("current") or {}
    if (
        current.get("authType") != "openai"
        or current.get("modelId") not in ALLOWED_QWEN_MODELS
        or current.get("baseUrl") != f"{OLLAMA_URL}/v1"
    ):
        raise AppError("Qwen ist nicht auf ein erlaubtes lokales Modell eingestellt.")
    return result


def validate_qwen_proxy_mutation(path: str, method: str, body: bytes) -> None:
    method = method.upper()
    if path.startswith("/workspace/auth/") and method != "GET":
        raise AppError("Cloud-/Provider-Anmeldung ist im lokalen Arbeitsplatz gesperrt.")

    is_model_switch = method == "POST" and re.fullmatch(r"/session/[^/]+/model", path)
    is_session_create = method == "POST" and path in {"/session", "/sessions"}
    if not (is_model_switch or is_session_create) or not body:
        return
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AppError("Ungültige Qwen-Anfrage.") from exc
    if not isinstance(payload, dict):
        raise AppError("Ungültige Qwen-Anfrage.")
    model_id = payload.get("modelId") if is_model_switch else payload.get("modelServiceId")
    if model_id is not None and model_id not in ALLOWED_QWEN_MODELS:
        raise AppError(f"Modell '{model_id}' ist gesperrt. Erlaubt sind nur FAST und QUALITY über Ollama.")


async def run_command(*args: str, timeout: float = 20) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise AppError(f"Zeitüberschreitung bei: {' '.join(args[:3])}")
    return proc.returncode, stdout.decode(errors="replace").strip(), stderr.decode(errors="replace").strip()


async def service_active(unit: str) -> bool:
    code, _, _ = await run_command("systemctl", "--user", "is-active", "--quiet", unit, timeout=5)
    return code == 0


async def service_action(action: str, unit: str) -> None:
    if action not in {"start", "stop"}:
        raise AppError("Interne Dienstaktion nicht erlaubt.")
    code, out, err = await run_command("systemctl", "--user", action, unit, timeout=30)
    if code != 0:
        raise AppError(err or out or f"{unit} konnte nicht {action} ausgeführt werden.")


async def wait_http(session: ClientSession, url: str, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            async with session.get(url, timeout=ClientTimeout(total=2)) as response:
                if response.status < 500:
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


# Discrete agent-boot stages. Percent jumps only when that step actually finishes.
BOOT_PHASES: dict[str, dict[str, Any]] = {
    "idle": {
        "percent": 0,
        "title": "Bereit",
        "detail": "",
    },
    "stopping_images": {
        "percent": 15,
        "title": "Bilder-KI wird beendet",
        "detail": "ComfyUI wird gestoppt, damit die Grafikkarte frei ist.",
    },
    "starting_qwen": {
        "percent": 32,
        "title": "Qwen-Dienst startet",
        "detail": "Der Agent-Dienst wird eingeschaltet.",
    },
    "waiting_health": {
        "percent": 45,
        "title": "Warte auf Qwen",
        "detail": "Noch keine Antwort von 127.0.0.1:4170/health.",
    },
    "ready": {
        "percent": 58,
        "title": "Qwen erreichbar",
        "detail": "Der Dienst antwortet. Als Nächstes kommen die Fensterdateien.",
    },
    "error": {
        "percent": 0,
        "title": "Agent hat nicht geladen",
        "detail": "",
    },
}


def boot_payload(phase: str, *, mode: str | None = "agent", detail: str | None = None) -> dict[str, Any]:
    spec = BOOT_PHASES.get(phase) or BOOT_PHASES["idle"]
    return {
        "mode": mode,
        "phase": phase if phase in BOOT_PHASES else "idle",
        "percent": int(spec["percent"]),
        "title": str(spec["title"]),
        "detail": str(spec["detail"] if detail is None else detail),
    }


def set_boot(app: web.Application, phase: str, *, detail: str | None = None) -> dict[str, Any]:
    payload = boot_payload(phase, detail=detail)
    app["boot"] = payload
    return payload


async def get_json(session: ClientSession, url: str, *, timeout: float = 3) -> Any | None:
    try:
        async with session.get(url, timeout=ClientTimeout(total=timeout)) as response:
            if response.status != 200:
                return None
            return await response.json()
    except Exception:
        return None


async def unload_ollama(session: ClientSession) -> list[str]:
    ps = await get_json(session, f"{OLLAMA_URL}/api/ps") or {}
    unloaded: list[str] = []
    for item in ps.get("models") or []:
        model = item.get("name") or item.get("model")
        if not isinstance(model, str) or not model:
            continue
        payload = {"model": model, "keep_alive": 0}
        async with session.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=ClientTimeout(total=30),
        ) as response:
            if response.status >= 300:
                text = await response.text()
                raise AppError(f"Ollama-Modell {model} konnte nicht entladen werden: {text[:300]}")
        unloaded.append(model)

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        current = await get_json(session, f"{OLLAMA_URL}/api/ps") or {}
        if not (current.get("models") or []):
            return unloaded
        await asyncio.sleep(0.5)
    raise AppError("Ollama meldet nach 20 Sekunden weiterhin ein geladenes Modell.")


async def ensure_agent_mode(app: web.Application) -> dict[str, Any]:
    try:
        if await service_active("comfyui.service"):
            set_boot(app, "stopping_images")
            await service_action("stop", "comfyui.service")
        set_boot(app, "starting_qwen")
        await service_action("start", "qwen-code-web.service")
        set_boot(app, "waiting_health")
        ready = await wait_http(app["session"], f"{QWEN_UPSTREAM}/health", 20)
        if not ready:
            set_boot(app, "error", detail="Qwen Code Web ist nach 20 Sekunden nicht erreichbar.")
            raise AppError("Qwen Code Web ist nach 20 Sekunden nicht erreichbar.")
        boot = set_boot(app, "ready")
        return {
            "ok": True,
            "mode": "agent",
            "message": "Agent bereit. Bilder-KI wurde beendet.",
            "boot": boot,
        }
    except AppError as exc:
        current = app.get("boot") or {}
        if current.get("phase") != "error":
            set_boot(app, "error", detail=str(exc))
        raise


async def ensure_image_mode(app: web.Application) -> dict[str, Any]:
    unloaded = await unload_ollama(app["session"])
    await service_action("start", "comfyui.service")
    ready = await wait_http(app["session"], f"{COMFY_URL}/system_stats", 45)
    if not ready:
        raise AppError("ComfyUI ist nach 45 Sekunden nicht erreichbar.")
    return {
        "ok": True,
        "mode": "images",
        "unloaded_models": unloaded,
        "message": "Bilder-KI bereit. Ollama-Modelle wurden entladen.",
    }


async def ensure_edit_image_mode(app: web.Application) -> dict[str, Any]:
    if await service_active("qwen-code-web.service"):
        await service_action("stop", "qwen-code-web.service")
    unloaded = await unload_ollama(app["session"])
    await asyncio.sleep(1)
    ps = await get_json(app["session"], f"{OLLAMA_URL}/api/ps") or {}
    if ps.get("models"):
        raise AppError("Ollama hat nach dem Entladen noch ein geladenes Modell.")
    if await service_active("qwen-code-web.service"):
        raise AppError("Qwen Serve läuft noch und blockiert die Grafikkarte.")

    gpu = await gpu_status()
    if gpu is not None and gpu["free_mib"] < MIN_VRAM_FREE_MIB:
        raise AppError(
            f"Nach dem Entladen sind nur {gpu['free_mib']} MiB VRAM frei, mindestens {MIN_VRAM_FREE_MIB} MiB werden gebraucht."
        )

    missing = missing_edit_models()
    if missing:
        raise AppError("Qwen-Image-2.1-Gewichte fehlen: " + ", ".join(Path(item).name for item in missing))

    await service_action("start", "comfyui.service")
    ready = await wait_http(app["session"], f"{COMFY_URL}/system_stats", 45)
    if not ready:
        raise AppError("ComfyUI ist nach 45 Sekunden nicht erreichbar.")

    stats = await get_json(app["session"], f"{COMFY_URL}/system_stats", timeout=8) or {}
    system = stats.get("system") if isinstance(stats, dict) else {}
    version_raw = ""
    if isinstance(system, dict):
        version_raw = str(system.get("comfyui_version") or system.get("version") or "")
    version = parse_comfy_version(version_raw)
    if version < (0, 37, 0):
        raise AppError(f"ComfyUI {version_raw or 'unbekannt'} ist kleiner als 0.37.0.")

    missing_nodes: list[str] = []
    for node_name in REQUIRED_EDIT_NODES:
        info = await get_json(app["session"], f"{COMFY_URL}/object_info/{quote(node_name)}", timeout=8)
        if not isinstance(info, dict) or node_name not in info:
            missing_nodes.append(node_name)
    if missing_nodes:
        raise AppError("Qwen-Image-2.1-Nodes fehlen: " + ", ".join(missing_nodes))
    return {
        "ok": True,
        "mode": "images",
        "unloaded_models": unloaded,
        "comfyui_version": version_raw,
        "message": "Bildbearbeitung bereit. Qwen Serve ist gestoppt, Ollama ist leer.",
    }


async def ensure_video_mode(app: web.Application) -> dict[str, Any]:
    if await service_active("qwen-code-web.service"):
        await service_action("stop", "qwen-code-web.service")
    unloaded = await unload_ollama(app["session"])
    await asyncio.sleep(1)
    ps = await get_json(app["session"], f"{OLLAMA_URL}/api/ps") or {}
    if ps.get("models"):
        raise AppError("Ollama hat nach dem Entladen noch ein geladenes Modell.")
    if await service_active("qwen-code-web.service"):
        raise AppError("Qwen Serve läuft noch und blockiert die Grafikkarte.")

    gpu = await gpu_status()
    if gpu is not None and gpu["free_mib"] < MIN_VRAM_FREE_MIB:
        raise AppError(
            f"Nach dem Entladen sind nur {gpu['free_mib']} MiB VRAM frei, mindestens {MIN_VRAM_FREE_MIB} MiB werden gebraucht."
        )

    missing = missing_video_models()
    if missing:
        raise AppError("Wan-2.2-Gewichte fehlen: " + ", ".join(Path(item).name for item in missing))

    await service_action("start", "comfyui.service")
    ready = await wait_http(app["session"], f"{COMFY_URL}/system_stats", 45)
    if not ready:
        raise AppError("ComfyUI ist nach 45 Sekunden nicht erreichbar.")

    stats = await get_json(app["session"], f"{COMFY_URL}/system_stats", timeout=8) or {}
    system = stats.get("system") if isinstance(stats, dict) else {}
    version_raw = ""
    if isinstance(system, dict):
        version_raw = str(system.get("comfyui_version") or system.get("version") or "")
    version = parse_comfy_version(version_raw)
    if version < (0, 37, 0):
        raise AppError(f"ComfyUI {version_raw or 'unbekannt'} ist kleiner als 0.37.0.")

    missing_nodes: list[str] = []
    for node_name in REQUIRED_VIDEO_NODES:
        info = await get_json(app["session"], f"{COMFY_URL}/object_info/{quote(node_name)}", timeout=8)
        if not isinstance(info, dict) or node_name not in info:
            missing_nodes.append(node_name)
    if missing_nodes:
        raise AppError("Wan-2.2-Video-Nodes fehlen: " + ", ".join(missing_nodes))
    return {
        "ok": True,
        "mode": "video",
        "unloaded_models": unloaded,
        "comfyui_version": version_raw,
        "message": "Video-KI bereit. Qwen Serve ist gestoppt, Ollama ist leer.",
    }


async def cleanup_gpu(app: web.Application) -> dict[str, Any]:
    """Stop GPU consumers after the last desktop window closes."""
    stopped: list[str] = []
    if await service_active("qwen-code-web.service"):
        await service_action("stop", "qwen-code-web.service")
        stopped.append("qwen-code-web.service")
    if await service_active("comfyui.service"):
        await service_action("stop", "comfyui.service")
        stopped.append("comfyui.service")
    unloaded = await unload_ollama(app["session"])
    await asyncio.sleep(1)
    return {
        "ok": True,
        "message": "GPU-Verbraucher wurden sauber beendet.",
        "stopped_services": stopped,
        "unloaded_models": unloaded,
        "gpu": await gpu_status(),
    }


async def gpu_status() -> dict[str, Any] | None:
    code, out, _ = await run_command(
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
        timeout=5,
    )
    if code != 0 or not out:
        return None
    parts = [part.strip() for part in out.splitlines()[0].split(",")]
    if len(parts) != 5:
        return None
    return {
        "name": parts[0],
        "total_mib": int(parts[1]),
        "used_mib": int(parts[2]),
        "free_mib": int(parts[3]),
        "utilization_percent": int(parts[4]),
    }


def memory_status() -> dict[str, float]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0])
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    return {
        "total_gib": round(total / 1024 / 1024, 2),
        "used_gib": round((total - available) / 1024 / 1024, 2),
        "swap_total_gib": round(swap_total / 1024 / 1024, 2),
        "swap_used_gib": round((swap_total - swap_free) / 1024 / 1024, 2),
    }


def disk_status(path: str) -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {
        "path": path,
        "total_gib": round(usage.total / 1024**3, 1),
        "used_gib": round(usage.used / 1024**3, 1),
        "free_gib": round(usage.free / 1024**3, 1),
    }


@web.middleware
async def local_only(request: web.Request, handler):
    if request.remote not in {"127.0.0.1", "::1"}:
        raise web.HTTPForbidden(text="Nur localhost ist erlaubt.")
    return await handler(request)


@web.middleware
async def security_headers(request: web.Request, handler):
    response = await handler(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: http://127.0.0.1:8188; "
        f"connect-src 'self' http://127.0.0.1:8188 http://127.0.0.1:{QWEN_PROXY_PORT}; "
        f"frame-src http://127.0.0.1:8188 http://127.0.0.1:{QWEN_PROXY_PORT}; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    return response


async def index(request: web.Request) -> web.Response:
    return web.FileResponse(WWW / "index.html")


async def api_status(request: web.Request) -> web.Response:
    app = request.app
    session = app["session"]
    version, ps = await asyncio.gather(
        get_json(session, f"{OLLAMA_URL}/api/version"),
        get_json(session, f"{OLLAMA_URL}/api/ps"),
    )
    services = await asyncio.gather(
        service_active("qwen-code-web.service"),
        service_active("comfyui.service"),
        service_active("open-webui.service"),
    )
    qwen_http, comfy_http, chat_http, gpu = await asyncio.gather(
        wait_http(session, f"{QWEN_UPSTREAM}/health", 1),
        wait_http(session, f"{COMFY_URL}/system_stats", 1),
        wait_http(session, "http://127.0.0.1:3000/health", 1),
        gpu_status(),
    )
    models = []
    for item in (ps or {}).get("models") or []:
        name = item.get("name") or item.get("model")
        if name:
            models.append(name)
    payload = {
        "ok": True,
        "ollama": {"running": version is not None, "version": (version or {}).get("version"), "models": models},
        "qwen": {"service": services[0], "ready": qwen_http, "url": QWEN_UPSTREAM},
        "comfyui": {"service": services[1], "ready": comfy_http, "url": COMFY_URL},
        "chat": {"service": services[2], "ready": chat_http, "url": "http://127.0.0.1:3000"},
        "gpu": gpu,
        "memory": memory_status(),
        "storage": {"active": disk_status("/srv/ai"), "archive": disk_status(str(ARCHIVE_ROOT))},
        "image_job_running": app["image_lock"].locked(),
        "boot": app.get("boot") or boot_payload("idle", mode=None),
        "bindings": [
            "127.0.0.1:11434",
            "127.0.0.1:3000",
            "127.0.0.1:4170",
            "127.0.0.1:8188",
            f"127.0.0.1:{UI_PORT}",
            f"127.0.0.1:{QWEN_PROXY_PORT}",
        ],
    }
    return web.json_response(payload)


async def api_mode(request: web.Request) -> web.Response:
    mode = request.match_info["mode"]
    try:
        if mode == "agent":
            payload = await ensure_agent_mode(request.app)
        elif mode == "images":
            payload = await ensure_image_mode(request.app)
        else:
            raise web.HTTPNotFound()
        return web.json_response(payload)
    except AppError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def api_gpu_cleanup(request: web.Request) -> web.Response:
    # If an image is still rendering or its manifest is being written, wait for
    # that protected job to finish before releasing ComfyUI and Ollama.
    try:
        async with request.app["image_lock"]:
            payload = await cleanup_gpu(request.app)
        return web.json_response(payload)
    except AppError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def image_generate(request: web.Request) -> web.Response:
    lock: asyncio.Lock = request.app["image_lock"]
    if lock.locked():
        return web.json_response(
            {"ok": False, "error": "Es läuft bereits ein Bildauftrag. Bitte warten."},
            status=409,
        )

    try:
        data = parse_image_request(await request.json())
    except (json.JSONDecodeError, web.HTTPBadRequest, AppError) as exc:
        message = str(exc) if isinstance(exc, AppError) else "Ungültige JSON-Anfrage."
        return web.json_response({"ok": False, "error": message}, status=400)

    async with lock:
        started_monotonic = time.monotonic()
        started_at = utc_now()
        job_id = uuid.uuid4().hex[:12]
        entered_gpu = False
        try:
            entered_gpu = True
            await ensure_image_mode(request.app)
            if not WORKFLOW_FILE.is_file():
                raise AppError(f"Workflow fehlt: {WORKFLOW_FILE}")
            template = json.loads(WORKFLOW_FILE.read_text())
            workflow = build_workflow(template, data, job_id)

            session = request.app["session"]
            async with session.post(
                f"{COMFY_URL}/prompt",
                json={"prompt": workflow, "client_id": f"ki-arbeitsplatz-{job_id}"},
                timeout=ClientTimeout(total=20),
            ) as response:
                result = await response.json(content_type=None)
                if response.status >= 300 or not result.get("prompt_id"):
                    raise AppError(f"ComfyUI hat den Auftrag abgelehnt: {result}")
            prompt_id = result["prompt_id"]

            history: dict[str, Any] | None = None
            deadline = time.monotonic() + IMAGE_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                current = await get_json(session, f"{COMFY_URL}/history/{quote(prompt_id)}", timeout=5)
                if current and prompt_id in current:
                    history = current[prompt_id]
                    break
                await asyncio.sleep(0.75)
            if history is None:
                raise AppError(f"Bildauftrag überschritt {IMAGE_TIMEOUT_SECONDS} Sekunden.")

            status = history.get("status") or {}
            if status.get("status_str") == "error":
                messages = status.get("messages") or []
                raise AppError(f"ComfyUI-Fehler: {str(messages)[-1200:]}")

            images = ((history.get("outputs") or {}).get("13") or {}).get("images") or []
            if not images:
                raise AppError("ComfyUI meldet Abschluss, aber keine Bilddatei.")

            if not os.path.ismount(ARCHIVE_ROOT):
                raise AppError("Archiv-HDD ist nicht eingehängt. Bild wird nicht in den falschen Datenträger geschrieben.")

            day = datetime.now().strftime("%Y-%m-%d")
            destination = IMAGE_ARCHIVE / day / job_id
            destination.mkdir(parents=True, exist_ok=False)
            copied: list[dict[str, str]] = []
            previews: list[str] = []
            for image in images:
                filename = image.get("filename", "")
                subfolder = image.get("subfolder", "")
                source = safe_comfy_output(filename, subfolder)
                if not source.is_file():
                    raise AppError(f"ComfyUI-Ausgabe fehlt: {source}")
                target = destination / filename
                shutil.copy2(source, target)
                copied.append({"source": str(source), "archive": str(target)})
                previews.append(
                    f"{COMFY_URL}/view?filename={quote(filename)}&subfolder={quote(subfolder)}&type=output"
                )

            missing = [str(path) for path in MODEL_FILES.values() if not path.is_file()]
            if missing:
                raise AppError("Modellbestand ist unvollständig: " + ", ".join(missing))
            model_hashes = {
                name: await asyncio.to_thread(sha256_file, str(path))
                for name, path in MODEL_FILES.items()
            }
            workflow_hash = hashlib.sha256(canonical_json(template)).hexdigest()
            finished_at = utc_now()
            runtime = round(time.monotonic() - started_monotonic, 3)
            manifest = {
                "manifest_version": 1,
                "job_id": job_id,
                "comfy_prompt_id": prompt_id,
                "workflow_id": WORKFLOW_ID,
                "workflow_sha256": workflow_hash,
                "model_files": {name: str(path) for name, path in MODEL_FILES.items()},
                "model_sha256": model_hashes,
                "prompt": data["prompt"],
                "seed": data["seed"],
                "width": data["width"],
                "height": data["height"],
                "batch": 1,
                "steps": 4,
                "cfg": 1.0,
                "sampler": "euler",
                "started_at": started_at,
                "finished_at": finished_at,
                "runtime_seconds": runtime,
                "outputs": copied,
            }
            manifest_file = destination / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            return web.json_response(
                {
                    "ok": True,
                    "job_id": job_id,
                    "runtime_seconds": runtime,
                    "archive_directory": str(destination),
                    "manifest": str(manifest_file),
                    "previews": previews,
                }
            )
        except AppError as exc:
            return web.json_response({"ok": False, "job_id": job_id, "error": str(exc)}, status=500)
        except Exception as exc:
            return web.json_response(
                {"ok": False, "job_id": job_id, "error": f"Unerwarteter Fehler: {type(exc).__name__}: {exc}"},
                status=500,
            )
        finally:
            if entered_gpu:
                try:
                    await cleanup_gpu(request.app)
                except Exception:
                    pass


async def _sample_vram_peak(peak: dict[str, int | None]) -> None:
    while True:
        gpu = await gpu_status()
        if gpu is not None:
            used = int(gpu["used_mib"])
            current = peak.get("mib")
            if current is None or used > current:
                peak["mib"] = used
        await asyncio.sleep(0.5)


async def image_edit(request: web.Request) -> web.Response:
    try:
        data = parse_edit_request(await request.json())
    except (json.JSONDecodeError, web.HTTPBadRequest, AppError) as exc:
        message = str(exc) if isinstance(exc, AppError) else "Ungültige JSON-Anfrage."
        return web.json_response({"ok": False, "error": message}, status=400)

    stage_paths = [data["input"]["path"], *[item["path"] for item in data["references"]]]
    lock: asyncio.Lock = request.app["image_lock"]
    if lock.locked():
        cleanup_ui_stage_paths(stage_paths)
        return web.json_response(
            {"ok": False, "error": "Es läuft bereits ein Bildauftrag. Bitte warten."},
            status=409,
        )

    async with lock:
        started_monotonic = time.monotonic()
        started_at = utc_now()
        job_id = uuid.uuid4().hex[:12]
        staged_names: list[str] = []
        entered_gpu = False
        peak: dict[str, int | None] = {"mib": None}
        sampler: asyncio.Task | None = None
        try:
            try:
                preflight_edit_storage()
            except AppError as exc:
                return web.json_response({"ok": False, "job_id": job_id, "error": str(exc)}, status=503)

            missing = missing_edit_models()
            if missing:
                raise AppError("Qwen-Image-2.1-Gewichte fehlen: " + ", ".join(Path(item).name for item in missing))
            if not EDIT_WORKFLOW_FILE.is_file():
                raise AppError(f"Workflow fehlt: {EDIT_WORKFLOW_FILE}")

            entered_gpu = True
            await ensure_edit_image_mode(request.app)
            images = [data["input"], *data["references"]]
            staged_names = await stage_edit_inputs(job_id, images)
            template = json.loads(EDIT_WORKFLOW_FILE.read_text())
            workflow = build_edit_workflow(template, data, job_id, staged_names)

            session = request.app["session"]
            sampler = asyncio.create_task(_sample_vram_peak(peak))
            async with session.post(
                f"{COMFY_URL}/prompt",
                json={"prompt": workflow, "client_id": f"ki-arbeitsplatz-edit-{job_id}"},
                timeout=ClientTimeout(total=20),
            ) as response:
                result = await response.json(content_type=None)
                if response.status >= 300 or not result.get("prompt_id"):
                    raise AppError(f"ComfyUI hat den Auftrag abgelehnt: {result}")
            prompt_id = result["prompt_id"]

            history: dict[str, Any] | None = None
            deadline = time.monotonic() + EDIT_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                current = await get_json(session, f"{COMFY_URL}/history/{quote(prompt_id)}", timeout=5)
                if current and prompt_id in current:
                    history = current[prompt_id]
                    break
                await asyncio.sleep(0.75)
            if history is None:
                raise AppError(f"Bildbearbeitung überschritt {EDIT_TIMEOUT_SECONDS} Sekunden.")

            status = history.get("status") or {}
            if status.get("status_str") == "error":
                messages = status.get("messages") or []
                raise AppError(f"ComfyUI-Fehler: {str(messages)[-1200:]}")

            outputs = ((history.get("outputs") or {}).get("9") or {}).get("images") or []
            if not outputs:
                raise AppError("ComfyUI meldet Abschluss, aber keine Bilddatei.")

            if not os.path.ismount(ARCHIVE_ROOT):
                raise AppError("Archiv-HDD ist nicht eingehängt. Bild wird nicht in den falschen Datenträger geschrieben.")

            day = datetime.now().strftime("%Y-%m-%d")
            destination = IMAGE_ARCHIVE / day / job_id
            destination.mkdir(parents=True, exist_ok=False)
            copied: list[dict[str, str]] = []
            output_file: Path | None = None
            for image in outputs:
                filename = image.get("filename", "")
                subfolder = image.get("subfolder", "")
                source = safe_comfy_output(filename, subfolder)
                checked = validate_png_output(source)
                target = destination / filename
                shutil.copy2(source, target)
                copied.append({"archive": str(target), "sha256": checked["sha256"], "bytes": str(checked["bytes"])})
                if output_file is None:
                    output_file = target
            if output_file is None:
                raise AppError("Keine Ausgabedatei zum Archivieren.")
            output_info = validate_png_output(output_file)

            model_hashes = {
                name: await asyncio.to_thread(sha256_file, str(path))
                for name, path in EDIT_MODEL_FILES.items()
            }
            workflow_hash = hashlib.sha256(canonical_json(template)).hexdigest()
            finished_at = utc_now()
            runtime = round(time.monotonic() - started_monotonic, 3)
            quantization = {"dit": "int8", "encoder": "w4a8", "cache": "int8/cpu"}
            manifest = {
                "manifest_version": 1,
                "job_id": job_id,
                "comfy_prompt_id": prompt_id,
                "workflow_id": EDIT_WORKFLOW_ID,
                "workflow_sha256": workflow_hash,
                "model_files": {name: str(path) for name, path in EDIT_MODEL_FILES.items()},
                "model_sha256": model_hashes,
                "quantization": quantization,
                "instruction": data["instruction"],
                "preserve_alpha": data["preserve_alpha"],
                "input": public_image_ref(data["input"]),
                "references": [public_image_ref(item) for item in data["references"]],
                "input_sha256": data["input"]["sha256"],
                "reference_sha256": [item["sha256"] for item in data["references"]],
                "seed": data["seed"],
                "width": data["width"],
                "height": data["height"],
                "resolution": data["resolution"],
                "batch": 1,
                "steps": EDIT_STEPS,
                "cfg": EDIT_CFG,
                "sampler": "euler",
                "scheduler": "simple",
                "started_at": started_at,
                "finished_at": finished_at,
                "runtime_seconds": runtime,
                "vram_peak_mib": peak.get("mib"),
                "outputs": copied,
                "output_path": str(output_file),
                "output_sha256": output_info["sha256"],
                "error": None,
            }
            manifest_file = destination / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            return web.json_response(
                {
                    "ok": True,
                    "job_id": job_id,
                    "workflow_id": EDIT_WORKFLOW_ID,
                    "runtime_seconds": runtime,
                    "archive_directory": str(destination),
                    "output_path": str(output_file),
                    "manifest_path": str(manifest_file),
                    "manifest": str(manifest_file),
                    "workflow_sha256": workflow_hash,
                    "input_sha256": data["input"]["sha256"],
                    "reference_sha256": [item["sha256"] for item in data["references"]],
                    "output_sha256": output_info["sha256"],
                    "quantization": quantization,
                    "preserve_alpha": data["preserve_alpha"],
                    "seed": data["seed"],
                    "width": data["width"],
                    "height": data["height"],
                    "vram_peak_mib": peak.get("mib"),
                }
            )
        except AppError as exc:
            return web.json_response({"ok": False, "job_id": job_id, "error": str(exc)}, status=500)
        except Exception as exc:
            return web.json_response(
                {"ok": False, "job_id": job_id, "error": f"Unerwarteter Fehler: {type(exc).__name__}: {exc}"},
                status=500,
            )
        finally:
            if sampler is not None:
                sampler.cancel()
                await asyncio.gather(sampler, return_exceptions=True)
            cleanup_staged_inputs(staged_names)
            cleanup_ui_stage_paths(stage_paths)
            if entered_gpu:
                try:
                    await cleanup_gpu(request.app)
                except Exception:
                    pass


async def video_generate(request: web.Request) -> web.Response:
    try:
        data = parse_video_request(await request.json())
    except (json.JSONDecodeError, web.HTTPBadRequest, AppError) as exc:
        message = str(exc) if isinstance(exc, AppError) else "Ungültige JSON-Anfrage."
        return web.json_response({"ok": False, "error": message}, status=400)

    lock: asyncio.Lock = request.app["image_lock"]
    if lock.locked():
        return web.json_response(
            {"ok": False, "error": "Es läuft bereits ein Bild- oder Videoauftrag. Bitte warten."},
            status=409,
        )

    async with lock:
        started_monotonic = time.monotonic()
        started_at = utc_now()
        job_id = uuid.uuid4().hex[:12]
        staged_name: str | None = None
        entered_gpu = False
        peak: dict[str, int | None] = {"mib": None}
        sampler: asyncio.Task | None = None
        try:
            try:
                preflight_video_storage()
            except AppError as exc:
                return web.json_response({"ok": False, "job_id": job_id, "error": str(exc)}, status=503)

            missing = missing_video_models()
            if missing:
                raise AppError("Wan-2.2-Gewichte fehlen: " + ", ".join(Path(item).name for item in missing))
            if not VIDEO_WORKFLOW_FILE.is_file():
                raise AppError(f"Workflow fehlt: {VIDEO_WORKFLOW_FILE}")

            entered_gpu = True
            await ensure_video_mode(request.app)
            staged_name = await stage_video_input(job_id, data["input"])
            template = json.loads(VIDEO_WORKFLOW_FILE.read_text())
            workflow = build_video_workflow(template, data, job_id, staged_name)

            session = request.app["session"]
            sampler = asyncio.create_task(_sample_vram_peak(peak))
            async with session.post(
                f"{COMFY_URL}/prompt",
                json={"prompt": workflow, "client_id": f"ki-arbeitsplatz-video-{job_id}"},
                timeout=ClientTimeout(total=20),
            ) as response:
                result = await response.json(content_type=None)
                if response.status >= 300 or not result.get("prompt_id"):
                    raise AppError(f"ComfyUI hat den Auftrag abgelehnt: {result}")
            prompt_id = result["prompt_id"]

            history: dict[str, Any] | None = None
            deadline = time.monotonic() + VIDEO_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                current = await get_json(session, f"{COMFY_URL}/history/{quote(prompt_id)}", timeout=5)
                if current and prompt_id in current:
                    history = current[prompt_id]
                    break
                await asyncio.sleep(1.0)
            if history is None:
                raise AppError(f"Videoauftrag überschritt {VIDEO_TIMEOUT_SECONDS} Sekunden.")

            status = history.get("status") or {}
            if status.get("status_str") == "error":
                messages = status.get("messages") or []
                raise AppError(f"ComfyUI-Fehler: {str(messages)[-1200:]}")

            outputs = collect_comfy_media(history.get("outputs"), "58")
            if not outputs:
                raise AppError("ComfyUI meldet Abschluss, aber keine Videodatei.")

            if not os.path.ismount(ARCHIVE_ROOT):
                raise AppError("Archiv-HDD ist nicht eingehängt. Video wird nicht in den falschen Datenträger geschrieben.")

            day = datetime.now().strftime("%Y-%m-%d")
            destination = VIDEO_ARCHIVE / day / job_id
            destination.mkdir(parents=True, exist_ok=False)
            copied: list[dict[str, str]] = []
            output_file: Path | None = None
            previews: list[str] = []
            for item in outputs:
                filename = item.get("filename", "")
                subfolder = item.get("subfolder", "")
                source = safe_comfy_output(filename, subfolder)
                if not source.is_file():
                    raise AppError(f"ComfyUI-Ausgabe fehlt: {source}")
                if source.stat().st_size < 1024:
                    raise AppError(f"Videodatei ist zu klein: {source}")
                digest = await asyncio.to_thread(sha256_file, str(source))
                target = destination / filename
                shutil.copy2(source, target)
                copied.append(
                    {
                        "source": str(source),
                        "archive": str(target),
                        "sha256": digest,
                        "bytes": str(target.stat().st_size),
                    }
                )
                previews.append(
                    f"{COMFY_URL}/view?filename={quote(filename)}&subfolder={quote(subfolder)}&type=output"
                )
                if output_file is None:
                    output_file = target
            if output_file is None:
                raise AppError("Keine Ausgabedatei zum Archivieren.")

            model_hashes = {
                name: await asyncio.to_thread(sha256_file, str(path))
                for name, path in VIDEO_MODEL_FILES.items()
            }
            workflow_hash = hashlib.sha256(canonical_json(template)).hexdigest()
            finished_at = utc_now()
            runtime = round(time.monotonic() - started_monotonic, 3)
            manifest = {
                "manifest_version": 1,
                "job_id": job_id,
                "comfy_prompt_id": prompt_id,
                "workflow_id": VIDEO_WORKFLOW_ID,
                "workflow_sha256": workflow_hash,
                "model_files": {name: str(path) for name, path in VIDEO_MODEL_FILES.items()},
                "model_sha256": model_hashes,
                "prompt": data["prompt"],
                "input": public_image_ref(data["input"]),
                "input_sha256": data["input"]["sha256"],
                "seed": data["seed"],
                "width": data["width"],
                "height": data["height"],
                "length": data["length"],
                "batch": 1,
                "steps": VIDEO_STEPS,
                "cfg": VIDEO_CFG,
                "sampler": "uni_pc",
                "scheduler": "simple",
                "started_at": started_at,
                "finished_at": finished_at,
                "runtime_seconds": runtime,
                "vram_peak_mib": peak.get("mib"),
                "outputs": copied,
                "output_path": str(output_file),
                "error": None,
            }
            manifest_file = destination / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            return web.json_response(
                {
                    "ok": True,
                    "job_id": job_id,
                    "workflow_id": VIDEO_WORKFLOW_ID,
                    "runtime_seconds": runtime,
                    "archive_directory": str(destination),
                    "output_path": str(output_file),
                    "manifest": str(manifest_file),
                    "manifest_path": str(manifest_file),
                    "previews": previews,
                    "seed": data["seed"],
                    "width": data["width"],
                    "height": data["height"],
                    "length": data["length"],
                    "vram_peak_mib": peak.get("mib"),
                }
            )
        except AppError as exc:
            return web.json_response({"ok": False, "job_id": job_id, "error": str(exc)}, status=500)
        except Exception as exc:
            return web.json_response(
                {"ok": False, "job_id": job_id, "error": f"Unerwarteter Fehler: {type(exc).__name__}: {exc}"},
                status=500,
            )
        finally:
            if sampler is not None:
                sampler.cancel()
                await asyncio.gather(sampler, return_exceptions=True)
            if staged_name:
                cleanup_staged_inputs([staged_name])
            if entered_gpu:
                try:
                    await cleanup_gpu(request.app)
                except Exception:
                    pass


async def image_stage(request: web.Request) -> web.Response:
    sweep_old_ui_stage()
    try:
        reader = await request.multipart()
    except Exception:
        return web.json_response({"ok": False, "error": "Ungültiger Datei-Upload."}, status=400)
    field = await reader.next()
    if field is None or getattr(field, "name", None) != "file":
        return web.json_response({"ok": False, "error": "Bitte genau eine Bilddatei senden."}, status=400)
    raw_name = field.filename or "upload.png"
    suffix = Path(raw_name).suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        return web.json_response({"ok": False, "error": "Erlaubt sind nur PNG, JPEG und WebP."}, status=400)
    UI_STAGE_DIR.mkdir(parents=True, exist_ok=True)
    dest = UI_STAGE_DIR / f"{UI_STAGE_PREFIX}{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with dest.open("wb") as handle:
            while True:
                chunk = await field.read_chunk(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise AppError("Die Bilddatei darf höchstens 25 MiB groß sein.")
                handle.write(chunk)
        if size <= 0:
            raise AppError("Die Bilddatei ist leer.")
        info = inspect_image_file(dest)
    except AppError as exc:
        dest.unlink(missing_ok=True)
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        return web.json_response({"ok": False, "error": f"Upload fehlgeschlagen: {type(exc).__name__}: {exc}"}, status=500)
    display_name = Path(raw_name).name
    if display_name != Path(display_name).name or display_name in {"", ".", ".."}:
        display_name = dest.name
    return web.json_response(
        {
            "ok": True,
            "path": str(dest.resolve()),
            "name": display_name,
            "width": info["width"],
            "height": info["height"],
            "bytes": info["bytes"],
            "kind": info["kind"],
        }
    )


async def image_job_output(request: web.Request) -> web.StreamResponse:
    try:
        path = find_job_output(request.match_info["job_id"])
        validate_png_output(path)
    except AppError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=404)
    return web.FileResponse(path, headers={"Content-Type": "image/png"})


def embed_origins() -> set[str]:
    return {
        f"http://127.0.0.1:{UI_PORT}",
        f"http://127.0.0.1:{QWEN_PROXY_PORT}",
        QWEN_UPSTREAM.rstrip("/"),
    }


def cors_allow_origin(request_origin: str | None) -> str | None:
    if request_origin in embed_origins():
        return request_origin
    return None


def filtered_request_headers(request: web.Request) -> dict[str, str]:
    drop = HOP_BY_HOP | DROP_UPSTREAM_REQUEST_HEADERS
    return {name: value for name, value in request.headers.items() if name.lower() not in drop}


def apply_embed_cors(request: web.Request, response: web.StreamResponse) -> None:
    allowed = cors_allow_origin(request.headers.get("Origin"))
    if not allowed:
        return
    response.headers["Access-Control-Allow-Origin"] = allowed
    response.headers["Vary"] = "Origin"


def copy_proxy_headers(upstream, response: web.StreamResponse, request: web.Request) -> None:
    for name, value in upstream.headers.items():
        lower = name.lower()
        if lower in HOP_BY_HOP or lower in {
            "x-frame-options",
            "content-security-policy",
            "access-control-allow-origin",
        }:
            continue
        response.headers.add(name, value)
    csp = upstream.headers.get("Content-Security-Policy")
    if csp:
        csp = csp.replace(
            "frame-ancestors 'none'",
            f"frame-ancestors http://127.0.0.1:{UI_PORT}",
        )
        response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    apply_embed_cors(request, response)


async def qwen_websocket_proxy(request: web.Request, target: str) -> web.WebSocketResponse:
    requested_protocols = [
        item.strip()
        for item in request.headers.get("Sec-WebSocket-Protocol", "").split(",")
        if item.strip()
    ]
    browser_ws = web.WebSocketResponse(protocols=requested_protocols, heartbeat=30)
    await browser_ws.prepare(request)
    headers = filtered_request_headers(request)
    for name in list(headers):
        if name.lower().startswith("sec-websocket-"):
            headers.pop(name)

    try:
        upstream_ws = await request.app["proxy_session"].ws_connect(
            target,
            protocols=requested_protocols,
            headers=headers,
            heartbeat=30,
            timeout=20,
        )
    except Exception as exc:
        await browser_ws.close(code=1011, message=f"Qwen-Verbindung fehlgeschlagen: {exc}".encode()[:120])
        return browser_ws

    async def browser_to_upstream() -> None:
        async for message in browser_ws:
            if message.type == WSMsgType.TEXT:
                await upstream_ws.send_str(message.data)
            elif message.type == WSMsgType.BINARY:
                await upstream_ws.send_bytes(message.data)
            elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                break

    async def upstream_to_browser() -> None:
        async for message in upstream_ws:
            if message.type == WSMsgType.TEXT:
                await browser_ws.send_str(message.data)
            elif message.type == WSMsgType.BINARY:
                await browser_ws.send_bytes(message.data)
            elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                break

    tasks = [asyncio.create_task(browser_to_upstream()), asyncio.create_task(upstream_to_browser())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*done, *pending, return_exceptions=True)
    await upstream_ws.close()
    await browser_ws.close()
    return browser_ws


async def qwen_proxy(request: web.Request) -> web.StreamResponse:
    if request.method == "OPTIONS":
        response = web.Response(status=204)
        apply_embed_cors(request, response)
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = request.headers.get(
            "Access-Control-Request-Headers", "content-type"
        )
        return response
    target = f"{QWEN_UPSTREAM}{request.rel_url}"
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await qwen_websocket_proxy(request, target)

    body = await request.read()
    try:
        validate_qwen_proxy_mutation(request.path, request.method, body)
    except AppError as exc:
        return web.json_response({"error": str(exc), "code": "local_provider_only"}, status=403)

    if request.method == "GET" and request.path == "/workspace/auth/providers":
        return web.json_response(
            {
                "v": 1,
                "workspaceCwd": "/srv/ai/workspaces",
                "providers": [],
                "groups": [],
                "localOnly": True,
            }
        )

    special_provider_status = request.method == "GET" and request.path == "/workspace/providers"
    headers = filtered_request_headers(request)
    if special_provider_status:
        headers.pop("Accept-Encoding", None)
    async with request.app["proxy_session"].request(
        request.method,
        target,
        headers=headers,
        data=body if body else None,
        allow_redirects=False,
        timeout=ClientTimeout(total=None, sock_connect=10, sock_read=None),
    ) as upstream:
        if special_provider_status:
            raw = await upstream.read()
            if upstream.status != 200:
                return web.Response(status=upstream.status, body=raw, content_type="application/json")
            try:
                filtered = filter_local_qwen_providers(json.loads(raw))
            except (json.JSONDecodeError, AppError) as exc:
                return web.json_response({"error": str(exc), "code": "local_provider_filter_failed"}, status=503)
            resp = web.json_response(filtered)
            apply_embed_cors(request, resp)
            return resp
        response = web.StreamResponse(status=upstream.status, reason=upstream.reason)
        copy_proxy_headers(upstream, response, request)
        await response.prepare(request)
        async for chunk in upstream.content.iter_chunked(64 * 1024):
            await response.write(chunk)
        await response.write_eof()
        return response


def create_ui_app(session: ClientSession) -> web.Application:
    app = web.Application(middlewares=[local_only, security_headers], client_max_size=28 * 1024 * 1024)
    app["session"] = session
    app["image_lock"] = asyncio.Lock()
    app["boot"] = boot_payload("idle", mode=None)
    app.router.add_get("/", index)
    app.router.add_get("/index.html", index)
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/mode/{mode}", api_mode)
    app.router.add_post("/api/gpu/cleanup", api_gpu_cleanup)
    app.router.add_post("/api/images/generate", image_generate)
    app.router.add_post("/api/images/edit", image_edit)
    app.router.add_post("/api/images/stage", image_stage)
    app.router.add_get("/api/images/jobs/{job_id}/output", image_job_output)
    app.router.add_post("/api/videos/generate", video_generate)
    return app


def create_proxy_app(session: ClientSession) -> web.Application:
    app = web.Application(middlewares=[local_only], client_max_size=16 * 1024 * 1024)
    app["proxy_session"] = session
    app.router.add_route("*", "/{tail:.*}", qwen_proxy)
    return app


async def async_main() -> None:
    if HOST in {"0.0.0.0", "::", ""}:
        raise SystemExit("KI-Arbeitsplatz bindet ausschließlich an 127.0.0.1")
    timeout = ClientTimeout(total=60)
    async with ClientSession(timeout=timeout) as session, ClientSession(auto_decompress=False) as proxy_session:
        ui_runner = web.AppRunner(create_ui_app(session), access_log=None)
        proxy_runner = web.AppRunner(create_proxy_app(proxy_session), access_log=None)
        await ui_runner.setup()
        await proxy_runner.setup()
        await web.TCPSite(ui_runner, HOST, UI_PORT).start()
        await web.TCPSite(proxy_runner, HOST, QWEN_PROXY_PORT).start()
        print(f"KI-Arbeitsplatz: http://{HOST}:{UI_PORT}", flush=True)
        print(f"Qwen-Einbettungsproxy: http://{HOST}:{QWEN_PROXY_PORT}", flush=True)

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()
        await proxy_runner.cleanup()
        await ui_runner.cleanup()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
