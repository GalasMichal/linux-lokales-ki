"""Visual PDF layout QA via local Ollama /api/chat. No Qwen Serve, no extra models."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from errors import ToolError
from paths import resolve_existing_file, resolve_workspace
from pdf_tools import PNG_SUFFIX, PDF_SUFFIX, RENDER_DPI, pdf_inspect, pdf_render, _parse_pages


OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
VISION_MODEL = "local-quality"
MAX_PAGES = 8
PAGE_TIMEOUT_S = 180
ISSUE_TYPES = (
    "clipped_text",
    "overlap",
    "text_too_small",
    "empty_page",
    "broken_table",
    "image_error",
    "bad_alignment",
    "bad_spacing",
    "overflow",
    "other",
)
SEVERITIES = ("low", "medium", "high")

PAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "issues"],
    "properties": {
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "severity", "description", "confidence"],
                "properties": {
                    "type": {"type": "string", "enum": list(ISSUE_TYPES)},
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "description": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        },
    },
}

SYSTEM_PROMPT = (
    "Visual PDF layout inspector. Look only at layout, not grammar or content quality. "
    "Report clipped/overflow text, overlaps, tiny type, broken/cut tables, "
    "bad alignment/spacing, missing or broken images. "
    "A blank or nearly blank page MUST include type empty_page with severity high. "
    "If the page is usable and not empty, issues=[]."
)
USER_PROMPT = "Inspect this PDF page render. Layout issues only. JSON."


def pdf_vision_qa(
    path: str,
    pages: str = "",
    strict: bool = False,
    workspace: str = "",
    chat_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if workspace.strip():
        resolve_workspace(workspace)
    source = resolve_existing_file(path, PDF_SUFFIX | PNG_SUFFIX)
    jobs = _jobs_for_path(source, pages)
    page_results: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    invalid = False
    for job in jobs:
        result = _inspect_page(job, chat_fn=chat_fn)
        page_results.append(result)
        issues.extend(result["issues"])
        if result.get("invalid_output"):
            invalid = True
    high = [item for item in issues if item.get("severity") == "high"]
    medium = [item for item in issues if item.get("severity") == "medium"]
    needs = bool(high) or (strict and bool(medium)) or invalid
    ok = (not needs) and (not invalid)
    summaries = [str(item.get("summary") or "").strip() for item in page_results]
    summaries = [text for text in summaries if text]
    return {
        "ok": ok,
        "needs_regeneration": needs,
        "pages_checked": [job["page"] for job in jobs],
        "summary": " | ".join(summaries)[:1200],
        "issues": issues,
        "strict": bool(strict),
        "model": VISION_MODEL,
        "endpoint": OLLAMA_CHAT_URL,
        "invalid_output": invalid,
        "pages": page_results,
        "source": str(source),
    }


def validate_page_payload(payload: Any, page: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ToolError("Vision-Antwort ist kein JSON-Objekt.")
    summary = payload.get("summary")
    if not isinstance(summary, str):
        raise ToolError("Vision-Antwort: summary muss ein String sein.")
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        raise ToolError("Vision-Antwort: issues muss eine Liste sein.")
    issues: list[dict[str, Any]] = []
    for item in raw_issues:
        issues.append(_validate_issue(item, page))
    extra = set(payload) - {"summary", "issues"}
    if extra:
        raise ToolError(f"Vision-Antwort hat unerwartete Felder: {sorted(extra)}")
    return {"summary": summary.strip(), "issues": issues}


def _jobs_for_path(source: Path, pages: str) -> list[dict[str, Any]]:
    if source.suffix.lower() in PNG_SUFFIX:
        return [{"page": 1, "png": source, "rendered": False}]
    inspected = pdf_inspect(str(source))
    page_count = int(inspected["pages"])
    selected = _parse_pages(pages, page_count)
    if len(selected) > MAX_PAGES:
        raise ToolError(f"Höchstens {MAX_PAGES} Seiten pro Vision-QA. Angefragt: {len(selected)}.")
    jobs = []
    for number in selected:
        dest = source.with_name(f"{source.stem}.vision-p{number}.png")
        rendered = pdf_render(str(source), str(dest), page=number, dpi=RENDER_DPI)
        jobs.append({"page": number, "png": Path(rendered["path"]), "rendered": True, "width": rendered.get("width")})
    return jobs


def _inspect_page(job: dict[str, Any], chat_fn: Callable[..., dict[str, Any]] | None) -> dict[str, Any]:
    page = int(job["page"])
    png = Path(job["png"])
    t0 = time.perf_counter()
    try:
        raw = (chat_fn or ollama_vision_chat)(png)
        payload = _parse_json_object(raw.get("content") if isinstance(raw, dict) else raw)
        checked = validate_page_payload(payload, page)
        if _nearly_blank_png(png) and not any(item["type"] == "empty_page" for item in checked["issues"]):
            checked["issues"].append(
                {
                    "page": page,
                    "type": "empty_page",
                    "severity": "high",
                    "description": "Seite ist visuell leer oder fast leer.",
                    "confidence": 1.0,
                }
            )
            if not checked["summary"]:
                checked["summary"] = "Leere Seite."
        elapsed = round(time.perf_counter() - t0, 3)
        return {
            "page": page,
            "path": str(png),
            "summary": checked["summary"],
            "issues": checked["issues"],
            "elapsed_s": elapsed,
            "invalid_output": False,
            "prompt_eval_count": raw.get("prompt_eval_count") if isinstance(raw, dict) else None,
            "eval_count": raw.get("eval_count") if isinstance(raw, dict) else None,
            "vram": raw.get("vram") if isinstance(raw, dict) else None,
        }
    except ToolError as exc:
        elapsed = round(time.perf_counter() - t0, 3)
        if _nearly_blank_png(png):
            return {
                "page": page,
                "path": str(png),
                "summary": "Leere Seite.",
                "issues": [
                    {
                        "page": page,
                        "type": "empty_page",
                        "severity": "high",
                        "description": "Seite ist visuell leer oder fast leer.",
                        "confidence": 1.0,
                    }
                ],
                "elapsed_s": elapsed,
                "invalid_output": False,
            }
        return {
            "page": page,
            "path": str(png),
            "summary": f"Ungültige Vision-Antwort: {exc}",
            "issues": [
                {
                    "page": page,
                    "type": "other",
                    "severity": "high",
                    "description": f"Modellausgabe nicht schema-gültig: {exc}",
                    "confidence": 1.0,
                }
            ],
            "elapsed_s": elapsed,
            "invalid_output": True,
        }


def ollama_vision_chat(png: Path) -> dict[str, Any]:
    if not png.is_file():
        raise ToolError(f"PNG fehlt: {png}")
    image_b64 = base64.b64encode(png.read_bytes()).decode("ascii")
    body = {
        "model": VISION_MODEL,
        "stream": False,
        "think": False,
        "format": PAGE_SCHEMA,
        "options": {"temperature": 0.1, "num_predict": 400},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT, "images": [image_b64]},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=PAGE_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ToolError(f"Ollama Vision nicht erreichbar auf {OLLAMA_CHAT_URL}: {exc}") from exc
    except TimeoutError as exc:
        raise ToolError(f"Ollama Vision-Timeout nach {PAGE_TIMEOUT_S}s.") from exc
    message = payload.get("message") if isinstance(payload, dict) else None
    content = ""
    if isinstance(message, dict):
        content = str(message.get("content") or "")
    return {
        "content": content,
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "eval_count": payload.get("eval_count"),
        "eval_duration": payload.get("eval_duration"),
        "load_duration": payload.get("load_duration"),
        "model": payload.get("model"),
        "done_reason": payload.get("done_reason"),
    }


def _parse_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        raise ToolError("Leere Vision-Antwort.")
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolError(f"Vision-Antwort ist kein JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ToolError("Vision-JSON ist kein Objekt.")
    return parsed


def _validate_issue(item: Any, page: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ToolError("Issue ist kein Objekt.")
    kind = item.get("type")
    severity = item.get("severity")
    description = item.get("description")
    confidence = item.get("confidence")
    if kind not in ISSUE_TYPES:
        raise ToolError(f"Unbekannter Issue-Typ: {kind}")
    if severity not in SEVERITIES:
        raise ToolError(f"Ungültige Severity: {severity}")
    if not isinstance(description, str) or not description.strip():
        raise ToolError("Issue-Beschreibung fehlt.")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ToolError("confidence muss eine Zahl sein.")
    conf = float(confidence)
    if 1.0 < conf <= 100.0:
        conf = conf / 100.0
    if not 0.0 <= conf <= 1.0:
        raise ToolError("confidence muss zwischen 0 und 1 liegen.")
    return {
        "page": page,
        "type": kind,
        "severity": severity,
        "description": description.strip(),
        "confidence": conf,
    }


def _nearly_blank_png(png: Path, threshold: float = 0.004) -> bool:
    """True when almost all pixels are near-white. Local safety net, not a vision call."""
    try:
        from PIL import Image
    except Exception:
        return False
    with Image.open(png) as image:
        hist = image.convert("L").histogram()
    total = sum(hist) or 1
    ink = sum(hist[:250])
    return (ink / total) < threshold

