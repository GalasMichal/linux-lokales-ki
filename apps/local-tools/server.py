#!/usr/bin/env python3
"""Local-only MCP gateway shared by Qwen Code and Open WebUI."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from desktop_session import (
    desktop_click as click_desktop,
    desktop_close as close_desktop,
    desktop_focus as focus_desktop,
    desktop_key as key_desktop,
    desktop_screenshot as shoot_desktop,
    desktop_scroll as scroll_desktop,
    desktop_snapshot as snap_desktop,
    desktop_type as type_desktop,
)
from browser_session import (
    browser_back as go_back,
    browser_click as click_browser,
    browser_close as close_browser,
    browser_open as open_browser,
    browser_screenshot as shoot_browser,
    browser_scroll as scroll_browser,
    browser_snapshot as snap_browser,
    browser_type as type_browser,
)
from errors import ToolError
from gateway import (
    edit_image_via_workplace,
    generate_image_via_workplace,
    generate_video_via_workplace,
)
from knowledge import knowledge_get as get_knowledge
from knowledge import knowledge_record as record_knowledge
from knowledge import knowledge_search as search_knowledge
from memory import memory_load as load_memory
from memory import memory_update as update_memory
from pdf_tools import (
    capabilities as pdf_capabilities,
    pdf_create as create_pdf,
    pdf_edit as edit_pdf,
    pdf_inspect as inspect_pdf,
    pdf_merge as merge_pdf,
    pdf_ocr as ocr_pdf,
    pdf_read as read_pdf,
    pdf_render as render_pdf,
    pdf_split as split_pdf,
)
from pdf_vision import pdf_vision_qa as vision_qa
from moe_consult import moe_consult as consult_moe


SERVER_VERSION = "1.8.0"
WORKFLOW_ID = "flux2-klein-t2i-v1"
VIDEO_WORKFLOW_ID = "wan22-ti2v-5b-v1"
TOOL_NAMES = [
    "generate_image",
    "edit_image",
    "generate_video",
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
]

mcp = MCPServer(
    "local-ai-tools",
    version=SERVER_VERSION,
    instructions=(
        "Lokale Werkzeuge: Bild erzeugen (FLUX.2-klein), Bild bearbeiten (Qwen-Image-2.1), "
        "Video aus Foto (Wan 2.2 TI2V-5B / generate_video), "
        "projektbezogenes .agent-Memory, Knowledge Base (search/get/record), PDF/Dokument-Arbeit, "
        "on-demand CPU-MoE Zweitmeinung (moe_consult), "
        "ein isolierter Browser und ein kontrollierter Desktop. Alles localhost, keine Cloud. "
        "Webseiten nur über browser_*-Tools. Native Fenster nur über desktop_*-Tools. "
        "Kein Terminal, kein Passwort, kein Shell. "
        "moe_consult nur für Architektur/Review/komplexe Pläne — nicht für triviale Edits."
    ),
)

_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
_READ = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
_BROWSER = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)
_DESKTOP = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)


def _tool_result(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except ToolError as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool(annotations=_WRITE)
async def generate_image(
    prompt: str,
    width: Literal[512, 768, 1024] = 1024,
    height: Literal[512, 768, 1024] = 1024,
    seed: int = 42,
    workflow_id: Literal["flux2-klein-t2i-v1"] = WORKFLOW_ID,
    size: str | None = None,
) -> dict[str, Any]:
    """Generate a local image from a text prompt. Use this when the user asks to create, generate, or draw a picture.

    Registered call name is mcp__local-tools__generate_image. Do not use Shell, Git, tool_search, or zoom_image.
    Preferred args: prompt, width, height, seed. Optional size like 512x512 is accepted. Batch is always 1.
    """
    if isinstance(size, str) and "x" in size.lower():
        parts = size.lower().replace(" ", "").split("x", 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            width, height = int(parts[0]), int(parts[1])
    try:
        return await generate_image_via_workplace(prompt, width, height, seed, workflow_id)
    except ToolError as exc:
        return {"ok": False, "error": str(exc), "workflow_id": WORKFLOW_ID}


@mcp.tool(annotations=_WRITE)
async def edit_image(
    instruction: str,
    input_path: str,
    reference_paths: list[str] | None = None,
    width: Literal[512, 768, 1024] = 1024,
    height: Literal[512, 768, 1024] = 1024,
    seed: int = 42,
    preserve_alpha: bool = False,
) -> dict[str, Any]:
    """Edit a local image with Qwen-Image-2.1. Use this when the user asks to change, edit, or restyle an existing picture.

    Registered call name is mcp__local-tools__edit_image. Do not use Shell, Git, tool_search, or generate_image for edits.
    input_path is a local file (png/jpg/jpeg/webp). Optionally up to two reference_paths. No URL, no Base64, no workflow_id.
    """
    try:
        return await edit_image_via_workplace(
            instruction,
            input_path,
            reference_paths,
            width,
            height,
            seed,
            preserve_alpha,
        )
    except ToolError as exc:
        return {"ok": False, "error": str(exc), "workflow_id": "qwen-image-21-edit-v1"}


@mcp.tool(annotations=_WRITE)
async def generate_video(
    prompt: str,
    input_path: str,
    width: Literal[704, 1280, 480, 832] = 704,
    height: Literal[1280, 704, 832, 480] = 1280,
    length: Literal[49, 81] = 49,
    seed: int = 42,
) -> dict[str, Any]:
    """Create a short local video from one photo (Wan 2.2 TI2V-5B). Use for TikTok-style image-to-video.

    Registered call name is mcp__local-tools__generate_video. Do not use Shell or generate_image for video.
    input_path is a local png/jpg/jpeg/webp. Allowed sizes: 704x1280, 1280x704, 480x832, 832x480. Length 49 or 81 frames.
    """
    try:
        return await generate_video_via_workplace(prompt, input_path, width, height, length, seed)
    except ToolError as exc:
        return {"ok": False, "error": str(exc), "workflow_id": VIDEO_WORKFLOW_ID}


@mcp.tool(annotations=_READ)
async def memory_load(workspace: str, files: str = "") -> dict[str, Any]:
    """Load compact persistent project memory from `.agent/` before a task. Never rely on chat history alone.

    files is a comma list of STATE.md,REQUIREMENTS.md,DECISIONS.md,TASKS.md,TOOLS.md. Empty loads all.
    History is listed by name only and is not dumped into the prompt.
    """
    wanted = [item.strip() for item in files.split(",") if item.strip()] or None
    return await asyncio.to_thread(_tool_result, load_memory, workspace, wanted)


@mcp.tool(annotations=_WRITE)
async def memory_update(
    workspace: str,
    summary: str,
    state: str = "",
    tasks: str = "",
    decisions: str = "",
    decision_title: str = "",
    requirements: str = "",
    tools: str = "",
) -> dict[str, Any]:
    """Update `.agent/` after a finished task. DECISIONS.md is append-only; old entries are never overwritten.

    Provide only fields that changed. summary is required. Snapshots go to `.agent/history/`.
    """
    return await asyncio.to_thread(
        _tool_result,
        update_memory,
        workspace,
        summary,
        state or None,
        tasks or None,
        decisions or None,
        decision_title or None,
        requirements or None,
        tools or None,
    )


@mcp.tool(annotations=_READ)
async def knowledge_search(workspace: str, query: str, max_results: int = 5, types: str = "") -> dict[str, Any]:
    """Search long-term project knowledge before repairing errors or making architecture choices.

    Returns a compact package (decisions/failures/fixes/fallbacks), not the whole store.
    Use for errors, regressions, replans, and research — not every trivial edit.
    types is an optional comma list: decision,failure,fix,fallback,replan,research,success.
    """
    return await asyncio.to_thread(_tool_result, search_knowledge, workspace, query, max_results, types)


@mcp.tool(annotations=_READ)
async def knowledge_get(workspace: str, id: str) -> dict[str, Any]:
    """Load one knowledge entry by stable id (e.g. KB-20260922-LEDGER-002). Use after knowledge_search."""
    return await asyncio.to_thread(_tool_result, get_knowledge, workspace, id)


@mcp.tool(annotations=_WRITE)
async def knowledge_record(
    workspace: str,
    type: str,
    topic: str,
    summary: str,
    status: str = "active",
    reason: str = "",
    cause: str = "",
    result: str = "",
    do_not_repeat: bool = False,
    supersedes: str = "",
    relates_to: str = "",
    fixes: str = "",
    fallback_for: str = "",
    evidence: str = "",
    source: str = "",
    confidence: str = "",
    keywords: str = "",
    findings: str = "",
    question: str = "",
    force_new: bool = False,
) -> dict[str, Any]:
    """Record a decision, failure, fix, fallback, replan, research, or success pattern.

    Dedupes identical type+topic+summary (updates evidence). Use supersedes to retire an old decision.
    evidence is a comma list of repo-relative paths. No secrets. Not for trivial chat notes.
    """
    return await asyncio.to_thread(
        _tool_result,
        record_knowledge,
        workspace,
        type,
        topic,
        summary,
        status,
        reason,
        cause,
        result,
        do_not_repeat,
        supersedes,
        relates_to,
        fixes,
        fallback_for,
        evidence,
        source,
        confidence,
        keywords,
        findings,
        question,
        force_new,
    )


@mcp.tool(annotations=_READ)
async def pdf_read(path: str, pages: str = "", max_chars: int = 20000) -> dict[str, Any]:
    """Extract text from a local PDF. pages like '1-3,5'; empty reads all up to max_chars."""
    return await asyncio.to_thread(_tool_result, read_pdf, path, pages, max_chars)


@mcp.tool(annotations=_READ)
async def pdf_inspect(path: str) -> dict[str, Any]:
    """Inspect a local PDF: page count, sizes, metadata, whether pages have text."""
    return await asyncio.to_thread(_tool_result, inspect_pdf, path)


@mcp.tool(annotations=_WRITE)
async def pdf_create(output: str, text: str = "", source_path: str = "", title: str = "", workspace: str = "") -> dict[str, Any]:
    """Create a local PDF from text or a .txt/.md file. Runs QA (reopen, text, render) afterwards."""
    return await asyncio.to_thread(_tool_result, create_pdf, output, text, source_path, title, workspace)


@mcp.tool(annotations=_WRITE)
async def pdf_edit(
    path: str,
    output: str,
    replacements: str = "",
    new_text: str = "",
    mode: str = "auto",
    workspace: str = "",
) -> dict[str, Any]:
    """Edit a local PDF. Default/auto with replacements = in-place replace (keeps layout).

    replacements: 'old=>new;foo=>bar'. Prefer same-length new text (pad spaces).
    mode=replace|auto → layout-preserving redact replace.
    mode=recreate|soffice or non-empty new_text → rebuild (NOT for 1:1 Vorlage).
    For Vorlage/1:1: always mode=replace, never new_text.
    """
    return await asyncio.to_thread(_tool_result, edit_pdf, path, output, replacements, new_text, mode, workspace)


@mcp.tool(annotations=_WRITE)
async def pdf_merge(paths: str, output: str, workspace: str = "") -> dict[str, Any]:
    """Merge local PDFs. paths is a comma-separated list of at least two PDF files."""
    return await asyncio.to_thread(_tool_result, merge_pdf, paths, output, workspace)


@mcp.tool(annotations=_WRITE)
async def pdf_split(path: str, output_dir: str, pages: str = "", workspace: str = "") -> dict[str, Any]:
    """Split a local PDF. Empty pages writes one file per page. pages like '2-3' writes that range."""
    return await asyncio.to_thread(_tool_result, split_pdf, path, output_dir, pages, workspace)


@mcp.tool(annotations=_WRITE)
async def pdf_ocr(path: str, output: str, languages: str = "deu+eng", workspace: str = "") -> dict[str, Any]:
    """OCR a local PDF with OCRmyPDF/Tesseract. Skips pages that already have text. Completely local."""
    return await asyncio.to_thread(_tool_result, ocr_pdf, path, output, languages, workspace)


@mcp.tool(annotations=_WRITE)
async def pdf_render(path: str, output: str, page: int = 1, dpi: int = 140, workspace: str = "") -> dict[str, Any]:
    """Render one PDF page to PNG. The image is vision-ready; call pdf_vision_qa separately for layout QA."""
    return await asyncio.to_thread(_tool_result, render_pdf, path, output, page, dpi, workspace)


@mcp.tool(annotations=_WRITE)
async def pdf_vision_qa(path: str, pages: str = "", strict: bool = False, workspace: str = "") -> dict[str, Any]:
    """Visually inspect a local PDF or pdf_render PNG via Ollama local-quality. Layout QA only, not grammar.

    Optional. Use after a final or layout-critical PDF: clipped text, overlap, empty pages, broken tables.
    Does not replace technical qa_pdf. Direct Ollama /api/chat, no Qwen Serve. Pages like '1-3,5'.
    """
    flag = strict
    if isinstance(strict, str):
        flag = strict.strip().lower() in {"1", "true", "yes", "on"}
    return await asyncio.to_thread(_tool_result, vision_qa, path, pages, bool(flag), workspace)


@mcp.tool(annotations=_READ)
async def moe_consult(
    task: str,
    role: str = "second_opinion",
    context: str = "",
    max_tokens: int = 0,
) -> dict[str, Any]:
    """On-demand CPU MoE second opinion (Qwen3-Coder-30B-A3B). Starts llama-cli once, then fully exits.

    Use ONLY for architecture, complex plans, large reviews, multi-cause debugging, security/regression
    review, ticket breakdown, or a second opinion before big changes. Do NOT use for trivial renames,
    one-line fixes, CSS color tweaks, or simple file ops. local-fast remains the main agent.

    role: planner|reviewer|architect|supervisor|second_opinion.
    max_tokens: 0 = role default (256–640); clamped 64–768. Advisory only — verify before applying.
    """
    tokens = None if not max_tokens else int(max_tokens)
    return await asyncio.to_thread(_tool_result, consult_moe, task, role, context, tokens)


@mcp.tool(annotations=_BROWSER)
async def browser_open(url: str) -> dict[str, Any]:
    """Open one http(s) page in the isolated local Brave window. Registered name mcp__local-tools__browser_open.

    No file, javascript, data, chrome, about, or private hosts. Returns URL, title, and a snapshot with element ids.
    """
    return await asyncio.to_thread(_tool_result, open_browser, url)


@mcp.tool(annotations=_BROWSER)
async def browser_snapshot() -> dict[str, Any]:
    """Read the current browser page: URL, title, visible text, and element ids like [l1] or [b1].

    Click and type only use ids from the latest snapshot. Do not invent selectors.
    """
    return await asyncio.to_thread(_tool_result, snap_browser)


@mcp.tool(annotations=_BROWSER)
async def browser_click(ref: str) -> dict[str, Any]:
    """Click one element from the latest browser_snapshot, for example l1 or b1. No screen coordinates.

    Purchases, payments, account deletion, sending mail, and uploads are refused.
    """
    return await asyncio.to_thread(_tool_result, click_browser, ref)


@mcp.tool(annotations=_BROWSER)
async def browser_type(ref: str, text: str) -> dict[str, Any]:
    """Type into one input or textarea id from the latest snapshot. Does not press Enter. No password or file fields."""
    return await asyncio.to_thread(_tool_result, type_browser, ref, text)


@mcp.tool(annotations=_BROWSER)
async def browser_scroll(direction: str = "down", amount: int = 600) -> dict[str, Any]:
    """Scroll the current page down or up, then return a fresh snapshot. amount is pixels, 100 to 1600."""
    return await asyncio.to_thread(_tool_result, scroll_browser, direction, amount)


@mcp.tool(annotations=_BROWSER)
async def browser_back() -> dict[str, Any]:
    """Go back one page in the isolated browser and return a fresh snapshot."""
    return await asyncio.to_thread(_tool_result, go_back)


@mcp.tool(annotations=_BROWSER)
async def browser_screenshot() -> dict[str, Any]:
    """Save a PNG of the browser page only, not the whole desktop. The tool chooses the path."""
    return await asyncio.to_thread(_tool_result, shoot_browser)


@mcp.tool(annotations=_BROWSER)
async def browser_close() -> dict[str, Any]:
    """Close the isolated browser window and its profile session. Does not touch the personal browser."""
    return await asyncio.to_thread(_tool_result, close_browser)


@mcp.tool(annotations=_READ)
async def desktop_snapshot() -> dict[str, Any]:
    """Capture monitors, windows, focus, and a desktop PNG. Window ids like [w1] are valid only for this snapshot.

    Registered name mcp__local-tools__desktop_snapshot. Does not click or type. Web pages stay on browser_* tools.
    """
    return await asyncio.to_thread(_tool_result, snap_desktop)


@mcp.tool(annotations=_DESKTOP)
async def desktop_focus(window_id: str) -> dict[str, Any]:
    """Focus one window id from the latest desktop_snapshot, for example w2. Does not launch or kill apps."""
    return await asyncio.to_thread(_tool_result, focus_desktop, window_id)


@mcp.tool(annotations=_DESKTOP)
async def desktop_click(window_id: str = "", element_id: str = "", x: int = -1, y: int = -1) -> dict[str, Any]:
    """Click an element id from the snapshot, or a point relative to that window. No global screen coordinates.

    Purchases, deletion, sending, passwords, terminals, and browser pages are refused.
    """
    return await asyncio.to_thread(_tool_result, click_desktop, window_id, element_id, x, y)


@mcp.tool(annotations=_DESKTOP)
async def desktop_type(window_id: str = "", text: str = "", element_id: str = "") -> dict[str, Any]:
    """Insert text into a text field of a focused native window. No password fields, terminals, or browser pages."""
    return await asyncio.to_thread(_tool_result, type_desktop, window_id, text, element_id)


@mcp.tool(annotations=_DESKTOP)
async def desktop_scroll(window_id: str = "", direction: str = "down") -> dict[str, Any]:
    """Scroll the text of one native window up or down. direction is up or down."""
    return await asyncio.to_thread(_tool_result, scroll_desktop, window_id, direction)


@mcp.tool(annotations=_DESKTOP)
async def desktop_key(window_id: str = "", key: str = "") -> dict[str, Any]:
    """Send one allowlisted key: Escape, Enter, Tab, Shift+Tab, Ctrl+A, Ctrl+C, or Ctrl+V.

    No Super, Alt+F2, virtual consoles, or other shortcuts.
    """
    return await asyncio.to_thread(_tool_result, key_desktop, window_id, key)


@mcp.tool(annotations=_READ)
async def desktop_screenshot() -> dict[str, Any]:
    """Save a PNG of the whole local desktop. The tool chooses the path. Does not click or type."""
    return await asyncio.to_thread(_tool_result, shoot_desktop)


@mcp.tool(annotations=_DESKTOP)
async def desktop_close() -> dict[str, Any]:
    """End the desktop control session and drop window ids. Does not close or kill applications."""
    return await asyncio.to_thread(_tool_result, close_desktop)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> Response:
    return JSONResponse(
        {
            "status": "ok",
            "server": "local-ai-tools",
            "version": SERVER_VERSION,
            "tools": TOOL_NAMES,
            "localhost_only": True,
            "pdf": pdf_capabilities(),
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
