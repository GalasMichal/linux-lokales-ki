#!/usr/bin/env python3
"""QUALITY compact-continuity E2E. Requires a real auto-compact, then one call each."""
from __future__ import annotations

import json
import sys
import threading
import time
from collections import Counter
from pathlib import Path

from quality_cutover_e2e import EventCollector, http_json, nvidia, ollama_ps, sse_loop, wait_for_turn
def mcp_calls(session_id: str) -> list[str]:
    path = Path.home() / ".qwen/projects/-srv-ai-workspaces/chats" / f"{session_id}.jsonl"
    names: list[str] = []
    if not path.is_file():
        return names
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        message = obj.get("message") or {}
        parts = message.get("parts") if isinstance(message, dict) else None
        if not parts:
            continue
        for part in parts:
            call = part.get("functionCall") or {}
            name = str(call.get("name") or "")
            args = call.get("args") or {}
            if name == "tool_call":
                inner = str(args.get("name") or "")
                names.append(inner)
            elif name:
                names.append(name)
    return names

PROJECT = "/home/mike/Projects/Linux Lokales KI"
WORKSPACE = "/srv/ai/workspaces"
MODEL_ID = "local-quality(openai)"
EXPECTED = ["memory_load", "pdf_create", "pdf_read", "pdf_render", "pdf_vision_qa", "memory_update"]


