#!/usr/bin/env python3
"""Multi-turn QUALITY MCP E2E: short prompts so 8k context still sees tools.

Wait for MCP tool completion before cancelling leftover essay text.
approvalMode stays default. Votes proceed_once only. No YOLO.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from quality_cutover_e2e import (
    BASE,
    MODEL_ID,
    OUT,
    PDF,
    PNG,
    PROJECT,
    WORKSPACE,
    EventCollector,
    http_json,
    nvidia,
    ollama_ps,
    pick_allow,
    sse_loop,
)

TURNS = [
    {
        "expect": "memory_load",
        "path": None,
        "text": (
            f'Call ONLY mcp__local-tools__memory_load with workspace="{PROJECT}". '
            "Stop immediately after the tool returns. No essay."
        ),
    },
    {
        "expect": "pdf_create",
        "path": PDF,
        "text": (
            f'Call ONLY mcp__local-tools__pdf_create with output="{PDF}", '
            'title="QUALITY Cutover E2E", '
            'text="Qwen3.8 27B is QUALITY at 8192. FAST stays local-fast." '
            "Stop immediately after the tool returns. No essay."
        ),
    },
    {
        "expect": "pdf_read",
        "path": None,
        "text": (
            f'Call ONLY mcp__local-tools__pdf_read with path="{PDF}". '
            "Stop immediately after the tool returns. No essay."
        ),
    },
    {
        "expect": "pdf_render",
        "path": PNG,
        "text": (
            f'Call ONLY mcp__local-tools__pdf_render with path="{PDF}", '
            f'output="{PNG}", page=1. Stop immediately after the tool returns. No essay.'
        ),
    },
    {
        "expect": "memory_update",
        "path": None,
        "text": (
            f'Call ONLY mcp__local-tools__memory_update with workspace="{PROJECT}", '
            'summary="QUALITY E2E Memory+PDF ran via qwen serve.", '
            'decisions="2026-09-15 — QUALITY E2E used short isolated sessions so 8k still sees MCP tools.", '
            'decision_title="QUALITY MCP E2E short sessions". '
            "Do not replace STATE.md or TASKS.md. Stop immediately after the tool returns."
        ),
    },
]


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


def tool_snapshot(collector: EventCollector) -> list[dict]:
    with collector.lock:
        return [dict(item) for item in collector.tools]


def matching_tools(collector: EventCollector, expect: str) -> list[dict]:
    needle = expect.lower()
    found = []
    for item in tool_snapshot(collector):
        blob = " ".join(str(item.get(key) or "") for key in ("name", "title")).lower()
        if "toolsearch" in blob.replace("_", "") or blob.startswith("tool_search"):
            continue
        if needle in blob:
            found.append(item)
    return found


def tool_completed(collector: EventCollector, expect: str) -> bool:
    done = {"completed", "success", "done", "ok"}
    return any(str(item.get("status") or "").lower() in done for item in matching_tools(collector, expect))


def cancel_prompt(session_id: str) -> None:
    try:
        http_json("POST", f"/session/{session_id}/cancel", {})
        print("[cancel] leftover essay after MCP completed", flush=True)
    except Exception as exc:
        print("[cancel]", exc, flush=True)


def wait_session_idle(session_id: str, seconds: int = 30) -> dict:
    last = {}
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            last = http_json("GET", f"/session/{session_id}/status")
        except Exception as exc:
            last = {"error": str(exc)}
            break
        if not last.get("hasActivePrompt") and not last.get("isWaitingForPermission"):
            break
        time.sleep(0.4)
    return last


def wait_ollama_idle(seconds: int = 40) -> str:
    deadline = time.time() + seconds
    last = ollama_ps()
    while time.time() < deadline:
        last = ollama_ps()
        gpu = nvidia()
        if gpu["gpu_util"] < 15 and "100%" not in last.split("PROCESSOR", 1)[-1][:80]:
            # ollama ps still shows a loaded model; that is fine. Wait until GPU is quiet.
            time.sleep(1.5)
            gpu2 = nvidia()
            if gpu2["gpu_util"] < 15:
                return last
        time.sleep(1)
    return last


def wait_idle(
    session_id: str,
    collector: EventCollector,
    t0: float,
    expect: str,
    success_path: str | None,
    seconds: int = 180,
) -> dict:
    deadline = time.time() + seconds
    last = {}
    votes_before = len(collector.votes)
    voted_at = None
    completed_at = None
    cancelled = False
    while time.time() < deadline:
        vote_pending(session_id, collector)
        if len(collector.votes) > votes_before and voted_at is None:
            voted_at = time.time()
        if tool_completed(collector, expect) and completed_at is None:
            completed_at = time.time()
        if success_path and Path(success_path).is_file() and completed_at is None:
            completed_at = time.time()
        status = http_json("GET", f"/session/{session_id}/status")
        last = status
        elapsed = round(time.perf_counter() - t0, 1)
        print(
            f"[wait {elapsed}s] active={status.get('hasActivePrompt')} wait={status.get('isWaitingForPermission')} "
            f"tools={len(collector.tools)} votes={len(collector.votes)} thoughts={collector.thoughts} "
            f"completed={bool(completed_at)}",
            flush=True,
        )
        if status.get("isWaitingForPermission"):
            time.sleep(0.4)
            continue
        if completed_at and not cancelled:
            # Give MCP a moment to flush files, then stop leftover generation.
            if time.time() - completed_at >= 3:
                if status.get("hasActivePrompt"):
                    cancel_prompt(session_id)
                    cancelled = True
                    last = wait_session_idle(session_id, seconds=20)
                    break
                break
        if (
            voted_at
            and completed_at is None
            and time.time() - voted_at >= 45
            and success_path
            and Path(success_path).is_file()
        ):
            completed_at = time.time()
            continue
        if (
            voted_at
            and completed_at is None
            and time.time() - voted_at >= 45
            and matching_tools(collector, expect)
            and not success_path
        ):
            # Local MCP should have finished; SSE may have missed completed.
            completed_at = time.time()
            continue
        if not status.get("hasActivePrompt") and elapsed > 3:
            time.sleep(1)
            status = http_json("GET", f"/session/{session_id}/status")
            last = status
            if not status.get("hasActivePrompt"):
                break
        time.sleep(2)
    return last


def run_turn(turn: dict, t0: float, model_id: str | None = None) -> dict:
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    http_json("POST", f"/session/{sid}/model", {"modelId": model_id or MODEL_ID})
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
    time.sleep(0.6)
    print(f"[session] {sid}", flush=True)
    print(f"[turn] {turn['expect']}: {turn['text'][:160]}", flush=True)
    http_json("POST", f"/session/{sid}/prompt", {"prompt": [{"type": "text", "text": turn["text"]}]})
    last = wait_idle(sid, collector, t0, turn["expect"], turn["path"], seconds=180)
    stop.set()
    try:
        http_json("DELETE", f"/session/{sid}")
    except Exception:
        pass
    wait_ollama_idle(seconds=25)
    return {
        "sessionId": sid,
        "expect": turn["expect"],
        "tools": collector.tools,
        "votes": collector.votes,
        "thoughts": collector.thoughts,
        "texts": collector.texts,
        "last": last,
        "path_exists": bool(turn["path"] and Path(turn["path"]).is_file()),
        "completed": tool_completed(collector, turn["expect"]),
    }


def main() -> None:
    Path(PDF).parent.mkdir(parents=True, exist_ok=True)
    for stale in (PDF, PNG):
        path = Path(stale)
        if path.is_file():
            path.unlink()
    t0 = time.perf_counter()
    turns = []
    for turn in TURNS:
        result = run_turn(turn, t0)
        turns.append(result)
        if turn["path"] and not Path(turn["path"]).is_file():
            print(f"[retry] {turn['expect']} missing {turn['path']}", flush=True)
            turns.append(run_turn(turn, t0))
        time.sleep(1)
    tools = []
    votes = []
    for turn in turns:
        votes.extend(turn["votes"])
        for item in turn["tools"]:
            tools.append(
                {
                    "name": item.get("name") or item.get("title"),
                    "status": item.get("status"),
                }
            )
    pdf_ok = Path(PDF).is_file()
    png_ok = Path(PNG).is_file()
    report = {
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "turns": [
            {
                "sessionId": t["sessionId"],
                "expect": t["expect"],
                "votes": len(t["votes"]),
                "thoughts": t["thoughts"],
                "completed": t["completed"],
                "path_exists": t["path_exists"],
                "tools": [
                    {"name": x.get("name") or x.get("title"), "status": x.get("status")}
                    for x in t["tools"]
                ],
            }
            for t in turns
        ],
        "votes": votes,
        "tools": tools,
        "pdf_exists": pdf_ok,
        "png_exists": png_ok,
        "nvidia": nvidia(),
        "ollama_ps": ollama_ps(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "e2e-multiturn.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print("WROTE", path, "pdf", pdf_ok, "png", png_ok, flush=True)
    if not (pdf_ok and png_ok and any(t["expect"] == "memory_load" and t["votes"] for t in turns)):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
