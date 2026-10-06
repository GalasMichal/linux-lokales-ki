#!/usr/bin/env python3
"""Knowledge Base v2 E2E: retrieval suite + FAST/QUALITY Qwen sessions."""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

PROJECT = Path("/home/mike/Projects/Linux Lokales KI")
sys.path.insert(0, str(PROJECT / "apps" / "local-tools"))
sys.path.insert(0, str(PROJECT / "benchmarks"))

from knowledge import bootstrap_knowledge, knowledge_search  # noqa: E402
from quality_cutover_e2e import (  # noqa: E402
    EventCollector,
    http_json,
    nvidia,
    ollama_ps,
    sse_loop,
    wait_for_turn,
)

OUT = PROJECT / "benchmarks" / "knowledge-base-20260922"
WORKSPACE = "/srv/ai/workspaces"


def mcp_health() -> dict:
    with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5) as resp:
        return json.loads(resp.read().decode())


def mcp_tool_calls(session_id: str) -> list[str]:
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
                names.append(str(args.get("name") or ""))
            elif name == "tool_search":
                names.append("tool_search")
            elif name:
                names.append(name)
        event = ((obj.get("systemPayload") or {}).get("uiEvent") or {})
        if event.get("event.name") == "qwen-code.tool_call":
            short = str(event.get("function_name") or "").split("__")[-1]
            if short:
                names.append(short)
    return names


def assistant_text(session_id: str, collector: EventCollector | None = None) -> str:
    chunks: list[str] = []
    if collector is not None:
        chunks.extend(collector.texts)
    path = Path.home() / ".qwen/projects/-srv-ai-workspaces/chats" / f"{session_id}.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            message = obj.get("message") or {}
            if message.get("role") not in {"assistant", "model"}:
                continue
            for part in message.get("parts") or []:
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text)
    return "\n".join(chunks)


def run_qwen(label: str, model_id: str, prompt: str) -> dict:
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    print(f"[{label}] session {sid}", flush=True)
    if created.get("attached"):
        http_json("DELETE", f"/session/{sid}")
        created = http_json("POST", "/session", {"cwd": WORKSPACE})
        sid = created["sessionId"]
        print(f"[{label}] fresh {sid}", flush=True)
    http_json("POST", f"/session/{sid}/model", {"modelId": model_id})
    try:
        http_json(
            "POST",
            f"/session/{sid}/config-option",
            {"configId": "reasoning_effort", "value": "none", "persist": False},
        )
    except Exception as exc:
        print(f"[{label}] effort skip {exc}", flush=True)
    stop = threading.Event()
    collector = EventCollector(sid)
    threading.Thread(target=sse_loop, args=(sid, collector, stop), daemon=True).start()
    time.sleep(0.8)
    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    prompt_error = None
    try:
        print(http_json("POST", f"/session/{sid}/prompt", {"prompt": [{"type": "text", "text": prompt}]}, timeout=30), flush=True)
    except Exception as exc:
        prompt_error = str(exc)
        print(f"[{label}] prompt FAIL {exc}", flush=True)
    final_health = wait_for_turn(sid, collector, t0, since)
    stop.set()
    tools = mcp_tool_calls(sid)
    text = assistant_text(sid, collector)
    return {
        "label": label,
        "session_id": sid,
        "model": model_id,
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "prompt_error": prompt_error,
        "health": final_health,
        "votes": collector.votes,
        "tools": tools,
        "used_knowledge_search": any("knowledge_search" in t for t in tools),
        "used_tool_search": "tool_search" in tools or any(t == "tool_search" for t in tools),
        "assistant_excerpt": text[-3500:],
        "yolo": any("yolo" in str(v.get("optionId") or "").lower() for v in collector.votes),
        "nvidia": nvidia(),
        "ollama_ps": ollama_ps(),
    }


def retrieval_suite() -> dict:
    boot = bootstrap_knowledge(str(PROJECT))
    cases = [
        ("lazy", "Warum sind die MCP-Schemas lazy?", ["17216", "lazy"]),
        ("ledger", "Was hat die doppelten PDF-Tool-Calls nach Compact gelöst?", ["ledger", "pdf_create"]),
        ("1536", "Warum starten wir noch kein 1536?", ["1536", "roadmap", "replan", "supervisor"]),
        ("systemd", "Was ist beim systemd Startproblem passiert?", ["systemd", "cycle", "boot"]),
        (
            "prevention",
            "Der Compact dupliziert pdf_create. Wie soll ich es reparieren?",
            ["prompt-only", "ledger", "do_not_repeat"],
        ),
        ("nohit", "quantum banana renderer", []),
    ]
    results = []
    tokens = []
    for name, query, needles in cases:
        hit = knowledge_search(str(PROJECT), query)
        package = hit["package"].lower()
        blob = json.dumps(hit, ensure_ascii=False).lower()
        approx = hit["stats"]["approx_tokens"]
        tokens.append(approx)
        if name == "nohit":
            ok = hit["hits"] == [] and "no relevant knowledge" in package
        elif name == "prevention":
            ok = bool(hit["hits"]) and ("prompt-only" in package or "insufficient" in package) and (
                "ledger" in package or "lazy" in package
            )
        else:
            ok = bool(hit["hits"]) and any(n.lower() in package or n.lower() in blob for n in needles)
        results.append(
            {
                "name": name,
                "ok": ok,
                "approx_tokens": approx,
                "hits": [h["id"] for h in hit["hits"]],
                "package_chars": hit["stats"]["package_chars"],
            }
        )
    return {
        "seeded_or_existing": boot,
        "cases": results,
        "avg_tokens": round(sum(tokens) / max(1, len(tokens)), 1),
        "max_tokens": max(tokens) if tokens else 0,
        "pass": all(item["ok"] for item in results) and max(tokens or [0]) <= 1500,
    }