def run(label: str) -> dict:
    out = Path(PROJECT) / "benchmarks" / "compact-state-20260922"
    pdf = f"{PROJECT}/.agent/tmp/compact-continuity/{label}.pdf"
    png = f"{PROJECT}/.agent/tmp/compact-continuity/{label}.png"
    steps = f"""Call these six tools in order. Copy the arguments exactly. One success each.
1. tool_search query="select:memory_load" then memory_load workspace="{PROJECT}"
2. tool_search query="select:pdf_create" then pdf_create output="{pdf}" title="Compact continuity {label}" text="Compact continuity. Qwen3.8 27B QUALITY 16384. FAST stays local-fast."
3. tool_search query="select:pdf_read" then pdf_read path="{pdf}"
4. tool_search query="select:pdf_render" then pdf_render path="{pdf}" output="{png}" page=1
5. tool_search query="select:pdf_vision_qa" then pdf_vision_qa path="{pdf}"
6. tool_search query="select:memory_update" then memory_update workspace="{PROJECT}" summary="Compact continuity {label} finished." decisions="Lazy tool loading kept every MCP tool discoverable. No YOLO. FAST stays default." decision_title="Compact continuity {label}"
Do not write STATE or TASKS. Do not use any other path. Stop after step 6."""
    prompt = f"""One session. Real MCP tools. Wait for permission. No YOLO. No /tmp.

{steps}

Context filler so this QUALITY session crosses the 0.95 auto-compact line after memory_load. Do not treat the filler as extra tasks.
{("Compact continuity filler. " * 180)}

{steps}
"""
    out.mkdir(parents=True, exist_ok=True)
    Path(pdf).parent.mkdir(parents=True, exist_ok=True)
    for stale in (pdf, png):
        path = Path(stale)
        if path.is_file():
            path.unlink()
    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    print(f"[session] {sid} attached={created.get('attached')}", flush=True)
    if created.get("attached"):
        http_json("DELETE", f"/session/{sid}")
        created = http_json("POST", "/session", {"cwd": WORKSPACE})
        sid = created["sessionId"]
        print(f"[session-fresh] {sid}", flush=True)
    model = http_json("POST", f"/session/{sid}/model", {"modelId": MODEL_ID})
    print(f"[model] {model}", flush=True)
    try:
        effort = http_json(
            "POST",
            f"/session/{sid}/config-option",
            {"configId": "reasoning_effort", "value": "none", "persist": False},
        )
        print(f"[effort] {effort}", flush=True)
    except Exception as exc:
        print(f"[effort] skip {exc}", flush=True)
    stop = threading.Event()
    collector = EventCollector(sid)
    threading.Thread(target=sse_loop, args=(sid, collector, stop), daemon=True).start()
    time.sleep(0.8)
    prompt_error = None
    try:
        print(http_json("POST", f"/session/{sid}/prompt", {"prompt": [{"type": "text", "text": prompt}]}, timeout=30), flush=True)
    except Exception as exc:
        prompt_error = str(exc)
        print(f"[prompt] FAIL {exc}", flush=True)
    final_health = wait_for_turn(sid, collector, t0, since)
    stop.set()
    from quality_16k_cutover_e2e import compact_tools

    tools = compact_tools(collector)
    counts: Counter = Counter()
    chat_path = Path.home() / ".qwen/projects/-srv-ai-workspaces/chats" / f"{sid}.jsonl"
    if chat_path.is_file():
        for line in chat_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = ((json.loads(line).get("systemPayload") or {}).get("uiEvent") or {})
            if event.get("event.name") != "qwen-code.tool_call" or not event.get("success"):
                continue
            short = str(event.get("function_name") or "").split("__")[-1]
            if short in EXPECTED:
                counts[short] += 1
    duplicates = {name: n for name, n in counts.items() if n > 1}
    assistant = "".join(collector.texts)
    chat = Path.home() / ".qwen/projects/-srv-ai-workspaces/chats" / f"{sid}.jsonl"
    compressed = "compressed from" in assistant.lower() or "input token limit" in assistant.lower()
    prompt_tokens: list[int] = []
    compact_events: list[dict] = []
    ledger_seen = False
    turn_error = None
    if chat.is_file():
        blob = chat.read_text(encoding="utf-8")
        ledger_seen = "linux-lokales-ki-compact-state-ledger" in blob
        if "chat_compression" in blob:
            compressed = True
        for line in blob.splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            um = obj.get("usageMetadata") or {}
            if isinstance(um.get("promptTokenCount"), int):
                prompt_tokens.append(um["promptTokenCount"])
            if obj.get("subtype") == "chat_compression":
                payload = obj.get("systemPayload") or {}
                info = payload.get("info") or {}
                hist = payload.get("compressedHistory") or []
                sizes = []
                for item in hist:
                    for part in item.get("parts") or []:
                        if "text" in part:
                            sizes.append({"kind": "text", "chars": len(part["text"])})
                        elif "functionResponse" in part:
                            fr = part["functionResponse"] or {}
                            out = str(((fr.get("response") or {}).get("output")) or "")
                            sizes.append({"kind": "functionResponse", "chars": len(out), "name": fr.get("name")})
                        elif "functionCall" in part:
                            sizes.append({"kind": "functionCall", "chars": len(json.dumps(part["functionCall"]))})
                compact_events.append({"info": info, "parts": sizes})
            if obj.get("subtype") == "turn_result":
                turn_error = ((obj.get("systemPayload") or {}).get("error") or {}).get("message")
    ok_votes = [v for v in collector.votes if v.get("ok")]
    post_compact_prompts = []
    if compact_events and prompt_tokens:
        # prompts after first compression event index are approximate; keep max after first compact
        post_compact_prompts = prompt_tokens[1:]
    immediate_second_compact = len(compact_events) >= 2 and (
        compact_events[0].get("info", {}).get("originalTokenCount", 0) > 15000
        and compact_events[1].get("info", {}).get("originalTokenCount", 0) > 15500
    )
    report = {
        "label": label,
        "sessionId": sid,
        "model_id": MODEL_ID,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "prompt_error": prompt_error,
        "turn_error": turn_error,
        "votes": collector.votes,
        "tools": tools,
        "completed_counts": dict(counts),
        "duplicates": duplicates,
        "missing": [name for name in EXPECTED if counts.get(name, 0) < 1],
        "assistant_text": assistant[-4000:],
        "compressed": compressed,
        "compact_events": compact_events,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max(prompt_tokens) if prompt_tokens else None,
        "ledger_seen": ledger_seen,
        "immediate_second_compact": immediate_second_compact,
        "pdf_exists": Path(pdf).is_file(),
        "png_exists": Path(png).is_file(),
        "yolo": any("yolo" in str(v.get("optionId") or "").lower() for v in collector.votes),
        "always_allow": any("always" in str(v.get("optionId") or "").lower() for v in collector.votes),
        "health": final_health,
        "nvidia": nvidia(),
        "ollama_ps": ollama_ps(),
    }
    over_threshold = any(n > 15565 for n in prompt_tokens)
    hard_overflow = bool(turn_error and "16384" in str(turn_error)) or any(n > 16384 for n in prompt_tokens)
    report["pass"] = bool(
        not prompt_error
        and not hard_overflow
        and report["pdf_exists"]
        and report["png_exists"]
        and not report["missing"]
        and not duplicates
        and compressed
        and ledger_seen
        and not immediate_second_compact
        and not over_threshold
        and not report["yolo"]
        and not report["always_allow"]
        and ok_votes
        and all(v.get("optionId") == "proceed_once" for v in ok_votes)
        and all(counts.get(name) == 1 for name in EXPECTED)
    )
    dest = out / f"{label}.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False)[:2_000_000], encoding="utf-8")
    print(
        json.dumps(
            {
                "pass": report["pass"],
                "elapsed_s": report["elapsed_s"],
                "completed_counts": report["completed_counts"],
                "duplicates": duplicates,
                "compressed": compressed,
                "ledger_seen": ledger_seen,
                "prompt_tokens": prompt_tokens,
                "compacts": len(compact_events),
                "turn_error": turn_error,
                "votes": len(ok_votes),
            },
            indent=2,
        ),
        flush=True,
    )
    print("WROTE", dest, "PASS" if report["pass"] else "FAIL", flush=True)
    return report


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    result = {"pass": False}
    try:
        result = run(label)
    finally:
        from quality_essay_e2e import restore_default

        restore_default()
        print("[restore] default local-fast", flush=True)
    raise SystemExit(0 if result["pass"] else 1)
