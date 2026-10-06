"""Project knowledge base v2: decisions, failures, fixes, fallbacks, replans, research.

Persistent under `.agent/knowledge/`. Separate from compact `.agent/` memory state.
No embeddings, no network, no home-wide indexing.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from errors import ToolError
from paths import resolve_workspace


KNOWLEDGE_TYPES = (
    "decision",
    "failure",
    "fix",
    "fallback",
    "replan",
    "research",
    "success",
)
STATUSES = (
    "active",
    "superseded",
    "failed",
    "validated",
    "deprecated",
)
CONFIDENCES = ("high", "medium", "low")
DEFAULT_MAX_RESULTS = 5
MAX_RESULTS_CAP = 12
MAX_PACKAGE_CHARS = 5500  # ~1500 tokens upper bound
PREFERRED_PACKAGE_CHARS = 2800  # ~700–800 tokens target
MAX_SUMMARY_CHARS = 400
MAX_FIELD_CHARS = 800
SECRET_RE = re.compile(
    r"(?i)(password|passwd|secret|api[_-]?key|token|authorization|private[_-]?key)\s*[:=]",
)

# Ranking weights
_STATUS_WEIGHT = {
    "validated": 40,
    "active": 30,
    "failed": 10,
    "deprecated": 0,
    "superseded": -20,
}


def knowledge_dir(workspace: Path) -> Path:
    return workspace / ".agent" / "knowledge"


def entries_path(root: Path) -> Path:
    return knowledge_dir(root) / "entries.jsonl"


def index_path(root: Path) -> Path:
    return knowledge_dir(root) / "index.json"


def bootstrap_knowledge(workspace: str | Path) -> dict[str, Any]:
    """Ensure knowledge store exists. Seeds curated entries only when empty."""
    root = resolve_workspace(workspace)
    target = knowledge_dir(root)
    target.mkdir(parents=True, exist_ok=True)
    path = entries_path(root)
    seeded = False
    if not path.exists() or path.stat().st_size == 0:
        path.write_text("", encoding="utf-8")
        for entry in curated_seed_entries():
            _append_entry(root, entry, rebuild=False)
        _rebuild_index(root)
        seeded = True
    elif not index_path(root).exists():
        _rebuild_index(root)
    return {
        "ok": True,
        "workspace": str(root),
        "knowledge_dir": str(target),
        "seeded": seeded,
        "count": len(_load_all(root)),
    }


def knowledge_search(
    workspace: str | Path,
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    types: str = "",
) -> dict[str, Any]:
    """Keyword retrieval with compact package. Never dumps the full KB."""
    boot = bootstrap_knowledge(workspace)
    root = Path(boot["workspace"])
    q = (query or "").strip()
    if not q:
        raise ToolError("query ist Pflicht.")
    if SECRET_RE.search(q):
        raise ToolError("Query darf keine Secrets enthalten.")
    limit = _clamp_results(max_results)
    type_filter = _parse_types(types)
    entries = _load_all(root)
    if not entries:
        return {
            "ok": True,
            "workspace": str(root),
            "query": q,
            "hits": [],
            "package": "Relevant knowledge:\n\nno relevant knowledge\n",
            "stats": {"candidates": 0, "returned": 0, "package_chars": 0},
            "instruction": _search_instruction(),
        }
    scored = []
    for entry in entries:
        if type_filter and entry.get("type") not in type_filter:
            continue
        score, reasons = _score_entry(entry, q)
        if score <= 0:
            continue
        scored.append((score, entry, reasons))
    scored.sort(key=lambda item: (-item[0], -_ts(item[1].get("updated_at") or item[1].get("created_at"))))
    top = scored[:limit]
    # Relation boost pass: pull related entries of top hits if room
    seen = {item[1]["id"] for item in top}
    related_extra: list[tuple[float, dict[str, Any], list[str]]] = []
    by_id = {e["id"]: e for e in entries}
    for _, entry, _ in top:
        for rel_id in _relation_ids(entry):
            if rel_id in seen or rel_id not in by_id:
                continue
            related = by_id[rel_id]
            if type_filter and related.get("type") not in type_filter:
                continue
            related_extra.append((5.0, related, ["relation"]))
            seen.add(rel_id)
            if len(top) + len(related_extra) >= limit:
                break
        if len(top) + len(related_extra) >= limit:
            break
    combined = top + related_extra
    combined = combined[:limit]
    hits = [_hit_view(entry, score, reasons) for score, entry, reasons in combined]
    package = _format_package(hits, q)
    slim_hits = [
        {
            "id": h.get("id"),
            "type": h.get("type"),
            "topic": h.get("topic"),
            "status": h.get("status"),
            "summary": _clip(str(h.get("summary") or ""), 180),
            "do_not_repeat": bool(h.get("do_not_repeat")),
            "score": h.get("score"),
        }
        for h in hits
    ]
    return {
        "ok": True,
        "workspace": str(root),
        "query": q,
        "hits": slim_hits,
        "package": package,
        "stats": {
            "candidates": len(scored),
            "returned": len(hits),
            "package_chars": len(package),
            "approx_tokens": max(1, (len(package) + len(json.dumps(slim_hits, ensure_ascii=False))) // 4),
        },
        "instruction": _search_instruction(),
    }


def knowledge_get(workspace: str | Path, entry_id: str) -> dict[str, Any]:
    boot = bootstrap_knowledge(workspace)
    root = Path(boot["workspace"])
    eid = (entry_id or "").strip()
    if not eid:
        raise ToolError("id ist Pflicht.")
    entry = _find_by_id(root, eid)
    if entry is None:
        return {"ok": False, "error": f"Unbekannte Knowledge-ID: {eid}", "id": eid}
    # Detail view stays compact: drop fingerprint internals
    detail = {k: v for k, v in entry.items() if k != "fingerprint"}
    payload = json.dumps(detail, ensure_ascii=False)
    if len(payload) > 3500:
        detail["summary"] = _clip(str(detail.get("summary") or ""), 300)
        detail["reason"] = _clip(str(detail.get("reason") or ""), 400)
        detail["cause"] = _clip(str(detail.get("cause") or ""), 400)
        detail["findings"] = _clip(str(detail.get("findings") or ""), 400)
        payload = json.dumps(detail, ensure_ascii=False)
    return {
        "ok": True,
        "workspace": str(root),
        "entry": detail,
        "chars": len(payload),
    }


def knowledge_record(
    workspace: str | Path,
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
    """Append or dedupe-update a knowledge entry. Never invent evidence paths."""
    boot = bootstrap_knowledge(workspace)
    root = Path(boot["workspace"])
    ktype = (type or "").strip().lower()
    if ktype not in KNOWLEDGE_TYPES:
        raise ToolError(f"Unbekannter type '{type}'. Erlaubt: {', '.join(KNOWLEDGE_TYPES)}")
    topic_clean = _clip((topic or "").strip(), 120)
    summary_clean = _clip((summary or "").strip(), MAX_SUMMARY_CHARS)
    if not topic_clean or not summary_clean:
        raise ToolError("topic und summary sind Pflicht.")
    for field_name, value in (
        ("summary", summary_clean),
        ("reason", reason),
        ("cause", cause),
        ("findings", findings),
        ("question", question),
    ):
        if value and SECRET_RE.search(value):
            raise ToolError(f"{field_name} darf keine Secrets enthalten.")
    st = (status or "active").strip().lower()
    if st not in STATUSES:
        raise ToolError(f"Unbekannter status '{status}'. Erlaubt: {', '.join(STATUSES)}")
    conf = (confidence or "").strip().lower()
    if conf and conf not in CONFIDENCES:
        raise ToolError(f"Unbekannte confidence '{confidence}'. Erlaubt: {', '.join(CONFIDENCES)}")

    evidence_list = _split_csv(evidence)
    for path in evidence_list:
        if path.startswith("/") and not any(
            path.startswith(prefix)
            for prefix in (
                "/home/mike/Projects/",
                "/srv/ai/",
                "/mnt/ai-archive/",
                "/tmp/",
            )
        ):
            raise ToolError(f"Evidence-Pfad außerhalb erlaubter Roots: {path}")

    now = _now().isoformat()
    fingerprint = _fingerprint(ktype, topic_clean, summary_clean)
    existing = None if force_new else _find_dedupe(root, fingerprint, ktype, topic_clean)
    if existing is not None:
        updated = dict(existing)
        updated["updated_at"] = now
        updated["status"] = st
        if reason.strip():
            updated["reason"] = _clip(reason.strip(), MAX_FIELD_CHARS)
        if cause.strip():
            updated["cause"] = _clip(cause.strip(), MAX_FIELD_CHARS)
        if result.strip():
            updated["result"] = _clip(result.strip(), MAX_FIELD_CHARS)
        if findings.strip():
            updated["findings"] = _clip(findings.strip(), MAX_FIELD_CHARS)
        if question.strip():
            updated["question"] = _clip(question.strip(), MAX_FIELD_CHARS)
        if conf:
            updated["confidence"] = conf
        if do_not_repeat:
            updated["do_not_repeat"] = True
        updated["evidence"] = _merge_unique(list(updated.get("evidence") or []), evidence_list)
        updated["keywords"] = _merge_unique(
            list(updated.get("keywords") or []),
            _split_csv(keywords) or _auto_keywords(topic_clean, summary_clean),
        )
        _merge_relations(updated, relates_to, fixes, fallback_for, supersedes)
        if source.strip():
            updated["source"] = _clip(source.strip(), 240)
        _rewrite_entry(root, updated)
        return {
            "ok": True,
            "workspace": str(root),
            "action": "updated",
            "id": updated["id"],
            "deduped": True,
            "entry": _hit_view(updated, 0, ["dedupe"]),
        }

    entry_id = _allocate_id(root, topic_clean, now)
    entry: dict[str, Any] = {
        "id": entry_id,
        "type": ktype,
        "topic": topic_clean,
        "summary": summary_clean,
        "status": st,
        "created_at": now,
        "updated_at": now,
        "reason": _clip(reason.strip(), MAX_FIELD_CHARS) if reason.strip() else "",
        "cause": _clip(cause.strip(), MAX_FIELD_CHARS) if cause.strip() else "",
        "result": _clip(result.strip(), MAX_FIELD_CHARS) if result.strip() else "",
        "do_not_repeat": bool(do_not_repeat) if ktype == "failure" else False,
        "supersedes": (supersedes or "").strip() or None,
        "relations": {
            "relates_to": _split_csv(relates_to),
            "fixes": _split_csv(fixes),
            "fallback_for": _split_csv(fallback_for),
        },
        "evidence": evidence_list,
        "source": _clip(source.strip(), 240) if source.strip() else "",
        "keywords": _split_csv(keywords) or _auto_keywords(topic_clean, summary_clean),
        "fingerprint": fingerprint,
    }
    if conf:
        entry["confidence"] = conf
    if question.strip():
        entry["question"] = _clip(question.strip(), MAX_FIELD_CHARS)
    if findings.strip():
        entry["findings"] = _clip(findings.strip(), MAX_FIELD_CHARS)

    if entry["supersedes"]:
        old = _find_by_id(root, entry["supersedes"])
        if old is None:
            raise ToolError(f"supersedes unbekannt: {entry['supersedes']}")
        superseded = dict(old)
        superseded["status"] = "superseded"
        superseded["updated_at"] = now
        superseded["superseded_by"] = entry_id
        _rewrite_entry(root, superseded, rebuild=False)

    _append_entry(root, entry, rebuild=True)
    return {
        "ok": True,
        "workspace": str(root),
        "action": "created",
        "id": entry_id,
        "deduped": False,
        "entry": _hit_view(entry, 0, ["new"]),
    }


def curated_seed_entries() -> list[dict[str, Any]]:
    """High-value facts from existing docs only. Stable IDs for tests."""
    base = "2026-09-22T10:00:00+02:00"
    entries: list[dict[str, Any]] = [
        {
            "id": "KB-20260922-COMPACT-001",
            "type": "failure",
            "topic": "qwen-compact",
            "summary": "85% autoCompactThreshold caused hidden post-tool generation pauses on QUALITY.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "cause": "Prompt tokens after tools exceeded 0.85×16384 so Qwen ran compact analysis.",
            "result": "failed",
            "do_not_repeat": True,
            "reason": "Threshold raised to 0.95; compactionModel=local-fast.",
            "evidence": ["docs/QWEN_COMPACT_CONTINUITY.md", "docs/AGENT_MEMORY.md"],
            "source": "docs/QWEN_COMPACT_CONTINUITY.md",
            "keywords": ["compact", "0.85", "hidden-gen", "threshold", "16384"],
            "relations": {"relates_to": [], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-compact-085",
        },
        {
            "id": "KB-20260922-COMPACT-002",
            "type": "decision",
            "topic": "qwen-compact",
            "summary": "Keep autoCompactThreshold=0.95 and compactionModel=local-fast.",
            "status": "active",
            "created_at": base,
            "updated_at": base,
            "reason": "Absorbs hidden compact work on FAST without truncating tool calls.",
            "evidence": ["docs/QWEN_COMPACT_CONTINUITY.md"],
            "source": "docs/QWEN_COMPACT_CONTINUITY.md",
            "keywords": ["compact", "0.95", "local-fast", "threshold"],
            "relations": {"relates_to": ["KB-20260922-COMPACT-001"], "fixes": ["KB-20260922-COMPACT-001"], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-compact-095",
        },
        {
            "id": "KB-20260922-COMPACT-003",
            "type": "failure",
            "topic": "compact-continuity",
            "summary": "Prompt-only compact continuity patch was insufficient.",
            "status": "failed",
            "created_at": base,
            "updated_at": base,
            "cause": "Successful tool calls omitted by FAST summary; 29 eager schemas overflowed to 17216.",
            "result": "failed",
            "do_not_repeat": True,
            "reason": "Do not reinstall prompt-only continuity as primary fix.",
            "evidence": ["docs/QWEN_COMPACT_CONTINUITY.md", "benchmarks/compact-continuity-20260921/summary.json"],
            "source": "docs/QWEN_COMPACT_CONTINUITY.md",
            "keywords": ["prompt-only", "continuity", "pdf_create", "duplicate", "17216"],
            "relations": {"relates_to": [], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-prompt-only-fail",
        },
        {
            "id": "KB-20260922-LAZY-001",
            "type": "failure",
            "topic": "qwen-context",
            "summary": "29 eager MCP tool schemas produced 17216 prompt tokens against QUALITY 16384.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "cause": "alwaysLoadTools true loaded every schema into the first prompt.",
            "result": "failed",
            "do_not_repeat": True,
            "evidence": ["docs/QWEN_LAZY_TOOL_LOADING.md"],
            "source": "docs/QWEN_LAZY_TOOL_LOADING.md",
            "keywords": ["17216", "eager", "schemas", "overflow", "mcp", "29"],
            "relations": {"relates_to": ["KB-20260922-COMPACT-003"], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-17216",
        },
        {
            "id": "KB-20260922-LAZY-002",
            "type": "fix",
            "topic": "qwen-context",
            "summary": "Lazy Tool Loading: alwaysLoadTools=false, tools.visible=[], all tools via ToolSearch.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "result": "pass",
            "reason": "Removed hard overflow 17216>16384 while keeping 29 tools discoverable.",
            "evidence": ["docs/QWEN_LAZY_TOOL_LOADING.md"],
            "source": "docs/QWEN_LAZY_TOOL_LOADING.md",
            "keywords": ["lazy", "alwaysLoadTools", "toolsearch", "schemas"],
            "relations": {
                "relates_to": ["KB-20260922-LAZY-001"],
                "fixes": ["KB-20260922-LAZY-001", "KB-20260922-COMPACT-003"],
                "fallback_for": [],
            },
            "supersedes": None,
            "fingerprint": "seed-lazy-fix",
        },
        {
            "id": "KB-20260922-LEDGER-001",
            "type": "failure",
            "topic": "compact-continuity",
            "summary": "After compact, full memory_load result reattached; continuation up to 16231 tokens.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "cause": "pendingUserMessage reattached large successful tool result after compression.",
            "result": "failed",
            "do_not_repeat": True,
            "evidence": ["docs/QWEN_COMPACT_STATE_LEDGER.md", "benchmarks/compact-state-20260922/baseline.json"],
            "source": "docs/QWEN_COMPACT_STATE_LEDGER.md",
            "keywords": ["16231", "memory_load", "reattach", "second compact", "4246"],
            "relations": {"relates_to": ["KB-20260922-COMPACT-003"], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-16231",
        },
        {
            "id": "KB-20260922-LEDGER-002",
            "type": "fix",
            "topic": "compact-continuity",
            "summary": "Deterministic runtime Compact State Ledger plus shrink of large successful results.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "result": "pass",
            "reason": "Machine <tool_continuity> from real tool events; not from FAST summary.",
            "evidence": [
                "docs/QWEN_COMPACT_STATE_LEDGER.md",
                "benchmarks/compact-state-20260922/ledger4.json",
            ],
            "source": "docs/QWEN_COMPACT_STATE_LEDGER.md",
            "keywords": [
                "ledger",
                "tool_continuity",
                "pdf_create",
                "duplicate",
                "shrink",
                "9318",
            ],
            "relations": {
                "relates_to": ["KB-20260922-LEDGER-001", "KB-20260922-COMPACT-003"],
                "fixes": ["KB-20260922-LEDGER-001", "KB-20260922-COMPACT-003"],
                "fallback_for": [],
            },
            "supersedes": None,
            "fingerprint": "seed-ledger-fix",
        },
        {
            "id": "KB-20260922-LEDGER-003",
            "type": "fallback",
            "topic": "compact-continuity",
            "summary": "Keep stock compact prompt; do not reinstall continuity prompt patch.",
            "status": "active",
            "created_at": base,
            "updated_at": base,
            "reason": "Runtime ledger solved duplicates; prompt-only previously failed.",
            "evidence": ["docs/QWEN_COMPACT_STATE_LEDGER.md"],
            "source": "docs/QWEN_COMPACT_STATE_LEDGER.md",
            "keywords": ["stock prompt", "prompt-patch", "fallback"],
            "relations": {
                "relates_to": ["KB-20260922-LEDGER-002", "KB-20260922-COMPACT-003"],
                "fixes": [],
                "fallback_for": ["KB-20260922-COMPACT-003", "KB-20260922-LEDGER-002"],
            },
            "supersedes": None,
            "fingerprint": "seed-stock-prompt-fallback",
        },
        {
            "id": "KB-20260922-LEDGER-004",
            "type": "decision",
            "topic": "compact-continuity",
            "summary": "Compact State Ledger stays productive with Lazy Tool Loading.",
            "status": "active",
            "created_at": base,
            "updated_at": base,
            "reason": "QUALITY E2E PASS: continuation 9318, six tools once, no immediate second compact.",
            "evidence": ["docs/QWEN_COMPACT_STATE_LEDGER.md", "benchmarks/compact-state-20260922/ledger4.json"],
            "source": "docs/QWEN_COMPACT_STATE_LEDGER.md",
            "keywords": ["ledger", "productive", "lazy", "pass"],
            "relations": {
                "relates_to": ["KB-20260922-LEDGER-002", "KB-20260922-LAZY-002"],
                "fixes": [],
                "fallback_for": [],
            },
            "supersedes": None,
            "fingerprint": "seed-ledger-decision",
        },
        {
            "id": "KB-20260922-TOOLSEARCH-001",
            "type": "fix",
            "topic": "qwen-tooling",
            "summary": "ToolSearch MCP short-name alias patch maps select:name to mcp__local-tools__name.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "result": "pass",
            "evidence": ["docs/QWEN_TOOLSEARCH_MCP_ALIAS.md"],
            "source": "docs/QWEN_TOOLSEARCH_MCP_ALIAS.md",
            "keywords": ["toolsearch", "short-name", "registry", "mcp alias"],
            "relations": {"relates_to": [], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-toolsearch",
        },
        {
            "id": "KB-20260922-GIT-001",
            "type": "fix",
            "topic": "qwen-tooling",
            "summary": "Git snapshot omit patch keeps large git status out of the model prompt.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "result": "pass",
            "evidence": ["docs/QWEN_TOOLSEARCH_MCP_ALIAS.md"],
            "source": "docs/CHATGPT_HANDOFF.md",
            "keywords": ["git", "snapshot", "omit", "patch"],
            "relations": {"relates_to": ["KB-20260922-TOOLSEARCH-001"], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-git-omit",
        },
        {
            "id": "KB-20260922-BOOT-001",
            "type": "failure",
            "topic": "systemd-boot",
            "summary": "systemd ordering cycle deleted local-tools-mcp start at boot.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "cause": "ki-workplace After=default.target plus MCP After/Wants workplace created a cycle.",
            "result": "failed",
            "do_not_repeat": True,
            "evidence": ["docs/ACCEPTANCE_A01_A14.md"],
            "source": "docs/ACCEPTANCE_A01_A14.md",
            "keywords": ["systemd", "cycle", "boot", "mcp", "ki-workplace"],
            "relations": {"relates_to": [], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-boot-cycle",
        },
        {
            "id": "KB-20260922-BOOT-002",
            "type": "fix",
            "topic": "systemd-boot",
            "summary": "MCP independent boot: both units After=network.target; MCP no longer Wants workplace.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "result": "pass",
            "evidence": ["docs/ACCEPTANCE_A01_A14.md", "scripts/apply-mcp-independent-boot.sh"],
            "source": "docs/ACCEPTANCE_A01_A14.md",
            "keywords": ["systemd", "independent", "boot", "network.target"],
            "relations": {
                "relates_to": ["KB-20260922-BOOT-001"],
                "fixes": ["KB-20260922-BOOT-001"],
                "fallback_for": [],
            },
            "supersedes": None,
            "fingerprint": "seed-boot-fix",
        },
        {
            "id": "KB-20260922-IMAGE-001",
            "type": "decision",
            "topic": "image-editing",
            "summary": "Use original uploaded image as edit input; 37fa72860c19 is not a quality benchmark.",
            "status": "active",
            "created_at": base,
            "updated_at": base,
            "reason": "Avoid cascading edits on AI outputs unless user asks for a second edit.",
            "evidence": ["docs/OPEN_WEBUI_IMAGE_TOOLS.md", "docs/CHATGPT_HANDOFF.md"],
            "source": "docs/CHATGPT_HANDOFF.md",
            "keywords": ["original", "37fa72860c19", "edit_image", "quality"],
            "relations": {"relates_to": [], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-original-image",
        },
        {
            "id": "KB-20260922-IMAGE-002",
            "type": "decision",
            "topic": "image-resolution",
            "summary": "Productive image sizes stay 512/768/1024; 1024 is VRAM ceiling for Qwen-Image edit on this host.",
            "status": "active",
            "created_at": base,
            "updated_at": base,
            "reason": "16 GB VRAM; 1536/2K/4K deferred by master plan.",
            "evidence": ["docs/QWEN_IMAGE_2_1_EDIT.md", "docs/MASTER_PLAN.md"],
            "source": "docs/MASTER_PLAN.md",
            "keywords": ["1024", "vram", "1536", "512", "768"],
            "relations": {"relates_to": [], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "fingerprint": "seed-1024-cap",
        },
        {
            "id": "KB-20260921-ROADMAP-000",
            "type": "decision",
            "topic": "roadmap",
            "summary": "After Desktop-Agent, next phase was 1536 image benchmark.",
            "status": "superseded",
            "created_at": "2026-09-21T20:30:00+02:00",
            "updated_at": "2026-09-22T09:00:00+02:00",
            "reason": "Historical plan from Desktop-Agent handoff.",
            "evidence": ["docs/CHANGELOG.md"],
            "source": "docs/CHANGELOG.md",
            "keywords": ["1536", "desktop", "next", "roadmap"],
            "relations": {"relates_to": [], "fixes": [], "fallback_for": []},
            "supersedes": None,
            "superseded_by": "KB-20260921-ROADMAP-001",
            "fingerprint": "seed-roadmap-old",
        },
        {
            "id": "KB-20260921-ROADMAP-001",
            "type": "replan",
            "topic": "roadmap",
            "summary": "Old plan Desktop→1536 superseded by Continuity→Knowledge→Supervisor→Context bench→autonomous workflow→High-Res.",
            "status": "active",
            "created_at": "2026-09-22T09:00:00+02:00",
            "updated_at": "2026-09-22T09:00:00+02:00",
            "reason": "Continuity was blocking; 1536 must wait until Knowledge and Supervisor land.",
            "result": "old_plan=Desktop→1536; new_plan=Continuity→KB→Supervisor→24K/32K bench→autonomous→1536/2K/4K",
            "evidence": ["docs/MASTER_PLAN.md"],
            "source": "docs/MASTER_PLAN.md",
            "keywords": ["roadmap", "1536", "master-plan", "supervisor", "knowledge", "desktop"],
            "relations": {"relates_to": ["KB-20260921-ROADMAP-000"], "fixes": [], "fallback_for": []},
            "supersedes": "KB-20260921-ROADMAP-000",
            "fingerprint": "seed-roadmap-replan",
        },
        {
            "id": "KB-20260922-SUCCESS-001",
            "type": "success",
            "topic": "qwen-context",
            "summary": "Lazy schemas plus Compact State Ledger is the validated continuity pattern.",
            "status": "validated",
            "created_at": base,
            "updated_at": base,
            "result": "pass",
            "evidence": [
                "docs/QWEN_LAZY_TOOL_LOADING.md",
                "docs/QWEN_COMPACT_STATE_LEDGER.md",
            ],
            "source": "docs/QWEN_COMPACT_STATE_LEDGER.md",
            "keywords": ["success", "lazy", "ledger", "pattern"],
            "relations": {
                "relates_to": ["KB-20260922-LAZY-002", "KB-20260922-LEDGER-002"],
                "fixes": [],
                "fallback_for": [],
            },
            "supersedes": None,
            "fingerprint": "seed-success-pattern",
        },
    ]
    return entries


def _search_instruction() -> str:
    return (
        "Use this package before inventing a new repair. Prefer validated fixes and active "
        "decisions. Do not repeat entries marked do_not_repeat or failed prompt-only approaches. "
        "Call knowledge_get only for one id when more detail is needed. Do not load the whole KB."
    )


def _clamp_results(value: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = DEFAULT_MAX_RESULTS
    return max(1, min(MAX_RESULTS_CAP, n))


def _parse_types(raw: str) -> set[str]:
    if not raw or not str(raw).strip():
        return set()
    out = set()
    for part in str(raw).split(","):
        name = part.strip().lower()
        if not name:
            continue
        if name not in KNOWLEDGE_TYPES:
            raise ToolError(f"Unbekannter type-Filter: {name}")
        out.add(name)
    return out


def _score_entry(entry: dict[str, Any], query: str) -> tuple[float, list[str]]:
    q = query.lower()
    tokens = [t for t in re.split(r"[^\w\-]+", q) if len(t) >= 3]
    # Drop ultra-common German/English filler tokens
    stop = {
        "was",
        "wie",
        "warum",
        "wenn",
        "oder",
        "und",
        "der",
        "die",
        "das",
        "den",
        "dem",
        "ein",
        "eine",
        "ist",
        "sind",
        "mit",
        "nach",
        "noch",
        "kein",
        "keine",
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "have",
        "soll",
        "sollte",
        "kommt",
        "beim",
        "dazu",
        "über",
        "ohne",
    }
    tokens = [t for t in tokens if t not in stop]
    reasons: list[str] = []
    score = 0.0
    topic = str(entry.get("topic") or "").lower()
    summary = str(entry.get("summary") or "").lower()
    keywords = [str(k).lower() for k in (entry.get("keywords") or [])]
    blob = " ".join(
        [
            topic,
            summary,
            str(entry.get("reason") or "").lower(),
            str(entry.get("cause") or "").lower(),
            str(entry.get("result") or "").lower(),
            " ".join(keywords),
            str(entry.get("id") or "").lower(),
        ]
    )
    if topic and (topic in q or q in topic):
        score += 50
        reasons.append("exact_topic")
    for kw in keywords:
        if kw and len(kw) >= 3 and kw in q:
            score += 18
            reasons.append(f"keyword:{kw}")
    for token in tokens:
        if token in topic:
            score += 14
            reasons.append(f"topic:{token}")
        elif token in keywords:
            score += 12
            reasons.append(f"kw:{token}")
        elif token in summary:
            score += 10
            reasons.append(f"summary:{token}")
        elif token in blob:
            score += 4
            reasons.append(f"body:{token}")
    # Phrase bonuses for known critical queries
    if "17216" in q and "17216" in blob:
        score += 25
        reasons.append("overflow")
    if "pdf_create" in q and "pdf_create" in blob:
        score += 15
    if "ledger" in q and "ledger" in blob:
        score += 20
    if "lazy" in q and ("lazy" in blob or "schema" in blob):
        score += 15
    if "1536" in q and "1536" in blob:
        score += 20
    if "systemd" in q and "systemd" in blob:
        score += 20
    if "prompt" in q and "prompt-only" in blob:
        score += 20
    if "desktop" in q and "desktop" in blob:
        score += 18
        reasons.append("desktop")
    if "roadmap" in q and "roadmap" in blob:
        score += 18
    if "agent" in q and "desktop" in q and "roadmap" in blob:
        score += 12

    # No content match → not a hit (prevents status-only noise)
    if score <= 0:
        return 0.0, []

    status = str(entry.get("status") or "active")
    score += _STATUS_WEIGHT.get(status, 0)
    if status == "superseded":
        reasons.append("SUPERSEDED")
    if entry.get("do_not_repeat"):
        score += 8
        reasons.append("do_not_repeat")
    score += min(10.0, _ts(entry.get("updated_at") or entry.get("created_at")) / 1e12)
    return score, reasons


def _hit_view(entry: dict[str, Any], score: float, reasons: list[str]) -> dict[str, Any]:
    rel = entry.get("relations") or {}
    return {
        "id": entry.get("id"),
        "type": entry.get("type"),
        "topic": entry.get("topic"),
        "summary": entry.get("summary"),
        "status": entry.get("status"),
        "reason": entry.get("reason") or entry.get("cause") or "",
        "result": entry.get("result") or "",
        "do_not_repeat": bool(entry.get("do_not_repeat")),
        "supersedes": entry.get("supersedes"),
        "superseded_by": entry.get("superseded_by"),
        "relations": {
            "fixes": list(rel.get("fixes") or []),
            "fallback_for": list(rel.get("fallback_for") or []),
            "relates_to": list(rel.get("relates_to") or []),
        },
        "evidence": list(entry.get("evidence") or [])[:6],
        "source": entry.get("source") or "",
        "confidence": entry.get("confidence") or "",
        "score": round(float(score), 2),
        "match": reasons[:6],
    }


def _format_package(hits: list[dict[str, Any]], query: str) -> str:
    if not hits:
        return "Relevant knowledge:\n\nno relevant knowledge\n"
    sections: list[str] = [f"Relevant knowledge for: {query.strip()[:160]}\n"]
    order = (
        ("decision", "ACTIVE/VALIDATED DECISION"),
        ("failure", "KNOWN FAILURE"),
        ("fix", "VALIDATED FIX"),
        ("fallback", "FALLBACK"),
        ("replan", "REPLAN"),
        ("success", "SUCCESS PATTERN"),
        ("research", "RESEARCH"),
    )
    by_type: dict[str, list[dict[str, Any]]] = {}
    for hit in hits:
        by_type.setdefault(str(hit.get("type")), []).append(hit)
    for type_name, heading in order:
        for hit in by_type.get(type_name, []):
            status = str(hit.get("status") or "").upper()
            line = [
                f"{heading} [{status}]",
                f"id: {hit.get('id')}",
                f"topic: {hit.get('topic')}",
                f"summary: {hit.get('summary')}",
            ]
            if hit.get("reason"):
                line.append(f"reason: {hit['reason']}")
            if hit.get("do_not_repeat"):
                line.append("do_not_repeat: true")
            if hit.get("status") == "superseded":
                line.append(f"SUPERSEDED → {hit.get('superseded_by') or 'see newer entry'}")
            if hit.get("supersedes"):
                line.append(f"supersedes: {hit['supersedes']} (prior entry SUPERSEDED)")
            rel = hit.get("relations") or {}
            if rel.get("fixes"):
                line.append(f"fixes: {', '.join(rel['fixes'])}")
            if rel.get("fallback_for"):
                line.append(f"fallback_for: {', '.join(rel['fallback_for'])}")
            if hit.get("evidence"):
                line.append(f"evidence: {', '.join(hit['evidence'][:3])}")
            sections.append("\n".join(line) + "\n")
    text = "\n".join(sections).strip() + "\n"
    if len(text) > MAX_PACKAGE_CHARS:
        text = text[: MAX_PACKAGE_CHARS - 40].rstrip() + "\n\n[truncated knowledge package]\n"
    elif len(text) > PREFERRED_PACKAGE_CHARS and len(hits) > 3:
        # Prefer shorter package when many hits: keep first 3 blocks roughly
        parts = text.split("\n\n")
        short = "\n\n".join(parts[:5])
        if len(short) < len(text):
            text = short.rstrip() + "\n\n[more hits omitted; use knowledge_get]\n"
    return text


def _relation_ids(entry: dict[str, Any]) -> list[str]:
    rel = entry.get("relations") or {}
    out: list[str] = []
    for key in ("fixes", "fallback_for", "relates_to"):
        out.extend(list(rel.get(key) or []))
    if entry.get("supersedes"):
        out.append(str(entry["supersedes"]))
    if entry.get("superseded_by"):
        out.append(str(entry["superseded_by"]))
    return out


def _load_all(root: Path) -> list[dict[str, Any]]:
    path = entries_path(root)
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("id"):
            entries.append(obj)
    return entries


def _find_by_id(root: Path, entry_id: str) -> dict[str, Any] | None:
    for entry in _load_all(root):
        if entry.get("id") == entry_id:
            return entry
    return None


def _find_dedupe(
    root: Path,
    fingerprint: str,
    ktype: str,
    topic: str,
) -> dict[str, Any] | None:
    for entry in _load_all(root):
        if entry.get("status") in {"superseded", "deprecated"}:
            continue
        if entry.get("fingerprint") == fingerprint:
            return entry
        if entry.get("type") == ktype and str(entry.get("topic") or "").lower() == topic.lower():
            if entry.get("fingerprint") == fingerprint:
                return entry
    return None


def _append_entry(root: Path, entry: dict[str, Any], *, rebuild: bool = True) -> None:
    path = entries_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    if rebuild:
        _rebuild_index(root)


def _rewrite_entry(root: Path, entry: dict[str, Any], *, rebuild: bool = True) -> None:
    entries = _load_all(root)
    found = False
    for index, existing in enumerate(entries):
        if existing.get("id") == entry.get("id"):
            entries[index] = entry
            found = True
            break
    if not found:
        entries.append(entry)
    path = entries_path(root)
    with path.open("w", encoding="utf-8") as handle:
        for item in entries:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
    if rebuild:
        _rebuild_index(root)


def _rebuild_index(root: Path) -> None:
    entries = _load_all(root)
    index = {
        "version": 1,
        "updated_at": _now().isoformat(),
        "count": len(entries),
        "by_id": {
            e["id"]: {
                "type": e.get("type"),
                "topic": e.get("topic"),
                "status": e.get("status"),
                "updated_at": e.get("updated_at"),
            }
            for e in entries
            if e.get("id")
        },
        "by_topic": {},
    }
    topics: dict[str, list[str]] = {}
    for entry in entries:
        topic = str(entry.get("topic") or "")
        topics.setdefault(topic, []).append(entry["id"])
    index["by_topic"] = topics
    index_path(root).write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _allocate_id(root: Path, topic: str, now_iso: str) -> str:
    day = now_iso[:10].replace("-", "")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", topic.upper()).strip("-")[:18] or "TOPIC"
    existing = {e.get("id") for e in _load_all(root)}
    for n in range(1, 1000):
        candidate = f"KB-{day}-{slug}-{n:03d}"
        if candidate not in existing:
            return candidate
    raise ToolError("Keine freie Knowledge-ID verfügbar.")


def _fingerprint(ktype: str, topic: str, summary: str) -> str:
    raw = f"{ktype}|{topic.lower().strip()}|{summary.lower().strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _merge_relations(
    entry: dict[str, Any],
    relates_to: str,
    fixes: str,
    fallback_for: str,
    supersedes: str,
) -> None:
    rel = dict(entry.get("relations") or {})
    rel["relates_to"] = _merge_unique(list(rel.get("relates_to") or []), _split_csv(relates_to))
    rel["fixes"] = _merge_unique(list(rel.get("fixes") or []), _split_csv(fixes))
    rel["fallback_for"] = _merge_unique(list(rel.get("fallback_for") or []), _split_csv(fallback_for))
    entry["relations"] = rel
    if supersedes.strip():
        entry["supersedes"] = supersedes.strip()


def _split_csv(raw: str) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    out: list[str] = []
    for part in str(raw).split(","):
        item = part.strip()
        if item and item not in out:
            out.append(item)
    return out


def _merge_unique(left: list[str], right: list[str]) -> list[str]:
    out = list(left)
    for item in right:
        if item not in out:
            out.append(item)
    return out


def _auto_keywords(topic: str, summary: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_\-]{2,}", f"{topic} {summary}")
    out: list[str] = []
    for word in words:
        low = word.lower()
        if low in out:
            continue
        out.append(low)
        if len(out) >= 12:
            break
    return out


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _ts(value: Any) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()