def score_fast(report: dict) -> bool:
    text = report.get("assistant_excerpt", "").lower()
    return bool(
        not report.get("prompt_error")
        and report.get("used_knowledge_search")
        and ("ledger" in text or "lazy" in text or "17216" in text or "prompt" in text or "compact" in text)
        and not report.get("yolo")
        and "run_shell_command" not in report.get("tools", [])
    )


def score_quality(report: dict) -> bool:
    text = report.get("assistant_excerpt", "").lower()
    bad = (
        ("prompt erneut patchen" in text and "nicht" not in text and "nein" not in text)
        or ("prompt-patch install" in text and "nicht" not in text)
    )
    return bool(
        not report.get("prompt_error")
        and report.get("used_knowledge_search")
        and ("prompt-only" in text or "insufficient" in text or "nicht" in text or "stock" in text)
        and ("ledger" in text or "state ledger" in text or "tool_continuity" in text or "determin" in text)
        and not bad
        and not report.get("yolo")
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    health = mcp_health()
    retrieval = retrieval_suite()
    (OUT / "retrieval.json").write_text(json.dumps(retrieval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"retrieval_pass": retrieval["pass"], "avg": retrieval["avg_tokens"], "max": retrieval["max_tokens"]}, indent=2), flush=True)

    fast_prompt = f"""Workspace: {PROJECT}

Aufgabe: Wir haben wieder doppelte PDF-Tool-Calls nach Compact.
1) tool_search query="select:knowledge_search"
2) knowledge_search workspace="{PROJECT}" query="compact duplicate pdf_create ledger"
3) Antworte kurz mit bekannten Ursachen und Fixes aus dem package.

Keine Shell. Kein pdf_create. Kein memory_update. Keine Dateiänderungen.
"""
    quality_prompt = f"""Workspace: {PROJECT}

Aufgabe: Sollen wir den Compact-Prompt erneut patchen?
1) tool_search query="select:knowledge_search"
2) knowledge_search workspace="{PROJECT}" query="compact prompt-only continuity ledger"
3) Begründe nur mit dem Knowledge-package: Prompt-only war insufficient; State Ledger PASS; Stock-Prompt behalten.

Keine Shell. Kein Code ändern. Kein pdf_create.
"""

    # Unload models first for clean runs
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps({"model": "local-fast", "keep_alive": 0, "prompt": ""}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=30,
        ).read()
    except Exception:
        pass

    fast = run_qwen("fast-kb", "local-fast(openai)", fast_prompt)
    fast["pass"] = score_fast(fast)
    (OUT / "fast-e2e.json").write_text(json.dumps(fast, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fast_pass": fast["pass"], "tools": fast["tools"][:20], "elapsed": fast["elapsed_s"]}, indent=2), flush=True)

    try:
        urllib.request.urlopen(
            urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=json.dumps({"model": "local-quality", "keep_alive": 0, "prompt": ""}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=60,
        ).read()
    except Exception:
        pass

    quality = run_qwen("quality-kb", "local-quality(openai)", quality_prompt)
    quality["pass"] = score_quality(quality)
    (OUT / "quality-e2e.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"quality_pass": quality["pass"], "tools": quality["tools"][:20], "elapsed": quality["elapsed_s"]},
            indent=2,
        ),
        flush=True,
    )

    summary = {
        "health": {"version": health.get("version"), "tools": len(health.get("tools") or [])},
        "retrieval_pass": retrieval["pass"],
        "retrieval_avg_tokens": retrieval["avg_tokens"],
        "retrieval_max_tokens": retrieval["max_tokens"],
        "fast_pass": fast.get("pass"),
        "quality_pass": quality.get("pass"),
        "fast_session": fast.get("session_id"),
        "quality_session": quality.get("session_id"),
        "pass": bool(
            health.get("version") == "1.6.0"
            and len(health.get("tools") or []) == 32
            and retrieval["pass"]
            and fast.get("pass")
            and quality.get("pass")
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
