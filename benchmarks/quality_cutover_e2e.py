#!/usr/bin/env python3
"""Interactive Qwen-serve Memory+PDF E2E for local-quality.

Uses the same HTTP bridge as KI-Arbeitsplatz (127.0.0.1:4170).
approvalMode stays default. trust stays false. Votes Allow-once only.
Not `qwen -p`. Not YOLO.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:4170"
WORKSPACE = "/srv/ai/workspaces"
PROJECT = "/home/mike/Projects/Linux Lokales KI"
MODEL_ID = "local-quality(openai)"
OUT = Path(PROJECT) / "benchmarks" / "quality-cutover-20260915"
OUT.mkdir(parents=True, exist_ok=True)
PDF = f"{PROJECT}/.agent/tmp/quality-cutover-e2e.pdf"
PNG = f"{PROJECT}/.agent/tmp/quality-cutover-e2e.png"

PROMPT = f"""Call mcp__local-tools__memory_load now with workspace="{PROJECT}". Then in order: pdf_create output="{PDF}" title="QUALITY Cutover E2E" text="Qwen3.8 27B QUALITY 8192. FAST stays local-fast."; pdf_read that PDF; pdf_render page 1 to "{PNG}"; memory_update workspace="{PROJECT}" with a short STATE/TASKS refresh and one DECISIONS append. Real MCP calls only. Wait for permission. No YOLO. No /tmp.
"""


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    last_err: Exception | None = None
    for attempt in range(8):
        req = urllib.request.Request(
            BASE + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if exc.code == 429:
                # Serve rate-limits status polls under load; back off and retry.
                retry_ms = 200
                try:
                    parsed = json.loads(body)
                    retry_ms = int(parsed.get("retryAfterMs") or retry_ms)
                except Exception:
                    pass
                time.sleep(max(0.05, retry_ms / 1000.0) + 0.05 * attempt)
                last_err = RuntimeError(f"{method} {path} -> {exc.code} {body[:2000]}")
                continue
            raise RuntimeError(f"{method} {path} -> {exc.code} {body[:2000]}") from exc
    raise last_err or RuntimeError(f"{method} {path} -> rate_limit retries exhausted")


def nvidia() -> dict:
    import subprocess

    raw = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    used, total, util = [x.strip() for x in raw.split(",")]
    return {"vram_used_mib": int(used), "vram_total_mib": int(total), "gpu_util": int(util)}


def ollama_ps() -> str:
    import subprocess

    return subprocess.check_output(["ollama", "ps"], text=True)


def pick_allow(options: list) -> str | None:
    ids = []
    for opt in options or []:
        if isinstance(opt, dict) and opt.get("optionId"):
            ids.append(str(opt["optionId"]))
    for preferred in ("proceed_once", "allow_once", "allow-once", "allow"):
        if preferred in ids:
            return preferred
    for oid in ids:
        low = oid.lower()
        if "always" in low or "forever" in low:
            continue
        if "allow" in low or low.endswith("_once") or low == "proceed_once":
            return oid
    return ids[0] if ids else None


class EventCollector:
    def __init__(self, session_id: str = "") -> None:
        self.session_id = session_id
        self.events: list[dict] = []
        self.permissions: list[dict] = []
        self.votes: list[dict] = []
        self.tools: list[dict] = []
        self.texts: list[str] = []
        self.thoughts = 0
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.error: str | None = None

    def handle(self, event_type: str, payload: dict) -> None:
        with self.lock:
            self.events.append({"type": event_type, "payload": payload})
        if event_type not in {"session_update", "message"}:
            print(f"[sse] {event_type}", flush=True)
        inner = payload.get("data") if isinstance(payload, dict) else None
        data = inner if isinstance(inner, dict) else payload
        if event_type == "permission_request" or (isinstance(payload, dict) and payload.get("type") == "permission_request"):
            req = data if "requestId" in data else (data.get("data") if isinstance(data.get("data"), dict) else data)
            self.permissions.append(req)
            options = req.get("options") or []
            oid = pick_allow(options)
            request_id = req.get("requestId")
            session_id = req.get("sessionId") or self.session_id
            vote = {"requestId": request_id, "optionId": oid, "ok": False}
            if request_id and oid:
                body = {"outcome": {"outcome": "selected", "optionId": oid}}
                try:
                    if session_id:
                        http_json("POST", f"/session/{session_id}/permission/{request_id}", body, timeout=20)
                    else:
                        http_json("POST", f"/permission/{request_id}", body, timeout=20)
                    vote["ok"] = True
                    print(f"[vote] {request_id} -> {oid} ok", flush=True)
                except Exception as exc:
                    vote["error"] = str(exc)
                    print(f"[vote] {request_id} FAIL {exc}", flush=True)
            with self.lock:
                self.votes.append(vote)
            return
        update = None
        if isinstance(data, dict):
            update = data.get("update") or data.get("data") or data
        session_update = update.get("sessionUpdate") if isinstance(update, dict) else None
        if session_update in {"tool_call", "tool_call_update"}:
            item = {
                "id": update.get("toolCallId"),
                "name": update.get("name") or update.get("title"),
                "status": update.get("status"),
                "title": update.get("title"),
                "rawInput": update.get("rawInput") or update.get("input"),
                "content": update.get("content") or update.get("rawOutput"),
            }
            with self.lock:
                merged = False
                if item["id"]:
                    for existing in self.tools:
                        if existing.get("id") == item["id"]:
                            for key, value in item.items():
                                if value not in (None, "", [], {}):
                                    existing[key] = value
                            merged = True
                            item = existing
                            break
                if not merged:
                    self.tools.append(item)
            print(
                f"[tool] {item.get('status')} {item.get('name') or item.get('title')}",
                flush=True,
            )
        if isinstance(update, dict) and update.get("sessionUpdate") == "agent_thought_chunk":
            with self.lock:
                self.thoughts += 1
        if isinstance(update, dict) and update.get("sessionUpdate") == "agent_message_chunk":
            content = update.get("content") or {}
            text = content.get("text") if isinstance(content, dict) else None
            if text:
                with self.lock:
                    self.texts.append(text)


def sse_loop(session_id: str, collector: EventCollector, stop: threading.Event) -> None:
    req = urllib.request.Request(
        f"{BASE}/session/{session_id}/events",
        headers={"Accept": "text/event-stream", "Last-Event-ID": "0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=1200) as resp:
            event_type = "message"
            buf = []
            while not stop.is_set():
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                if text.startswith("event:"):
                    event_type = text.split(":", 1)[1].strip()
                elif text.startswith("data:"):
                    buf.append(text.split(":", 1)[1].strip())
                elif text.strip() == "":
                    if buf:
                        raw = "\n".join(buf)
                        buf = []
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            payload = {"raw": raw}
                        collector.handle(event_type, payload)
                    event_type = "message"
    except Exception as exc:
        collector.error = str(exc)
    finally:
        collector.done.set()


def ollama_ngen(since: str) -> int | None:
    import subprocess

    raw = subprocess.check_output(
        ["journalctl", "-u", "ollama.service", "--since", since, "--no-pager", "-o", "cat"],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    n_gen = None
    saw_new_post = False
    for line in raw.splitlines():
        if "POST     \"/v1/chat/completions\"" in line or "POST     \"/api/chat\"" in line:
            saw_new_post = True
            n_gen = 0
        if "n_gen =" in line:
            try:
                n_gen = int(line.split("n_gen =", 1)[1].split(",", 1)[0].strip())
            except ValueError:
                continue
    if not saw_new_post and n_gen is None:
        return None
    return n_gen


def health_snapshot(session_id: str, collector: EventCollector, since: str) -> dict:
    status = http_json("GET", f"/session/{session_id}/status")
    gpu = nvidia()
    return {
        "active": status.get("hasActivePrompt"),
        "wait_perm": status.get("isWaitingForPermission"),
        "pending": status.get("pendingInteractionCount"),
        "votes": len(collector.votes),
        "tools": len(collector.tools),
        "thoughts": collector.thoughts,
        "n_gen": ollama_ngen(since),
        "gpu_util": gpu["gpu_util"],
        "vram": gpu["vram_used_mib"],
    }


def wait_for_turn(session_id: str, collector: EventCollector, t0: float, since: str) -> dict:
    last_key = None
    abort = None
    next_periodic = 5.0
    deadline = time.time() + 900
    last = {}
    while time.time() < deadline:
        elapsed = round(time.perf_counter() - t0, 1)
        snap = health_snapshot(session_id, collector, since)
        last = snap
        if snap["wait_perm"]:
            try:
                status = http_json("GET", f"/session/{session_id}/status")
            except Exception:
                status = {}
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
                        timeout=20,
                    )
                    print(f"[vote-poll] {request_id} -> {oid}", flush=True)
                    with collector.lock:
                        collector.votes.append({"requestId": request_id, "optionId": oid, "ok": True, "via": "poll"})
                except Exception as exc:
                    print(f"[vote-poll] fail {exc}", flush=True)
        key = (
            snap["active"],
            snap["wait_perm"],
            snap["votes"],
            snap["tools"],
            snap["thoughts"],
            snap["n_gen"],
            snap["gpu_util"] > 10,
        )
        if elapsed >= next_periodic:
            if key != last_key or next_periodic == 5.0:
                print(
                    f"[health {elapsed}s] active={snap['active']} tools={snap['tools']} "
                    f"votes={snap['votes']} thoughts={snap['thoughts']} n_gen={snap['n_gen']} "
                    f"gpu={snap['gpu_util']}% vram={snap['vram']} wait_perm={snap['wait_perm']}",
                    flush=True,
                )
                last_key = key
            if next_periodic < 20:
                next_periodic += 7
            else:
                next_periodic += 20
        n_gen = snap["n_gen"] or 0
        vram = snap["vram"] or 0
        # 27B 64K/80K cold load often exceeds 45s with n_gen still 0 and VRAM < 4G.
        # Abort only after a long idle-and-unloaded window, not mid-load.
        if (
            elapsed >= 150
            and snap["active"]
            and n_gen == 0
            and snap["gpu_util"] < 5
            and snap["tools"] == 0
            and vram < 4000
        ):
            abort = f"kein Ollama-Fortschritt nach {elapsed}s"
            break
        if elapsed >= 180 and snap["tools"] == 0 and snap["votes"] == 0:
            abort = f"180s ohne Tool-Call (n_gen={n_gen} thoughts={snap['thoughts']})"
            break
        if n_gen >= 2500 and snap["tools"] == 0:
            abort = f"Thinking-Lauf ohne Tools (n_gen={n_gen})"
            break
        if not snap["active"] and elapsed > 8:
            time.sleep(1)
            snap = health_snapshot(session_id, collector, since)
            last = snap
            if not snap["active"]:
                print(
                    f"[health {round(time.perf_counter()-t0,1)}s] idle tools={snap['tools']} votes={snap['votes']}",
                    flush=True,
                )
                break
        time.sleep(3)
    if abort:
        print(f"[abort] {abort}", flush=True)
        try:
            http_json("POST", f"/session/{session_id}/cancel", {})
        except Exception as exc:
            print(f"[cancel] {exc}", flush=True)
    return last


def main() -> None:
    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    mcp = http_json("GET", "/workspace/mcp")
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    session_id = created["sessionId"]
    print(f"[session] {session_id} attached={created.get('attached')}", flush=True)
    model = http_json("POST", f"/session/{session_id}/model", {"modelId": MODEL_ID})
    print(f"[model] {model}", flush=True)
    try:
        effort = http_json(
            "POST",
            f"/session/{session_id}/config-option",
            {"configId": "reasoning_effort", "value": "none", "persist": False},
        )
        print(f"[effort] {effort}", flush=True)
    except Exception as exc:
        print(f"[effort] skip {exc}", flush=True)
    stop = threading.Event()
    collector = EventCollector(session_id)
    thread = threading.Thread(target=sse_loop, args=(session_id, collector, stop), daemon=True)
    thread.start()
    time.sleep(0.8)
    prompt_error = None
    prompt_result = None
    try:
        prompt_result = http_json(
            "POST",
            f"/session/{session_id}/prompt",
            {"prompt": [{"type": "text", "text": PROMPT}]},
            timeout=30,
        )
        print(f"[prompt] {prompt_result}", flush=True)
    except Exception as exc:
        prompt_error = str(exc)
        print(f"[prompt] FAIL {exc}", flush=True)
    print("[health] erste Prüfung in 5s", flush=True)
    final_health = wait_for_turn(session_id, collector, t0, since)
    context = {}
    status = {}
    try:
        context = http_json("GET", f"/session/{session_id}/context")
    except Exception as exc:
        context = {"error": str(exc)}
    try:
        status = http_json("GET", f"/session/{session_id}/status")
    except Exception as exc:
        status = {"error": str(exc)}
    status["health"] = final_health
    stop.set()
    thread.join(timeout=5)
    elapsed = round(time.perf_counter() - t0, 3)
    tools_compact = []
    seen = []
    for item in collector.tools:
        key = (item.get("id"), item.get("status"))
        if key in seen:
            continue
        seen.append(key)
        tools_compact.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "title": item.get("title"),
                "status": item.get("status"),
                "input": item.get("rawInput"),
            }
        )
    result = {
        "sessionId": session_id,
        "attached": created.get("attached"),
        "model_switch": model,
        "mcp_status": {
            "initialized": mcp.get("initialized"),
            "servers": [
                {
                    "name": s.get("name"),
                    "status": s.get("status"),
                    "trust": s.get("trust"),
                }
                for s in (mcp.get("servers") or mcp.get("mcpServers") or [])
                if isinstance(s, dict)
            ],
        },
        "prompt_result": prompt_result,
        "prompt_error": prompt_error,
        "elapsed_s": elapsed,
        "votes": collector.votes,
        "permissions": [
            {
                "requestId": p.get("requestId"),
                "tool": (p.get("toolCall") or {}).get("name") if isinstance(p.get("toolCall"), dict) else p.get("toolCall"),
                "options": [o.get("optionId") for o in (p.get("options") or []) if isinstance(o, dict)],
            }
            for p in collector.permissions
        ],
        "tools": tools_compact,
        "assistant_text": "".join(collector.texts),
        "sse_error": collector.error,
        "context": context,
        "status": status,
        "nvidia": nvidia(),
        "ollama_ps": ollama_ps(),
        "event_count": len(collector.events),
    }
    (OUT / "e2e.json").write_text(json.dumps(result, indent=2, ensure_ascii=False)[:2_000_000], encoding="utf-8")
    (OUT / "e2e-events.json").write_text(
        json.dumps(collector.events[:400], indent=2, ensure_ascii=False)[:2_000_000],
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "sessionId": session_id,
            "elapsed_s": elapsed,
            "prompt_error": prompt_error,
            "stopReason": (prompt_result or {}).get("stopReason"),
            "votes": result["votes"],
            "tools": tools_compact,
            "assistant_tail": result["assistant_text"][-1500:],
            "nvidia": result["nvidia"],
            "ollama_ps": result["ollama_ps"],
        },
        indent=2,
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
