#!/usr/bin/env python3
"""A/B harness: QUALITY multi-tool essays between MCP calls.

Votes proceed_once only. No YOLO. Restores default local-fast.
Does not abort while GPU/token/tool progress is visible.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

from quality_cutover_e2e import (
    EventCollector,
    health_snapshot,
    http_json,
    nvidia,
    ollama_ps,
    pick_allow,
    sse_loop,
)

PROJECT = "/home/mike/Projects/Linux Lokales KI"
WORKSPACE = "/srv/ai/workspaces"
OUT = Path(PROJECT) / "benchmarks" / "quality-essay-ab-20260916"
EXPECTED = ["memory_load", "pdf_create", "pdf_read"]

STEPS_ONLY = """You are in one continuous session. Use real MCP tools. Wait for permission. No YOLO. No /tmp.

Do these steps in order:
1. mcp__local-tools__memory_load workspace="{project}"
2. mcp__local-tools__pdf_create output="{pdf}" title="Essay AB {variant}" text="QUALITY 16k essay-control A/B variant {variant}."
3. mcp__local-tools__pdf_read path="{pdf}"
"""

COMPACT_RULE = """
After a successful tool, immediately call the next required tool.
At most one short status sentence between tools. No intermediate summary, no recap of memory files, no analysis essay.
Full report only after the last tool returns. Stop after pdf_read.
"""


def prompt_for(variant: str, pdf: str) -> str:
    base = STEPS_ONLY.format(project=PROJECT, pdf=pdf, variant=variant)
    if variant == "B":
        return base + COMPACT_RULE
    return base + "\nStop after pdf_read returns.\n"


class TimedCollector(EventCollector):
    def __init__(self, session_id: str = "") -> None:
        super().__init__(session_id)
        self.t0 = time.perf_counter()
        self.timeline: list[dict] = []

    def _elapsed(self) -> float:
        return round(time.perf_counter() - self.t0, 3)

    def handle(self, event_type: str, payload: dict) -> None:
        super().handle(event_type, payload)
        inner = payload.get("data") if isinstance(payload, dict) else None
        data = inner if isinstance(inner, dict) else payload
        update = None
        if isinstance(data, dict):
            update = data.get("update") or data.get("data") or data
        session_update = update.get("sessionUpdate") if isinstance(update, dict) else None
        if session_update in {"tool_call", "tool_call_update"} and isinstance(update, dict):
            self.timeline.append(
                {
                    "t": self._elapsed(),
                    "kind": "tool",
                    "id": update.get("toolCallId"),
                    "name": update.get("name") or update.get("title"),
                    "status": update.get("status"),
                }
            )
        if isinstance(update, dict) and update.get("sessionUpdate") == "agent_message_chunk":
            content = update.get("content") or {}
            text = content.get("text") if isinstance(content, dict) else None
            if text:
                self.timeline.append({"t": self._elapsed(), "kind": "text", "text": text})
        if isinstance(payload, dict) and "approached the input token limit" in str(payload):
            self.timeline.append({"t": self._elapsed(), "kind": "compress_hint", "raw": str(payload)[:400]})


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
            }
        )
    return out


def names_hit(tools: list[dict]) -> list[str]:
    hit = []
    for item in tools:
        blob = str(item.get("name") or "").lower()
        for expect in EXPECTED:
            if expect in blob and "toolsearch" not in blob.replace("_", ""):
                hit.append(expect)
    return hit


def segments_from_timeline(timeline: list[dict]) -> list[dict]:
    segs = []
    buf = []
    start = 0.0
    last_tool = None
    for event in timeline:
        if event.get("kind") == "text":
            if not buf:
                start = event["t"]
            buf.append(event.get("text") or "")
        elif event.get("kind") == "tool" and event.get("status") in {"pending", "in_progress", None}:
            text = "".join(buf)
            segs.append(
                {
                    "after_tool": last_tool,
                    "before_tool": event.get("name"),
                    "start_s": start if buf else event["t"],
                    "end_s": event["t"],
                    "chars": len(text),
                    "approx_tokens": max(1, len(text) // 4) if text else 0,
                    "text_preview": text[:400],
                }
            )
            buf = []
            last_tool = event.get("name")
        elif event.get("kind") == "tool" and event.get("status") == "completed":
            last_tool = event.get("name")
    text = "".join(buf)
    if text:
        segs.append(
            {
                "after_tool": last_tool,
                "before_tool": "(final/leftover)",
                "start_s": start,
                "end_s": timeline[-1]["t"] if timeline else 0,
                "chars": len(text),
                "approx_tokens": max(1, len(text) // 4),
                "text_preview": text[:400],
            }
        )
    return segs


def restore_default_model() -> None:
    import subprocess

    script = Path(PROJECT) / "scripts" / "set-qwen-quality-context.py"
    settings = Path.home() / ".qwen" / "settings.json"
    subprocess.check_call([script.as_posix(), str(settings), "16384"])


def wait_measured(
    session_id: str,
    collector: TimedCollector,
    t0: float,
    expected: list[str],
    since: str,
) -> dict:
    last = {}
    last_progress = time.time()
    last_sig = None
    leftover_since = None
    deadline = time.time() + 720
    next_periodic = 8.0
    abort = None
    cancelled = False
    while time.time() < deadline:
        elapsed = round(time.perf_counter() - t0, 1)
        snap = health_snapshot(session_id, collector, since)
        last = snap
        if snap["wait_perm"]:
            vote_pending(session_id, collector)
        tools = compact_tools(collector)
        hit = names_hit(tools)
        completed = [x for x in hit if True]
        text_len = sum(len(x) for x in collector.texts)
        sig = (snap["tools"], snap["votes"], snap.get("n_gen"), text_len, snap["gpu_util"] > 8)
        if sig != last_sig:
            last_progress = time.time()
            last_sig = sig
        if elapsed >= next_periodic:
            print(
                f"[health {elapsed}s] active={snap['active']} tools={snap['tools']} "
                f"votes={snap['votes']} n_gen={snap['n_gen']} gpu={snap['gpu_util']}% "
                f"vram={snap['vram']} chars={text_len} hit={completed}",
                flush=True,
            )
            next_periodic += 15 if next_periodic > 20 else 8
        all_done = all(name in hit for name in expected)
        if all_done and leftover_since is None:
            leftover_since = time.time()
            print(f"[tools-done {elapsed}s] measuring leftover", flush=True)
        if all_done and leftover_since is not None:
            leftover = time.time() - leftover_since
            if not snap["active"] or leftover >= 40:
                if snap["active"] and not cancelled:
                    try:
                        http_json("POST", f"/session/{session_id}/cancel", {})
                        cancelled = True
                        print("[cancel] leftover after expected tools", flush=True)
                    except Exception as exc:
                        print(f"[cancel] {exc}", flush=True)
                if not snap["active"] or leftover >= 45:
                    break
        if time.time() - last_progress >= 180:
            abort = f"180s ohne Fortschritt nach {elapsed}s"
            break
        if not snap["active"] and elapsed > 10 and all_done:
            time.sleep(1)
            snap = health_snapshot(session_id, collector, since)
            last = snap
            if not snap["active"]:
                break
        time.sleep(2)
    if abort:
        print(f"[abort] {abort}", flush=True)
        try:
            http_json("POST", f"/session/{session_id}/cancel", {})
        except Exception as exc:
            print(f"[cancel] {exc}", flush=True)
    last["abort"] = abort
    last["cancelled_leftover"] = cancelled
    return last


def run_variant(variant: str, model_id: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    pdf = f"{PROJECT}/.agent/tmp/essay-ab-{variant}.pdf"
    Path(pdf).parent.mkdir(parents=True, exist_ok=True)
    if Path(pdf).is_file():
        Path(pdf).unlink()
    t0 = time.perf_counter()
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
    model = http_json("POST", f"/session/{sid}/model", {"modelId": model_id})
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
    collector = TimedCollector(sid)
    threading.Thread(target=sse_loop, args=(sid, collector, stop), daemon=True).start()
    time.sleep(0.8)

    def poll() -> None:
        while not stop.is_set():
            vote_pending(sid, collector)
            time.sleep(0.6)

    threading.Thread(target=poll, daemon=True).start()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    prompt_error = None
    prompt_result = None
    try:
        prompt_result = http_json(
            "POST",
            f"/session/{sid}/prompt",
            {"prompt": [{"type": "text", "text": prompt_for(variant, pdf)}]},
            timeout=30,
        )
        print(f"[prompt] {prompt_result}", flush=True)
    except Exception as exc:
        prompt_error = str(exc)
        print(f"[prompt] FAIL {exc}", flush=True)
    final_health = wait_measured(sid, collector, t0, EXPECTED, since)
    stop.set()
    tools = compact_tools(collector)
    hit = names_hit(tools)
    segs = segments_from_timeline(collector.timeline)
    max_mid = max((s["approx_tokens"] for s in segs if s.get("before_tool") != "(final/leftover)"), default=0)
    yolo = any("yolo" in str(v.get("optionId") or "").lower() for v in collector.votes)
    always = any("always" in str(v.get("optionId") or "").lower() for v in collector.votes)
    ok_votes = [v for v in collector.votes if v.get("ok")]
    assistant = "".join(collector.texts)
    compressed = "compressed from" in assistant.lower() or "input token limit" in assistant.lower()
    report = {
        "variant": variant,
        "model_id": model_id,
        "sessionId": sid,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "prompt_error": prompt_error,
        "prompt_result": prompt_result,
        "votes": collector.votes,
        "tools": tools,
        "tool_names": hit,
        "missing": [x for x in EXPECTED if x not in hit],
        "duplicate_tools": [n for n in hit if hit.count(n) > 1],
        "thoughts": collector.thoughts,
        "assistant_chars": len(assistant),
        "assistant_approx_tokens": len(assistant) // 4,
        "segments": segs,
        "max_mid_tokens": max_mid,
        "compressed": compressed,
        "pdf_exists": Path(pdf).is_file(),
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
        "assistant_text": assistant[:8000],
    }
    report["pass_tools"] = bool(
        not prompt_error
        and Path(pdf).is_file()
        and not report["missing"]
        and not yolo
        and not always
        and ok_votes
        and all(v.get("optionId") == "proceed_once" for v in ok_votes)
    )
    report["essay_ok"] = report["max_mid_tokens"] <= 500 and not compressed
    safe_model = model_id.split("(")[0]
    path = OUT / f"{variant}-{safe_model}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False)[:2_000_000], encoding="utf-8")
    print(
        json.dumps(
            {
                "variant": variant,
                "pass_tools": report["pass_tools"],
                "essay_ok": report["essay_ok"],
                "elapsed_s": report["elapsed_s"],
                "tool_names": hit,
                "missing": report["missing"],
                "duplicate_tools": report["duplicate_tools"],
                "max_mid_tokens": max_mid,
                "assistant_approx_tokens": report["assistant_approx_tokens"],
                "compressed": compressed,
                "votes": len(collector.votes),
            },
            indent=2,
            ensure_ascii=False,
        ),
        flush=True,
    )
    print("WROTE", path, flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="A")
    parser.add_argument("--model", default="local-quality(openai)")
    args = parser.parse_args()
    try:
        run_variant(args.variant, args.model)
    finally:
        try:
            restore_default_model()
            print("[restore] default local-fast, quality ctx 16384", flush=True)
        except Exception as exc:
            print(f"[restore] FAIL {exc}", flush=True)


if __name__ == "__main__":
    main()
