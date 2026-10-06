#!/usr/bin/env python3
"""Replay a captured Qwen-Serve /v1 request against Ollama with thinking/prompt variants."""

from __future__ import annotations

import json
import time
import urllib.request
from copy import deepcopy
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
WS = Path("/home/mike/Projects/Linux Lokales KI")
CAPTURE = WS / "benchmarks/toolcall-debug-20260915/captured-serve-request.json"
OUT = WS / "benchmarks/toolcall-debug-20260915/replay-matrix.json"
USER = "Use memory_load and report the current project state."
MIN_SYS = "You are a local coding assistant. Use tools when asked. Do not invent tool results."


def post(url: str, payload: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
    elapsed = round(time.perf_counter() - t0, 3)
    data = json.loads(raw)
    data["_elapsed_s"] = elapsed
    return data


def summarize_openai(data: dict) -> dict:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    tcs = msg.get("tool_calls") or []
    names = []
    for tc in tcs:
        fn = tc.get("function") if isinstance(tc, dict) else {}
        names.append((fn or {}).get("name") or tc.get("name"))
    return {
        "elapsed_s": data.get("_elapsed_s"),
        "finish_reason": choice.get("finish_reason"),
        "has_tool_call": bool(tcs),
        "tool_names": names,
        "memory_load_called": any(
            n and "memory_load" in str(n) for n in names
        ),
        "content_head": (msg.get("content") or "")[:280],
        "reasoning_head": str(
            msg.get("reasoning") or msg.get("reasoning_content") or ""
        )[:160],
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "error": data.get("error"),
    }


def summarize_chat(data: dict) -> dict:
    msg = data.get("message") or {}
    tcs = msg.get("tool_calls") or []
    names = [
        ((c.get("function") or {}).get("name") if isinstance(c, dict) else None)
        for c in tcs
    ]
    return {
        "elapsed_s": data.get("_elapsed_s"),
        "has_tool_call": bool(tcs),
        "tool_names": names,
        "memory_load_called": any(
            n and "memory_load" in str(n) for n in names
        ),
        "content_head": (msg.get("content") or "")[:280],
        "thinking_head": str(msg.get("thinking") or "")[:160],
        "prompt_eval_count": data.get("prompt_eval_count"),
        "eval_count": data.get("eval_count"),
    }


def only_memory_tools(tools: list) -> list:
    kept = []
    for t in tools:
        fn = t.get("function") if isinstance(t, dict) else t
        name = str((fn or {}).get("name") or t.get("name") or "")
        if "memory_load" in name:
            kept.append(t)
    return kept


def run_v1(name: str, body: dict) -> dict:
    payload = deepcopy(body)
    payload["stream"] = False
    payload.pop("stream_options", None)
    print(f"RUN {name} tools={len(payload.get('tools') or [])} model={payload.get('model')}", flush=True)
    try:
        data = post(f"{OLLAMA}/v1/chat/completions", payload)
        summary = summarize_openai(data)
    except Exception as exc:
        summary = {"error": str(exc)[:400]}
    summary["variant"] = name
    summary["model"] = payload.get("model")
    summary["tool_count"] = len(payload.get("tools") or [])
    summary["think"] = payload.get("think")
    summary["enable_thinking"] = payload.get("enable_thinking")
    summary["reasoning_effort"] = payload.get("reasoning_effort")
    summary["tool_choice"] = payload.get("tool_choice")
    print(
        f"  -> tools={summary.get('tool_names')} mem={summary.get('memory_load_called')} "
        f"tok={summary.get('prompt_tokens')}/{summary.get('completion_tokens')} "
        f"{summary.get('elapsed_s')}s err={summary.get('error')}",
        flush=True,
    )
    return summary


def run_chat(name: str, model: str, messages: list, tools: list, think) -> dict:
    ollama_tools = []
    for t in tools:
        fn = t.get("function") if isinstance(t, dict) else t
        ollama_tools.append(
            {
                "type": "function",
                "function": {
                    "name": (fn or {}).get("name"),
                    "description": (fn or {}).get("description"),
                    "parameters": (fn or {}).get("parameters") or {},
                },
            }
        )
    payload = {
        "model": model,
        "messages": messages,
        "tools": ollama_tools,
        "stream": False,
        "think": think,
    }
    print(f"RUN {name} think={think} tools={len(ollama_tools)}", flush=True)
    try:
        data = post(f"{OLLAMA}/api/chat", payload)
        summary = summarize_chat(data)
    except Exception as exc:
        summary = {"error": str(exc)[:400]}
    summary["variant"] = name
    summary["model"] = model
    summary["think"] = think
    summary["tool_count"] = len(ollama_tools)
    print(
        f"  -> tools={summary.get('tool_names')} mem={summary.get('memory_load_called')} "
        f"tok={summary.get('prompt_eval_count')}/{summary.get('eval_count')} "
        f"{summary.get('elapsed_s')}s err={summary.get('error')}",
        flush=True,
    )
    return summary


def main() -> None:
    captured = json.loads(CAPTURE.read_text())
    tools = captured.get("tools") or []
    msgs = captured.get("messages") or []
    mem_tools = only_memory_tools(tools)
    min_msgs = [
        {"role": "system", "content": MIN_SYS},
        {"role": "user", "content": USER},
    ]
    exact_msgs = [
        {"role": "system", "content": MIN_SYS},
        {
            "role": "user",
            "content": "Call mcp__local-tools__memory_load now and report the current project state.",
        },
    ]
    short_name_msgs = [
        {"role": "system", "content": MIN_SYS},
        {
            "role": "user",
            "content": "Call memory_load now and report the current project state.",
        },
    ]

    results = []

    as_is = deepcopy(captured)
    results.append(run_v1("D_serve_as_is", as_is))

    v_on = deepcopy(captured)
    for k in ("think", "enable_thinking", "reasoning_effort"):
        v_on.pop(k, None)
    results.append(run_v1("think_default_omit_flags", v_on))

    v_true = deepcopy(captured)
    v_true["think"] = True
    v_true["enable_thinking"] = True
    v_true.pop("reasoning_effort", None)
    results.append(run_v1("think_explicit_on", v_true))

    v_re = deepcopy(captured)
    v_re.pop("think", None)
    v_re.pop("enable_thinking", None)
    v_re["reasoning_effort"] = "none"
    results.append(run_v1("reasoning_effort_none_only", v_re))

    v_mem = deepcopy(captured)
    v_mem["tools"] = mem_tools
    results.append(run_v1("full_prompt_only_memory_load", v_mem))

    v_min_all = deepcopy(captured)
    v_min_all["messages"] = min_msgs
    results.append(run_v1("min_prompt_all_tools", v_min_all))

    v_min_mem = deepcopy(captured)
    v_min_mem["messages"] = min_msgs
    v_min_mem["tools"] = mem_tools
    results.append(run_v1("min_prompt_only_memory_load", v_min_mem))

    v_exact = deepcopy(captured)
    v_exact["messages"] = exact_msgs
    results.append(run_v1("min_prompt_exact_mcp_name", v_exact))

    v_short = deepcopy(captured)
    v_short["messages"] = short_name_msgs
    results.append(run_v1("min_prompt_short_name", v_short))

    v_req = deepcopy(captured)
    v_req["tool_choice"] = "required"
    results.append(run_v1("full_prompt_tool_choice_required", v_req))

    results.append(
        run_chat("A_api_chat_think_false_full", "local-quality", msgs, tools, False)
    )
    results.append(
        run_chat("A_api_chat_think_true_full", "local-quality", msgs, tools, True)
    )
    results.append(
        run_chat("A_api_chat_think_false_min_mem", "local-quality", min_msgs, mem_tools, False)
    )

    v_fast = deepcopy(captured)
    v_fast["model"] = "local-fast"
    results.append(run_v1("FAST_serve_shape", v_fast))

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
