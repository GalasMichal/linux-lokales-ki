#!/usr/bin/env python3
"""Forced-compact regression with knowledge_search before the PDF chain."""
from __future__ import annotations

import json
import sys
import threading
import time
from collections import Counter
from pathlib import Path

from quality_cutover_e2e import EventCollector, http_json, nvidia, ollama_ps, sse_loop, wait_for_turn

PROJECT = "/home/mike/Projects/Linux Lokales KI"
WORKSPACE = "/srv/ai/workspaces"
MODEL_ID = "local-quality(openai)"
OUT = Path(PROJECT) / "benchmarks" / "knowledge-base-20260922"
EXPECTED = ["knowledge_search", "memory_load", "pdf_create", "pdf_read", "memory_update"]


def run() -> dict:
    label = "compact-kb"
    pdf = f"{PROJECT}/.agent/tmp/knowledge-base/{label}.pdf"
    steps = f"""ONLY these five MCP tools, in order, once each. No ReadFile. No Edit. No write_file. No Shell. No YOLO.
After compact, CONTINUE remaining MCP steps.
1. tool_search select:knowledge_search → knowledge_search workspace="{PROJECT}" query="compact ledger" max_results=3
2. tool_search select:memory_load → memory_load workspace="{PROJECT}" files="STATE.md,TASKS.md"
3. tool_search select:pdf_create → pdf_create output="{pdf}" title="KB compact {label}" text="Knowledge Base compact regression."
4. tool_search select:pdf_read → pdf_read path="{pdf}"
5. tool_search select:memory_update → memory_update workspace="{PROJECT}" summary="KB compact regression {label}" decisions="Knowledge search before compact chain. No YOLO." decision_title="KB compact {label}"
After step 5 stop. Never edit ~/.qwen files.
"""
    prompt = f"""QUALITY MCP chain. Finish all 5 steps.

{steps}

Filler:
{("Knowledge compact filler line. " * 160)}

{steps}
"""
    OUT.mkdir(parents=True, exist_ok=True)
    Path(pdf).parent.mkdir(parents=True, exist_ok=True)
    if Path(pdf).is_file():
        Path(pdf).unlink()
    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    if created.get("attached"):
        http_json("DELETE", f"/session/{sid}")
        created = http_json("POST", "/session", {"cwd": WORKSPACE})
        sid = created["sessionId"]
    http_json("POST", f"/session/{sid}/model", {"modelId": MODEL_ID})
    try:
        http_json(
            "POST",
            f"/session/{sid}/config-option",
            {"configId": "reasoning_effort", "value": "none", "persist": False},
        )
    except Exception:
        pass
    stop = threading.Event()
    collector = EventCollector(sid)
    threading.Thread(target=sse_loop, args=(sid, collector, stop), daemon=True).start()
    time.sleep(0.8)
    prompt_error = None
    try:
        http_json("POST", f"/session/{sid}/prompt", {"prompt": [{"type": "text", "text": prompt}]}, timeout=30)
    except Exception as exc:
        prompt_error = str(exc)
    wait_for_turn(sid, collector, t0, since)
    stop.set()
    counts: Counter = Counter()
    chat = Path.home() / ".qwen/projects/-srv-ai-workspaces/chats" / f"{sid}.jsonl"
    prompt_tokens: list[int] = []
    compact_events = 0
    ledger_seen = False
    if chat.is_file():
        blob = chat.read_text(encoding="utf-8")
        ledger_seen = "linux-lokales-ki-compact-state-ledger" in blob
        for line in blob.splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            um = obj.get("usageMetadata") or {}
            if isinstance(um.get("promptTokenCount"), int):
                prompt_tokens.append(um["promptTokenCount"])
            if obj.get("subtype") == "chat_compression":
                compact_events += 1
            event = ((obj.get("systemPayload") or {}).get("uiEvent") or {})
            if event.get("event.name") == "qwen-code.tool_call" and event.get("success"):
                short = str(event.get("function_name") or "").split("__")[-1]
                if short in EXPECTED:
                    counts[short] += 1
    duplicates = {k: v for k, v in counts.items() if v > 1}
    over = any(n > 15565 for n in prompt_tokens)
    # Allow one prompt at/over threshold that *triggers* compact; fail if any post-compact prompt stays over.
    post_compact = []
    if compact_events and prompt_tokens:
        # tokens after the peak that triggered compact
        peak_i = max(range(len(prompt_tokens)), key=lambda i: prompt_tokens[i])
        post_compact = prompt_tokens[peak_i + 1 :]
    immediate_second = compact_events >= 2 and any(n > 15565 for n in post_compact[:2])
    hard = any(n > 16384 for n in prompt_tokens)
    report = {
        "label": label,
        "sessionId": sid,
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "prompt_error": prompt_error,
        "completed_counts": dict(counts),
        "duplicates": duplicates,
        "compressed": compact_events > 0,
        "compact_events": compact_events,
        "ledger_seen": ledger_seen,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max(prompt_tokens) if prompt_tokens else None,
        "post_compact_tokens": post_compact,
        "max_post_compact": max(post_compact) if post_compact else None,
        "pdf_exists": Path(pdf).is_file(),
        "over_threshold_peak": over,
        "immediate_second_compact": immediate_second,
        "hard_overflow": hard,
        "nvidia": nvidia(),
        "ollama_ps": ollama_ps(),
    }
    report["pass"] = bool(
        not prompt_error
        and report["pdf_exists"]
        and compact_events >= 1
        and not duplicates
        and not hard
        and not immediate_second
        and (ledger_seen or (post_compact and max(post_compact) <= 14500))
        and counts.get("knowledge_search") == 1
        and counts.get("memory_load") == 1
        and counts.get("pdf_create") == 1
        and counts.get("pdf_read") == 1
        and counts.get("memory_update") == 1
        and (not post_compact or max(post_compact) <= 14500)
    )
    (OUT / f"{label}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"pass": report["pass"], **{k: report[k] for k in ("completed_counts", "duplicates", "compressed", "ledger_seen", "max_prompt_tokens", "elapsed_s")}}, indent=2))
    return report


if __name__ == "__main__":
    result = run()
    raise SystemExit(0 if result["pass"] else 1)
