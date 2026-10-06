#!/usr/bin/env python3
"""Controlled local Fable/agent benchmark. Does not replace existing aliases."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from mcp import Client


REPO = Path("/home/mike/Projects/Linux Lokales KI")
BENCH_WS = Path("/srv/ai/workspaces/fable-bench-20260915")
OUT_DIR = REPO / "benchmarks" / "fable-agent-20260915"
MCP_URL = "http://127.0.0.1:8765/mcp"
OLLAMA = "http://127.0.0.1:11434"
CODING_FILES = (
    REPO / "apps" / "local-tools" / "errors.py",
    REPO / "tests" / "test_tool_error.py",
)
ERRORS_PY = CODING_FILES[0]
TEST_PY = CODING_FILES[1]
BASELINE_ERRORS = ERRORS_PY.read_text(encoding="utf-8")

MODELS = [
    {"id": "local-fast", "role": "FAST", "ctx": 32768},
    {"id": "local-quality", "role": "QUALITY-REF", "ctx": 8192},
    {"id": "bench-qwen38-27b-8k", "role": "CANDIDATE-38", "ctx": 8192},
    {"id": "bench-qwen36-coding-8k", "role": "CANDIDATE-CODING", "ctx": 8192},
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "memory_load",
            "description": "Load persistent .agent/ memory files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "string",
                        "description": "Comma-separated names e.g. STATE.md,REQUIREMENTS.md,DECISIONS.md",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_update",
            "description": "Update compact memory. DECISIONS.md is append-only; never invent old decisions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "state": {"type": "string"},
                    "tasks": {"type": "string"},
                    "decisions": {"type": "string"},
                    "decision_title": {"type": "string"},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_create",
            "description": "Create a local PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "output": {"type": "string"},
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["output", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_read",
            "description": "Read text from a local PDF.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_render",
            "description": "Render a PDF page to PNG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "output": {"type": "string"},
                    "page": {"type": "integer"},
                },
                "required": ["path", "output"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 file from the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a UTF-8 file. Only errors.py and tests/test_tool_error.py are allowed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "contents": {"type": "string"},
                },
                "required": ["path", "contents"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run unittest for tests/test_tool_error.py",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def nvidia() -> dict:
    out = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    used, total, util = [x.strip() for x in out.split(",")]
    return {"vram_mib": int(used), "vram_total_mib": int(total), "gpu_util": int(util)}


def ollama_ps() -> str:
    return subprocess.check_output(["ollama", "ps"], text=True)


def chat(model: str, messages: list, num_predict: int = 400) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "think": False,
        "options": {"num_predict": num_predict, "temperature": 0.2},
    }
    t0 = time.perf_counter()
    req = urllib.request.Request(
        f"{OLLAMA}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    data["_wall_s"] = round(time.perf_counter() - t0, 3)
    data["_nvidia"] = nvidia()
    return data


def _allowed_write(path: str) -> Path:
    target = (REPO / path).resolve() if not path.startswith("/") else Path(path).resolve()
    allowed = {p.resolve() for p in CODING_FILES}
    if target not in allowed:
        raise PermissionError(f"write_file blocked: {target}")
    return target


async def run_tool(name: str, args: dict) -> dict:
    ws = str(BENCH_WS)
    if name == "read_file":
        raw = args.get("path") or ""
        path = Path(raw)
        if not path.is_absolute():
            path = REPO / raw
        path = path.resolve()
        if REPO not in path.parents and path != REPO:
            return {"ok": False, "error": "path outside repo"}
        text = path.read_text(encoding="utf-8")
        limit = int(args.get("limit") or 4000)
        return {"ok": True, "path": str(path), "text": text[:limit]}
    if name == "write_file":
        target = _allowed_write(args["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args["contents"], encoding="utf-8")
        return {"ok": True, "path": str(target), "bytes": target.stat().st_size}
    if name == "run_tests":
        proc = subprocess.run(
            ["python3", "-m", "unittest", "-q", "tests.test_tool_error"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-2000:],
        }
    async with Client(MCP_URL) as client:
        payload = dict(args)
        payload["workspace"] = ws
        result = await client.call_tool(name, payload)
        if getattr(result, "structured_content", None) is not None:
            return result.structured_content
        return {"raw": str(result)[:4000]}


def reset_coding() -> None:
    """Restore coding-task files. errors.py is untracked, so no git checkout."""
    ERRORS_PY.write_text(BASELINE_ERRORS, encoding="utf-8")
    if TEST_PY.exists():
        TEST_PY.unlink()


def prepare_workspace() -> None:
    BENCH_WS.mkdir(parents=True, exist_ok=True)
    dest = BENCH_WS / ".agent"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(REPO / ".agent", dest, ignore=shutil.ignore_patterns("tmp", "*.png", "*.pdf"))
    (BENCH_WS / ".agent" / "tmp").mkdir(exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)


TASKS = {
    "1_memory": {
        "max_rounds": 3,
        "prompt": (
            "You are a local coding agent. Workspace memory is in .agent/ via tools. "
            "1) Call memory_load with files STATE.md,REQUIREMENTS.md,DECISIONS.md. "
            "2) Summarize current requirements in 5 bullets. "
            "3) List existing decisions without inventing any. "
            "Do not call other tools."
        ),
    },
    "2_pdf": {
        "max_rounds": 6,
        "prompt": (
            "Use tools, do not only describe them. "
            "1) memory_load files REQUIREMENTS.md. "
            "2) pdf_create output .agent/tmp/bench-report.pdf title 'Fable bench' "
            "text 'Local stack: Ollama localhost, MCP local-tools, no YOLO, trust false.'. "
            "3) pdf_read that PDF. "
            "4) pdf_render it to .agent/tmp/bench-report.png. "
            "5) If QA failed, fix with another pdf_create. "
            "6) memory_update summary 'PDF smoke from fable bench' and a short state note. "
            "Stop after tools succeed."
        ),
    },
    "3_coding": {
        "max_rounds": 7,
        "prompt": (
            "Real coding task in this repo. Respect existing architecture. "
            "File apps/local-tools/errors.py currently has class ToolError(RuntimeError) only. "
            "Change: ToolError.__init__(self, message: str, code: str | None = None) stores self.code. "
            "Do not change gateway.py. "
            "Add tests/test_tool_error.py with unittest: default code is None, custom code is kept, str(err) is the message. "
            "Then call run_tests. "
            "Read the file first, then write_file both files, then run_tests. "
            "If tests fail, fix and re-run once."
        ),
    },
    "4_agent": {
        "max_rounds": 8,
        "prompt": (
            "Multi-step agent cycle. Use tools, do not only mention them. "
            "1) memory_load STATE.md,REQUIREMENTS.md,DECISIONS.md. "
            "2) read_file apps/local-tools/errors.py. "
            "3) Plan in one short paragraph. "
            "4) Same coding change as before: ToolError code parameter + tests/test_tool_error.py + run_tests. "
            "5) pdf_create .agent/tmp/agent-cycle.pdf with a 4-line report of what you did. "
            "6) pdf_read it. "
            "7) memory_update summary of this cycle, no invented historical decisions. "
            "Stop when tests pass and PDF exists."
        ),
    },
}


def metrics_from(resp: dict) -> dict:
    eval_count = resp.get("eval_count") or 0
    eval_ns = resp.get("eval_duration") or 1
    prompt_ns = resp.get("prompt_eval_duration") or 0
    return {
        "prompt_tokens": resp.get("prompt_eval_count"),
        "output_tokens": eval_count,
        "tok_s": round(eval_count / (eval_ns / 1e9), 2) if eval_ns else None,
        "ttft_ms": round(prompt_ns / 1e6, 1) if prompt_ns else None,
        "wall_s": resp.get("_wall_s"),
        "nvidia": resp.get("_nvidia"),
    }


async def run_task(model: str, task_id: str, spec: dict) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a careful local agent. Prefer tools over guesses. "
                "Never invent DECISIONS. Never claim a tool ran unless you called it. "
                "German or English is fine. Keep answers short."
            ),
        },
        {"role": "user", "content": spec["prompt"]},
    ]
    calls: list[dict] = []
    rounds = []
    t0 = time.perf_counter()
    for _ in range(spec["max_rounds"]):
        resp = chat(model, messages)
        msg = resp.get("message") or {}
        rounds.append(
            {
                "metrics": metrics_from(resp),
                "content": (msg.get("content") or "")[:1500],
                "tool_calls": msg.get("tool_calls") or [],
                "ps": ollama_ps(),
            }
        )
        tool_calls = msg.get("tool_calls") or []
        messages.append(msg)
        if not tool_calls:
            break
        for tc in tool_calls:
            fn = (tc.get("function") or {})
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or {}
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {}
            try:
                result = await run_tool(name, raw_args)
                err = False
            except Exception as exc:  # tool isolation
                result = {"ok": False, "error": str(exc)}
                err = True
            calls.append({"name": name, "args": raw_args, "ok": not err and result.get("ok", True), "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(result, ensure_ascii=False)[:6000],
                }
            )
    return {
        "task": task_id,
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "rounds": rounds,
        "tool_calls": calls,
        "tool_success": sum(1 for c in calls if c["ok"]),
        "tool_total": len(calls),
        "final_text": (rounds[-1]["content"] if rounds else ""),
    }


def score_task(task_id: str, result: dict) -> dict:
    names = [c["name"] for c in result["tool_calls"]]
    ok_names = [c["name"] for c in result["tool_calls"] if c["ok"]]
    text = result["final_text"].lower()
    mentioned_only = ("memory_load" in text or "pdf_create" in text) and not result["tool_calls"]

    def has(*want: str) -> bool:
        return all(w in ok_names for w in want)

    scores = {}
    if task_id == "1_memory":
        scores["tools"] = 9 if has("memory_load") else (2 if mentioned_only else 3)
        scores["memory"] = 8 if has("memory_load") else 2
        scores["instruction"] = 7 if has("memory_load") else 3
    elif task_id == "2_pdf":
        scores["tools"] = 9 if has("pdf_create", "pdf_read", "pdf_render") else (5 if "pdf_create" in ok_names else 2)
        scores["pdf"] = scores["tools"]
        scores["memory"] = 8 if "memory_load" in ok_names else 3
        scores["instruction"] = scores["tools"]
    elif task_id == "3_coding":
        test_ok = any(c["name"] == "run_tests" and c["ok"] and (c["result"] or {}).get("ok") for c in result["tool_calls"])
        wrote = "write_file" in ok_names
        read = "read_file" in ok_names
        scores["coding"] = 9 if test_ok else (6 if wrote else (4 if read else 2))
        scores["tools"] = 8 if wrote and read else 4
        scores["instruction"] = scores["coding"]
    else:
        test_ok = any(c["name"] == "run_tests" and (c["result"] or {}).get("ok") for c in result["tool_calls"])
        pdf_ok = "pdf_create" in ok_names
        mem = "memory_load" in ok_names
        scores["planning"] = 8 if mem and (test_ok or pdf_ok) else 4
        scores["tools"] = 8 if mem and pdf_ok else 4
        scores["coding"] = 8 if test_ok else 3
        scores["pdf"] = 8 if pdf_ok else 3
        scores["memory"] = 7 if mem else 3
    return scores


async def main() -> int:
    prepare_workspace()
    report = {
        "started": _now(),
        "models": {},
        "notes": "Agent loop via Ollama /api/chat + live MCP. Qwen trust:false not bypassed.",
    }
    for spec in MODELS:
        model = spec["id"]
        print(f"=== {model} ===", flush=True)
        subprocess.run(["ollama", "stop", model], check=False, capture_output=True)
        reset_coding()
        model_out = {"role": spec["role"], "ctx": spec["ctx"], "tasks": {}}
        for task_id, task in TASKS.items():
            print(f"  task {task_id}", flush=True)
            reset_coding()
            result = await run_task(model, task_id, task)
            result["scores"] = score_task(task_id, result)
            model_out["tasks"][task_id] = result
        model_out["ps_end"] = ollama_ps()
        model_out["nvidia_end"] = nvidia()
        report["models"][model] = model_out
        (OUT_DIR / f"{model.replace(':', '_')}.json").write_text(
            json.dumps(model_out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        reset_coding()
    report["finished"] = _now()
    (OUT_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT_DIR / "report.json")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
