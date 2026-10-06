#!/usr/bin/env python3
"""Single-session 16k QUALITY agent E2E via qwen serve.

Uses bench-qwen38-27b-16k. Does not retarget local-quality.
Votes proceed_once only. No YOLO. trust stays false.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from quality_cutover_e2e import (
    BASE,
    EventCollector,
    http_json,
    nvidia,
    ollama_ps,
    pick_allow,
    sse_loop,
    wait_for_turn,
)

PROJECT = "/home/mike/Projects/Linux Lokales KI"
WORKSPACE = "/srv/ai/workspaces"
MODEL_ID = "bench-qwen38-27b-16k(openai)"
OUT = Path(PROJECT) / "benchmarks" / "ctx16k-20260916"
PDF = f"{PROJECT}/.agent/tmp/ctx16k-e2e.pdf"
PNG = f"{PROJECT}/.agent/tmp/ctx16k-e2e.png"

PROMPT = f"""You are in one continuous session. Use real MCP tools. Wait for permission. No YOLO. No /tmp.

Do these steps in order:
1. mcp__local-tools__memory_load workspace="{PROJECT}"
2. mcp__local-tools__pdf_create output="{PDF}" title="16K Context E2E" text="Qwen3.8 27B bench alias at 16384. local-quality stays 8192. FAST stays local-fast."
3. mcp__local-tools__pdf_read path="{PDF}"
4. mcp__local-tools__pdf_render path="{PDF}" output="{PNG}" page=1
5. mcp__local-tools__pdf_vision_qa path="{PDF}"
6. mcp__local-tools__memory_update workspace="{PROJECT}" summary="16k bench E2E ran in one qwen-serve session." decisions="2026-09-16 — 16k agent E2E used bench-qwen38-27b-16k; local-quality stayed 8192." decision_title="16k QUALITY agent E2E" — do not wipe unrelated STATE/TASKS content.

Stop after memory_update returns. Short confirmation only.
"""

EXPECTED = ["memory_load", "pdf_create", "pdf_read", "pdf_render", "pdf_vision_qa", "memory_update"]


def vote_pending(session_id: str, collector: EventCollector) -> None:
    try:
        status = http_json("GET", f"/session/{session_id}/status")
    except Exception:
        return
    for item in status.get("pendingInteractions") or []:
        request_id = item.get("requestId") or item.get("id")
        if not request_id:
            continue
        oid = pick_allow(item.get("options") or []) or "proceed_once"
        try:
            http_json(
                "POST",
                f"/session/{session_id}/permission/{request_id}",
                {"outcome": {"outcome": "selected", "optionId": oid}},
            )
            print(f"[vote] {request_id} -> {oid}", flush=True)
            collector.votes.append({"requestId": request_id, "optionId": oid, "ok": True})
        except Exception as exc:
            print(f"[vote] fail {exc}", flush=True)


def compact_tools(collector: EventCollector) -> list[dict]:
    seen = []
    out = []
    for item in collector.tools:
        key = (item.get("id"), item.get("status"))
        if key in seen:
            continue
        seen.append(key)
        out.append(
            {
                "id": item.get("id"),
                "name": item.get("name") or item.get("title"),
                "status": item.get("status"),
                "input": item.get("rawInput"),
            }
        )
    return out


def names_hit(tools: list[dict]) -> set[str]:
    hit = set()
    for item in tools:
        blob = str(item.get("name") or "").lower()
        for expect in EXPECTED:
            if expect in blob and "toolsearch" not in blob.replace("_", ""):
                hit.add(expect)
    return hit


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    Path(PDF).parent.mkdir(parents=True, exist_ok=True)
    for stale in (PDF, PNG):
        path = Path(stale)
        if path.is_file():
            path.unlink()
    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    mcp = http_json("GET", "/workspace/mcp")
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    print(f"[session] {sid}", flush=True)
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

    def poll_votes() -> None:
        while not stop.is_set():
            vote_pending(sid, collector)
            time.sleep(0.6)

    threading.Thread(target=poll_votes, daemon=True).start()
    prompt_error = None
    prompt_result = None
    try:
        prompt_result = http_json(
            "POST",
            f"/session/{sid}/prompt",
            {"prompt": [{"type": "text", "text": PROMPT}]},
            timeout=30,
        )
        print(f"[prompt] {prompt_result}", flush=True)
    except Exception as exc:
        prompt_error = str(exc)
        print(f"[prompt] FAIL {exc}", flush=True)
    final_health = wait_for_turn(sid, collector, t0, since)
    stop.set()
    tools = compact_tools(collector)
    hit = names_hit(tools)
    pdf_ok = Path(PDF).is_file()
    png_ok = Path(PNG).is_file()
    yolo = any("yolo" in str(v.get("optionId") or "").lower() for v in collector.votes)
    always = any("always" in str(v.get("optionId") or "").lower() for v in collector.votes)
    continuous = True  # single session by construction
    report = {
        "sessionId": sid,
        "model_switch": model,
        "model_id": MODEL_ID,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "prompt_error": prompt_error,
        "prompt_result": prompt_result,
        "votes": collector.votes,
        "tools": tools,
        "expected_hit": sorted(hit),
        "missing": [x for x in EXPECTED if x not in hit],
        "thoughts": collector.thoughts,
        "assistant_text": "".join(collector.texts),
        "pdf_exists": pdf_ok,
        "png_exists": png_ok,
        "yolo": yolo,
        "always_allow": always,
        "single_session": continuous,
        "mcp_status": {
            "initialized": mcp.get("initialized"),
            "servers": [
                {"name": s.get("name"), "status": s.get("status"), "trust": s.get("trust")}
                for s in (mcp.get("servers") or mcp.get("mcpServers") or [])
                if isinstance(s, dict)
            ],
        },
        "health": final_health,
        "nvidia": nvidia(),
        "ollama_ps": ollama_ps(),
    }
    report["pass"] = bool(
        not prompt_error
        and pdf_ok
        and png_ok
        and "memory_load" in hit
        and "pdf_vision_qa" in hit
        and "memory_update" in hit
        and not yolo
        and not always
        and collector.votes
        and all(v.get("optionId") == "proceed_once" for v in collector.votes if v.get("ok"))
    )
    (OUT / "e2e.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)[:2_000_000], encoding="utf-8")
    print(json.dumps({
        "pass": report["pass"],
        "elapsed_s": report["elapsed_s"],
        "expected_hit": report["expected_hit"],
        "missing": report["missing"],
        "votes": len(collector.votes),
        "thoughts": collector.thoughts,
        "pdf_exists": pdf_ok,
        "png_exists": png_ok,
        "nvidia": report["nvidia"],
        "ollama_ps": report["ollama_ps"],
        "assistant_tail": report["assistant_text"][-800:],
    }, indent=2, ensure_ascii=False))
    print("WROTE", OUT / "e2e.json", "PASS" if report["pass"] else "FAIL", flush=True)
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
