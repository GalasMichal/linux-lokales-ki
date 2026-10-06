"""Host-testable rules for Open WebUI image tools. No Open WebUI imports."""

from __future__ import annotations

import re
from typing import Any

ALLOWED_SIZES = (512, 768, 1024)
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/jpg"}
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

SECOND_EDIT_PATTERNS = (
    re.compile(r"bearbeite das ergebnis", re.I),
    re.compile(r"nimm das zuletzt erzeugte", re.I),
    re.compile(r"nimm dieses ergebnis", re.I),
    re.compile(r"nimm das letzte (?:bild|ergebnis)", re.I),
    re.compile(r"\ban diesem ergebnis\b", re.I),
    re.compile(r"noch einmal bearbeiten", re.I),
    re.compile(r"zusätzlich den hintergrund", re.I),
    re.compile(r"use the last (?:generated|edited) image", re.I),
    re.compile(r"take this result", re.I),
    re.compile(r"edit the result again", re.I),
    re.compile(r"change (?:this|the) result", re.I),
    re.compile(r"additionally change", re.I),
)

ACK_PATTERNS = (
    re.compile(r"^\s*danke\b", re.I),
    re.compile(r"sieht gut aus", re.I),
    re.compile(r"passt so\b", re.I),
    re.compile(r"super, danke", re.I),
    re.compile(r"^\s*thanks\b", re.I),
    re.compile(r"looks good", re.I),
)

SIZE_IN_TEXT = re.compile(r"\b(512|768|1024)\b")


def snap_edit_size(width: int, height: int) -> tuple[int, int]:
    """Map original pixel size onto the frozen 512/768/1024 ladder. Never above 1024."""
    longest = max(int(width), int(height))
    if longest <= 640:
        size = 512
    elif longest <= 896:
        size = 768
    else:
        size = 1024
    return size, size


def parse_requested_size(width: Any, height: Any) -> tuple[int, int] | None:
    """Return a supported pair only if the caller named a legal size. None means omit."""
    if width in (None, "", "null") and height in (None, "", "null"):
        return None
    try:
        if width in (None, "", "null"):
            w = int(height)
        elif height in (None, "", "null"):
            w = int(width)
        else:
            w = int(width)
            h = int(height)
            if w != h:
                w = max(w, h)
    except (TypeError, ValueError):
        return None
    if w not in ALLOWED_SIZES:
        return None
    return w, w


def requested_size_from_text(text: str) -> tuple[int, int] | None:
    """Only honor a size the user actually wrote. Models often invent 1024."""
    matches = SIZE_IN_TEXT.findall(text or "")
    if not matches:
        return None
    size = int(matches[-1])
    if size not in ALLOWED_SIZES:
        return None
    return size, size


def resolve_named_size(text: str, width: Any = None, height: Any = None) -> tuple[int, int] | None:
    named = requested_size_from_text(text)
    if named:
        return named
    return None


def is_explicit_second_edit(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    return any(pattern.search(raw) for pattern in SECOND_EDIT_PATTERNS)


def is_non_edit_ack(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if is_explicit_second_edit(raw):
        return False
    return any(pattern.search(raw) for pattern in ACK_PATTERNS)


def normalize_file_item(item: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    nested = item.get("file") if isinstance(item.get("file"), dict) else {}
    nested_meta = nested.get("meta") if isinstance(nested.get("meta"), dict) else {}
    item_meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    content = (
        item.get("content_type")
        or item.get("mime")
        or nested.get("content_type")
        or nested_meta.get("content_type")
        or item_meta.get("content_type")
        or ""
    )
    name = (
        item.get("name")
        or item.get("filename")
        or nested.get("filename")
        or nested.get("meta", {}).get("name")
        or item.get("id")
        or nested.get("id")
        or ""
    )
    return {
        "id": item.get("id") or nested.get("id"),
        "type": item.get("type") or nested.get("type") or "file",
        "name": name,
        "content_type": content,
        "path": item.get("path") or nested.get("path") or "",
        "url": item.get("url") or nested.get("url") or "",
        "local_ki_output": bool(item.get("local_ki_output") or nested.get("local_ki_output")),
        "raw": item,
    }


def is_ki_result_file(item: dict[str, Any]) -> bool:
    data = normalize_file_item(item)
    if not data:
        return False
    if data.get("local_ki_output"):
        return True
    kind = str(data.get("type") or "").lower()
    url = str(data.get("url") or "")
    if kind == "image" and not data.get("id") and url.startswith("data:"):
        return True
    return False


def is_image_upload(item: dict[str, Any]) -> bool:
    data = normalize_file_item(item)
    if not data or is_ki_result_file(item):
        return False
    kind = str(data.get("type") or "file").lower()
    content = str(data.get("content_type") or "").lower()
    name = str(data.get("name") or "").lower()
    if kind == "image" and data.get("id"):
        return True
    if kind == "image":
        return False
    if content in IMAGE_TYPES or content.startswith("image/"):
        return True
    return name.endswith(IMAGE_SUFFIXES)


def choose_source_file(
    files: list[dict[str, Any]] | None,
    instruction: str,
    *,
    last_job_id: str | None = None,
) -> dict[str, Any]:
    """Pick the original user upload unless the user explicitly asks to edit the last KI result."""
    items = [item for item in (files or []) if isinstance(item, dict)]
    uploads = [item for item in items if is_image_upload(item)]
    results = [item for item in items if is_ki_result_file(item)]
    if is_explicit_second_edit(instruction):
        if last_job_id:
            return {"source": "last_job", "job_id": last_job_id}
        if results:
            return {"source": "ki_result", "file": normalize_file_item(results[-1])}
        raise ValueError("Kein vorheriges KI-Ergebnis in diesem Chat. Bitte ein Originalbild hochladen.")
    if uploads:
        return {"source": "original", "file": normalize_file_item(uploads[0])}
    raise ValueError("Bitte zuerst ein Originalbild hochladen. Ein KI-Ergebnis wird nicht automatisch weiterbearbeitet.")
