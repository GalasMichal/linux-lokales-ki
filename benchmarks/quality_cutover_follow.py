#!/usr/bin/env python3
"""Follow an in-flight Qwen session: SSE + Allow-once votes + wait for settle."""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:4170"
PROJECT = "/home/mike/Projects/Linux Lokales KI"
OUT = Path(PROJECT) / "benchmarks" / "quality-cutover-20260915"
SESSION = sys.argv[1] if len(sys.argv) > 1 else "e2ab61f0-8502-4bef-89d0-dd5fdc4591ab"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quality_cutover_e2e import EventCollector, http_json, nvidia, ollama_ps, sse_loop  # noqa: E402


def main() -> None:
    t0 = time.perf_counter()
    stop = threading.Event()
    collector = EventCollector()
    thread = threading.Thread(target=sse_loop, args=(SESSION, collector, stop), daemon=True)
    thread.start()
    last_status = {}
    deadline = time.time() + 1200
    while time.time() < deadline:
        last_status = http_json("GET", f"/session/{SESSION}/status")
        active = last_status.get("hasActivePrompt")
        waiting = last_status.get("isWaitingForPermission")
        pending = last_status.get("pendingInteractions") or []
        print(
            f"[status] active={active} wait_perm={waiting} pending={len(pending)} votes={len(collector.votes)} tools={len(collector.tools)}",
            flush=True,
        )
        if waiting and pending:
            for item in pending:
                request_id = item.get("requestId") or item.get("id")
                if not request_id:
                    continue
                options = item.get("options") or [{"optionId": "allow"}]
                from quality_cutover_e2e import pick_allow

                oid = pick_allow(options) or "allow"
                try:
                    http_json(
                        "POST",
                        f"/session/{SESSION}/permission/{request_id}",
                        {"outcome": {"outcome": "selected", "optionId": oid}},
                    )
                    print(f"[vote-poll] {request_id} -> {oid}", flush=True)
                except Exception as exc:
                    print(f"[vote-poll] fail {exc}", flush=True)
        if not active and collector.tools:
            time.sleep(1.5)
            last_status = http_json("GET", f"/session/{SESSION}/status")
            if not last_status.get("hasActivePrompt"):
                break
        if not active and time.time() - t0 > 20 and not collector.tools:
            # still starting; keep waiting
            pass
        time.sleep(3)
    stop.set()
    thread.join(timeout=5)
    context = {}
    transcript = {}
    try:
        context = http_json("GET", f"/session/{SESSION}/context")
    except Exception as exc:
        context = {"error": str(exc)}
    try:
        transcript = http_json("GET", f"/session/{SESSION}/transcript")
    except Exception as exc:
        transcript = {"error": str(exc)}
    tools = []
    seen = set()
    for item in collector.tools:
        key = (item.get("id"), item.get("status"))
        if key in seen:
            continue
        seen.add(key)
        tools.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "title": item.get("title"),
                "status": item.get("status"),
                "input": item.get("rawInput"),
            }
        )
    result = {
        "sessionId": SESSION,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "final_status": last_status,
        "votes": collector.votes,
        "permissions": collector.permissions,
        "tools": tools,
        "assistant_text": "".join(collector.texts),
        "sse_error": collector.error,
        "event_count": len(collector.events),
        "context": context,
        "transcript_head": transcript if isinstance(transcript, dict) else {"raw": str(transcript)[:5000]},
        "nvidia": nvidia(),
        "ollama_ps": ollama_ps(),
    }
    (OUT / "e2e-follow.json").write_text(json.dumps(result, indent=2, ensure_ascii=False)[:2_000_000], encoding="utf-8")
    (OUT / "e2e-follow-events.json").write_text(
        json.dumps(collector.events[:500], indent=2, ensure_ascii=False)[:2_000_000],
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "elapsed_s": result["elapsed_s"],
            "hasActivePrompt": last_status.get("hasActivePrompt"),
            "votes": result["votes"],
            "tools": tools,
            "assistant_tail": result["assistant_text"][-2000:],
            "nvidia": result["nvidia"],
            "ollama_ps": result["ollama_ps"],
        },
        indent=2,
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
