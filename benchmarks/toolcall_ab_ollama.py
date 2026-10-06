#!/usr/bin/env python3
"""A/B matrix: Ollama native vs OpenAI vs think on/off for FAST and QUALITY."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
PROMPT = "Use memory_load and report the current project state."
WS = "/home/mike/Projects/Linux Lokales KI"
OUT = Path(WS) / "benchmarks" / "toolcall-debug-20260915"
OUT.mkdir(parents=True, exist_ok=True)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "memory_load",
            "description": "Load compact .agent project memory.",
            "parameters": {
                "type": "object",
                "properties": {"workspace": {"type": "string"}},
                "required": ["workspace"],
            },
        },
    }
]


def post(url: str, payload: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    data["_elapsed_s"] = round(time.perf_counter() - t0, 3)
    return data


def summarize_chat(data: dict, think) -> dict:
    msg = data.get("message") or {}
    return {
        "content_head": (msg.get("content") or "")[:240],
        "tool_calls": msg.get("tool_calls"),
        "thinking_head": str(msg.get("thinking") or "")[:200],
        "eval_count": data.get("eval_count"),
        "prompt_eval_count": data.get("prompt_eval_count"),
        "elapsed_s": data["_elapsed_s"],
        "think_arg": think,
        "has_tool_call": bool(msg.get("tool_calls")),
        "memory_load_called": any(
            ((c.get("function") or {}).get("name") == "memory_load")
            for c in (msg.get("tool_calls") or [])
        ),
    }


def summarize_openai(data: dict, think) -> dict:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    return {
        "content_head": (msg.get("content") or "")[:240],
        "tool_calls": msg.get("tool_calls"),
        "reasoning_head": str(msg.get("reasoning") or msg.get("reasoning_content") or "")[:200],
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "elapsed_s": data["_elapsed_s"],
        "think_arg": think,
        "has_tool_call": bool(msg.get("tool_calls")),
        "memory_load_called": any(
            ((c.get("function") or {}).get("name") == "memory_load")
            for c in (msg.get("tool_calls") or [])
        ),
        "wire_keys": sorted(k for k in data.keys() if k != "choices"),
    }


def run_api_chat(model: str, think) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "tools": TOOLS,
        "stream": False,
        "options": {"num_predict": 120, "temperature": 0},
    }
    if think is not None:
        payload["think"] = think
    data = post(f"{OLLAMA}/api/chat", payload)
    return summarize_chat(data, think)


def run_v1(model: str, extra: dict) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "tools": TOOLS,
        "stream": False,
        "temperature": 0,
        "max_tokens": 120,
        **extra,
    }
    data = post(f"{OLLAMA}/v1/chat/completions", payload)
    out = summarize_openai(data, extra)
    out["sent_keys"] = sorted(extra.keys())
    return out


def main() -> None:
    rows = []
    for model in ("local-quality", "local-fast"):
        for think in (False, True, None):
            label = f"A_{model}_think={think}"
            print("RUN", label, flush=True)
            try:
                row = {"id": label, "path": "/api/chat", "model": model, **run_api_chat(model, think)}
            except Exception as exc:
                row = {"id": label, "path": "/api/chat", "model": model, "error": str(exc)}
            rows.append(row)
            print(" ->", {k: row.get(k) for k in ("has_tool_call", "memory_load_called", "elapsed_s", "eval_count", "error")}, flush=True)
        variants = [
            ("think_false", {"think": False}),
            ("think_true", {"think": True}),
            ("enable_thinking_false", {"enable_thinking": False}),
            ("reasoning_effort_none", {"reasoning_effort": "none"}),
            ("chat_template_kwargs", {"chat_template_kwargs": {"enable_thinking": False}}),
            ("bare", {}),
        ]
        for name, extra in variants:
            label = f"B_{model}_{name}"
            print("RUN", label, flush=True)
            try:
                row = {"id": label, "path": "/v1/chat/completions", "model": model, **run_v1(model, extra)}
            except Exception as exc:
                row = {"id": label, "path": "/v1/chat/completions", "model": model, "error": str(exc)}
            rows.append(row)
            print(" ->", {k: row.get(k) for k in ("has_tool_call", "memory_load_called", "elapsed_s", "completion_tokens", "error")}, flush=True)
    (OUT / "ab-ollama.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT / "ab-ollama.json")


if __name__ == "__main__":
    main()
