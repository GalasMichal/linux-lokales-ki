"""Project-scoped persistent agent memory under `.agent/`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from errors import ToolError
from paths import resolve_dir, resolve_workspace


MEMORY_FILES = (
    "STATE.md",
    "REQUIREMENTS.md",
    "DECISIONS.md",
    "TASKS.md",
    "TOOLS.md",
)
MAX_CHARS_PER_FILE = 3500
MAX_TOTAL_CHARS = 14000
MAX_HISTORY_LIST = 4
KEEP_RECENT_DECISIONS = 4
MEMORY_INSTRUCTION = (
    "Treat these files as source of truth. Do not rely on chat history. "
    "Do not summarize them in chat. After a successful tool, immediately call "
    "the next required tool. At most one short status sentence between tools. "
    "Full report only after the last step. Call memory_update only after the "
    "user's task is finished, never between tools."
)

_TEMPLATES: dict[str, str] = {
    "STATE.md": (
        "# State\n\n"
        "- Project: (name)\n"
        "- Phase: (current phase)\n"
        "- Last update: (ISO-8601)\n"
        "- Blockers: none\n"
        "- Notes: compact working state only. Do not paste chat logs.\n"
    ),
    "REQUIREMENTS.md": (
        "# Requirements\n\n"
        "Stable requirements for this workspace. Append; do not silently drop old items.\n"
    ),
    "DECISIONS.md": (
        "# Decisions\n\n"
        "Append-only. To change a decision, add a new dated entry that supersedes the old one.\n"
        "Never delete or rewrite previous entries.\n"
    ),
    "TASKS.md": (
        "# Tasks\n\n"
        "- [ ] Load `.agent/` memory before starting work\n"
        "- [ ] Update STATE.md and TASKS.md when a task finishes\n"
        "- [ ] Append DECISIONS.md when a choice is made\n"
    ),
    "TOOLS.md": (
        "# Tools\n\n"
        "Local MCP server `local-tools` (`http://127.0.0.1:8765/mcp`):\n"
        "- `generate_image` — FLUX.2-klein text-to-image via KI-Arbeitsplatz\n"
        "- `edit_image` — Qwen-Image-2.1 edit via KI-Arbeitsplatz\n"
        "- `generate_video` — Wan 2.2 TI2V-5B image-to-video via KI-Arbeitsplatz\n"
        "- `memory_load` / `memory_update` — persistent `.agent/` memory\n"
        "- `knowledge_search` / `knowledge_get` / `knowledge_record` — long-term knowledge base\n"
        "- `pdf_read` `pdf_inspect` `pdf_create` `pdf_edit` `pdf_merge` `pdf_split` `pdf_ocr` `pdf_render` `pdf_vision_qa`\n"
    ),
}


def agent_dir(workspace: Path) -> Path:
    return workspace / ".agent"


def bootstrap_memory(workspace: str | Path) -> dict[str, Any]:
    root = resolve_workspace(workspace)
    target = agent_dir(root)
    target.mkdir(parents=True, exist_ok=True)
    (target / "history").mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    existing: list[str] = []
    for name in MEMORY_FILES:
        path = target / name
        if path.exists():
            existing.append(name)
            continue
        path.write_text(_TEMPLATES[name], encoding="utf-8")
        created.append(name)
    return {
        "ok": True,
        "workspace": str(root),
        "agent_dir": str(target),
        "created": created,
        "existing": existing,
    }


def memory_load(workspace: str | Path, files: list[str] | None = None) -> dict[str, Any]:
    """Load compact `.agent/` files. Does not dump history into the prompt."""
    boot = bootstrap_memory(workspace)
    root = Path(boot["workspace"])
    target = Path(boot["agent_dir"])
    requested = _normalize_files(files)
    payload: dict[str, Any] = {}
    total = 0
    for name in requested:
        path = target / name
        raw = path.read_text(encoding="utf-8") if path.is_file() else ""
        truncated = False
        compacted = False
        content = raw
        if name == "DECISIONS.md":
            content, compacted = _compact_decisions(raw)
        elif name == "TASKS.md":
            content, compacted = _compact_tasks(raw)
        budget = min(MAX_CHARS_PER_FILE, max(0, MAX_TOTAL_CHARS - total))
        if len(content) > budget:
            content = content[:budget].rstrip() + "\n\n[truncated; read the file directly if needed]\n"
            truncated = True
        total += len(content)
        payload[name] = {
            "content": content,
            "chars": len(raw),
            "truncated": truncated,
            "compacted": compacted,
            "mtime": _mtime(path),
        }
    return {
        "ok": True,
        "workspace": str(root),
        "agent_dir": str(target),
        "bootstrapped": boot["created"],
        "files": payload,
        "recent_history": _list_history(target / "history"),
        "budget": {
            "max_chars_per_file": MAX_CHARS_PER_FILE,
            "max_total_chars": MAX_TOTAL_CHARS,
            "loaded_chars": total,
        },
        "instruction": MEMORY_INSTRUCTION,
    }


def memory_update(
    workspace: str | Path,
    summary: str,
    state: str | None = None,
    tasks: str | None = None,
    decisions: str | None = None,
    decision_title: str | None = None,
    requirements: str | None = None,
    tools: str | None = None,
) -> dict[str, Any]:
    """Update compact state files. DECISIONS.md is append-only."""
    if not isinstance(summary, str) or not summary.strip():
        raise ToolError("summary ist Pflicht und darf nicht leer sein.")
    boot = bootstrap_memory(workspace)
    root = Path(boot["workspace"])
    target = Path(boot["agent_dir"])
    history_dir = resolve_dir(target / "history", create=True)
    stamp = _now().strftime("%Y%m%d-%H%M%S")
    changed: list[str] = []
    snapshots: list[str] = []

    replacements = {
        "STATE.md": state,
        "TASKS.md": tasks,
        "REQUIREMENTS.md": requirements,
        "TOOLS.md": tools,
    }
    for name, content in replacements.items():
        if not _has_text(content):
            continue
        path = target / name
        snapshots.append(_snapshot(history_dir, stamp, path))
        path.write_text(_as_markdown(name, content.strip()), encoding="utf-8")
        changed.append(name)

    if _has_text(decisions):
        path = target / "DECISIONS.md"
        snapshots.append(_snapshot(history_dir, stamp, path))
        _append_decision(path, decision_title, decisions.strip())
        changed.append("DECISIONS.md")

    history_note = history_dir / f"{stamp}-summary.md"
    history_note.write_text(
        f"# Memory update { _now().isoformat() }\n\n"
        f"Summary: {summary.strip()}\n\n"
        f"Changed: {', '.join(changed) if changed else '(none)'}\n",
        encoding="utf-8",
    )
    if not changed:
        raise ToolError("Keine Memory-Felder gesetzt. Übergebe state, tasks, decisions, requirements oder tools.")
    return {
        "ok": True,
        "workspace": str(root),
        "changed": changed,
        "history": [item for item in snapshots if item] + [str(history_note)],
        "summary": summary.strip(),
    }


def _compact_tasks(raw: str) -> tuple[str, bool]:
    """Keep open tasks plus a short completed count. Full list stays on disk."""
    lines = raw.splitlines()
    open_items = [line for line in lines if line.strip().startswith("- [ ]")]
    done_items = [line for line in lines if line.strip().startswith("- [x]")]
    other = [line for line in lines if not line.strip().startswith("- [")]
    if len(done_items) <= 4:
        return raw, False
    out = "\n".join(other).rstrip()
    out += f"\n\nCompleted: {len(done_items)} items (full list in `.agent/TASKS.md`).\n"
    recent_done = done_items[-3:]
    if recent_done:
        out += "\n".join(recent_done) + "\n"
    if open_items:
        out += "\n".join(open_items) + "\n"
    if not out.endswith("\n"):
        out += "\n"
    return out, True


def _compact_decisions(raw: str) -> tuple[str, bool]:
    """Keep recent DECISIONS entries in full; older ones as headings only."""
    if not raw.strip():
        return raw, False
    chunks: list[str] = []
    buf: list[str] = []
    for line in raw.splitlines(keepends=True):
        if line.startswith("## ") and buf:
            chunks.append("".join(buf))
            buf = [line]
        else:
            buf.append(line)
    if buf:
        chunks.append("".join(buf))
    preamble = ""
    entries: list[str] = []
    for chunk in chunks:
        if chunk.lstrip().startswith("## "):
            entries.append(chunk if chunk.endswith("\n") else chunk + "\n")
        else:
            preamble += chunk
    if len(entries) <= KEEP_RECENT_DECISIONS:
        return raw, False
    older = entries[:-KEEP_RECENT_DECISIONS]
    recent = entries[-KEEP_RECENT_DECISIONS:]
    headings = []
    for entry in older:
        first = entry.splitlines()[0].strip()
        headings.append(f"- {first.lstrip('#').strip()}")
    out = preamble.rstrip() + "\n\n## Older decisions (headings only; full text is in `.agent/DECISIONS.md`)\n\n"
    out += "\n".join(headings) + "\n\n" + "".join(recent)
    if not out.endswith("\n"):
        out += "\n"
    return out, True


def _normalize_files(files: list[str] | None) -> list[str]:
    if not files:
        return list(MEMORY_FILES)
    wanted: list[str] = []
    for item in files:
        name = Path(str(item).strip()).name
        if name not in MEMORY_FILES:
            raise ToolError(f"Unbekannte Memory-Datei: {item}. Erlaubt: {', '.join(MEMORY_FILES)}")
        if name not in wanted:
            wanted.append(name)
    return wanted


def _append_decision(path: Path, title: str | None, body: str) -> None:
    heading = (title or "decision").strip() or "decision"
    if path.exists():
        current = path.read_text(encoding="utf-8")
    else:
        current = _TEMPLATES["DECISIONS.md"]
    entry = f"## {_now().isoformat()} — {heading}\n\n{body.strip()}\n"
    path.write_text(current.rstrip() + "\n\n" + entry, encoding="utf-8")


def _as_markdown(name: str, content: str) -> str:
    title = name.removesuffix(".md").title()
    if content.lstrip().startswith("#"):
        return content if content.endswith("\n") else content + "\n"
    return f"# {title}\n\n{content}\n"


def _snapshot(history_dir: Path, stamp: str, path: Path) -> str:
    if not path.is_file():
        return ""
    dest = history_dir / f"{stamp}-{path.name}"
    dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return str(dest)


def _list_history(history_dir: Path) -> list[dict[str, Any]]:
    if not history_dir.is_dir():
        return []
    entries = sorted(history_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)
    result = []
    for path in entries:
        if not path.is_file() or path.name.startswith("."):
            continue
        result.append({"name": path.name, "mtime": _mtime(path)})
        if len(result) >= MAX_HISTORY_LIST:
            break
    return result


def _mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _has_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())
