#!/usr/bin/env python3
"""Full QUALITY agent E2E after essay-control fix. proceed_once only. No YOLO."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

from quality_16k_cutover_e2e import compact_tools, names_hit, vote_pending
from quality_cutover_e2e import (
    EventCollector,
    http_json,
    nvidia,
    ollama_ps,
    sse_loop,
    wait_for_turn,
)

PROJECT = "/home/mike/Projects/Linux Lokales KI"
WORKSPACE = "/srv/ai/workspaces"
MODEL_ID = "local-quality(openai)"
OUT = Path(PROJECT) / "benchmarks" / "quality-essay-ab-20260916"
PDF = f"{PROJECT}/.agent/tmp/quality-essay-e2e.pdf"
PNG = f"{PROJECT}/.agent/tmp/quality-essay-e2e.png"
EXPECTED = ["memory_load", "pdf_create", "pdf_read", "pdf_render", "pdf_vision_qa", "memory_update"]

PROMPT = f"""One session. Real MCP tools. Wait for permission. No YOLO. No /tmp.

Order:
1. mcp__local-tools__memory_load workspace="{PROJECT}"
2. mcp__local-tools__pdf_create output="{PDF}" title="QUALITY Essay-Control E2E" text="Qwen3.8 27B QUALITY 16384. FAST stays local-fast."
3. mcp__local-tools__pdf_read path="{PDF}"
4. mcp__local-tools__pdf_render path="{PDF}" output="{PNG}" page=1
5. mcp__local-tools__pdf_vision_qa path="{PDF}"
6. mcp__local-tools__memory_update workspace="{PROJECT}" summary="QUALITY hidden-gen E2E ran in one serve session." decisions="Hidden post-tool tokens were Qwen auto-compact analysis. context.autoCompactThreshold=0.95 and compactionModel=local-fast. No global max_tokens. FAST stays default." decision_title="QUALITY hidden-gen compact fix"

Do not replace unrelated STATE/TASKS. After each successful tool, call the next tool immediately. One short status sentence max between tools. Stop after memory_update.
"""


def restore_default() -> None:
    script = Path(PROJECT) / "scripts" / "set-qwen-quality-context.py"
    settings = Path.home() / ".qwen" / "settings.json"
    subprocess.check_call([script.as_posix(), str(settings), "16384"])


def completed_counts(tools: list[dict]) -> Counter:
    counts: Counter = Counter()
    for item in tools:
        if item.get("status") != "completed":
            continue
        blob = str(item.get("name") or "").lower()
        for expect in EXPECTED:
            if expect in blob and "toolsearch" not in blob.replace("_", ""):
                counts[expect] += 1
    return counts


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
    print(f"[session] {sid} attached={created.get('attached')}", flush=True)
    if created.get("attached"):
        try:
            http_json("DELETE", f"/session/{sid}")
            created = http_json("POST", "/session", {"cwd": WORKSPACE})
            sid = created["sessionId"]
            print(f"[session-fresh] {sid}", flush=True)
        except Exception as exc:
            print(f"[session-fresh] skip {exc}", flush=True)
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
    counts = completed_counts(tools)
    duplicates = {name: n for name, n in counts.items() if n > 1}
    assistant = "".join(collector.texts)
    compressed = "compressed from" in assistant.lower() or "input token limit" in assistant.lower()
    pdf_ok = Path(PDF).is_file()
    png_ok = Path(PNG).is_file()
    yolo = any("yolo" in str(v.get("optionId") or "").lower() for v in collector.votes)
    always = any("always" in str(v.get("optionId") or "").lower() for v in collector.votes)
    ok_votes = [v for v in collector.votes if v.get("ok")]
    report = {
        "sessionId": sid,
        "model_id": MODEL_ID,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "prompt_error": prompt_error,
        "votes": collector.votes,
        "tools": tools,
        "completed_counts": dict(counts),
        "duplicates": duplicates,
        "expected_hit": sorted(hit),
        "missing": [x for x in EXPECTED if x not in hit],
        "thoughts": collector.thoughts,
        "assistant_text": assistant,
        "compressed": compressed,
        "pdf_exists": pdf_ok,
        "png_exists": png_ok,
        "yolo": yolo,
        "always_allow": always,
        "mcp_status": {
            "initialized": mcp.get("initialized"),
            "servers": [
                {"name": s.get("name"), "status": s.get("status")}
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
        and not report["missing"]
        and not duplicates
        and not compressed
        and not yolo
        and not always
        and ok_votes
        and all(v.get("optionId") == "proceed_once" for v in ok_votes)
    )
    (OUT / "e2e.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)[:2_000_000], encoding="utf-8")
    print(
        json.dumps(
            {
                "pass": report["pass"],
                "elapsed_s": report["elapsed_s"],
                "expected_hit": report["expected_hit"],
                "missing": report["missing"],
                "duplicates": duplicates,
                "compressed": compressed,
                "votes": len(collector.votes),
                "pdf_exists": pdf_ok,
                "png_exists": png_ok,
                "assistant_tail": assistant[-600:],
            },
            indent=2,
            ensure_ascii=False,
        ),
        flush=True,
    )
    print("WROTE", OUT / "e2e.json", "PASS" if report["pass"] else "FAIL", flush=True)
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            restore_default()
            print("[restore] default local-fast", flush=True)
        except Exception as exc:
            print(f"[restore] FAIL {exc}", flush=True)
