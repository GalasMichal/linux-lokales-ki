#!/usr/bin/env python3
"""Fair 8k vs 16k QUALITY comparison. Does not retarget local-quality/local-fast.

Stops immediately on OOM-like pressure, Ollama crash, or runaway swap.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

REPO = Path("/home/mike/Projects/Linux Lokales KI")
OUT = REPO / "benchmarks" / "ctx16k-20260916"
OUT.mkdir(parents=True, exist_ok=True)
OLLAMA = "http://127.0.0.1:11434"
REF = "local-quality"
CAND = "bench-qwen38-27b-16k"
CAPTURE_DIR = REPO / "benchmarks" / "toolcall-debug-20260915"
TEXT_PROMPT = (
    "Erkläre in genau drei Sätzen, was ein lokaler MCP-Server macht. "
    "Keine Liste, keine Überschrift."
)
TOOL_PROMPT_CANON = (
    'Call ONLY the tool mcp__local-tools__memory_load with '
    'workspace="/home/mike/Projects/Linux Lokales KI". No essay.'
)
TOOL_PROMPT_SHORT = (
    'Call ONLY the tool memory_load with '
    'workspace="/home/mike/Projects/Linux Lokales KI". No essay.'
)
MEMORY_TOOL_CANON = [
    {
        "type": "function",
        "function": {
            "name": "mcp__local-tools__memory_load",
            "description": "Load compact .agent memory files.",
            "parameters": {
                "type": "object",
                "properties": {"workspace": {"type": "string"}},
                "required": ["workspace"],
            },
        },
    }
]
MEMORY_TOOL_SHORT = [
    {
        "type": "function",
        "function": {
            "name": "memory_load",
            "description": "Load compact .agent memory files.",
            "parameters": {
                "type": "object",
                "properties": {"workspace": {"type": "string"}},
                "required": ["workspace"],
            },
        },
    }
]
SAMPLE = {
    "temperature": 1,
    "top_k": 20,
    "top_p": 0.95,
    "min_p": 0,
    "repeat_penalty": 1,
    "presence_penalty": 1.5,
}
ABORT_PATH = OUT / "ABORT.json"
LOG_PATH = OUT / "resource-log.jsonl"


class Abort(RuntimeError):
    pass


def dump_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def nvidia() -> dict:
    raw = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    name, total, used, free, util = [x.strip() for x in raw.split(",", 4)]
    return {
        "name": name,
        "vram_total_mib": int(total),
        "vram_used_mib": int(used),
        "vram_free_mib": int(free),
        "gpu_util": int(util),
    }


def meminfo() -> dict:
    vals = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, rest = line.split(":", 1)
        vals[key] = int(rest.strip().split()[0])
    return {
        "mem_total_mib": vals["MemTotal"] // 1024,
        "mem_available_mib": vals["MemAvailable"] // 1024,
        "mem_used_mib": (vals["MemTotal"] - vals["MemAvailable"]) // 1024,
        "swap_total_mib": vals["SwapTotal"] // 1024,
        "swap_used_mib": (vals["SwapTotal"] - vals["SwapFree"]) // 1024,
    }


def ollama_ps() -> dict:
    text = subprocess.check_output(["ollama", "ps"], text=True)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    row = lines[1] if len(lines) > 1 else ""
    parts = row.split()
    ctx = None
    for token in parts:
        if token.isdigit() and int(token) in {4096, 4098, 8192, 16384, 32768}:
            ctx = int(token)
            break
    processor = ""
    if "CPU/GPU" in row:
        processor = row.split()[-4] if len(parts) >= 4 else row
        for i, p in enumerate(parts):
            if "CPU/GPU" in p or p.endswith("%"):
                processor = " ".join(parts[i : i + 3]) if i + 2 < len(parts) else p
                break
        # Typical: 18 GB    38%/62% CPU/GPU    8192
        joined = row
        if "CPU/GPU" in joined:
            before = joined.split("CPU/GPU")[0].split()
            processor = before[-1] + " CPU/GPU" if before else joined
    return {"raw": text, "loaded": bool(row), "line": row, "context": ctx, "processor": processor}


def ollama_active() -> bool:
    return subprocess.call(["systemctl", "is-active", "--quiet", "ollama.service"]) == 0


def snapshot(tag: str) -> dict:
    snap = {"tag": tag, "ts": time.time(), **nvidia(), **meminfo(), "ps": ollama_ps(), "ollama_active": ollama_active()}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snap, ensure_ascii=False) + "\n")
    return snap


BASELINE = snapshot("baseline")


def check_stable(where: str) -> dict:
    snap = snapshot(where)
    if not snap["ollama_active"]:
        raise Abort(f"Ollama inaktiv bei {where}")
    if snap["mem_available_mib"] < 1024:
        raise Abort(f"RAM-Not bei {where}: available={snap['mem_available_mib']} MiB")
    growth = snap["swap_used_mib"] - BASELINE["swap_used_mib"]
    snap["swap_growth_mib"] = growth
    # 2 GiB Swap bei >20 GiB verfügbarem RAM ist Kernel-Reclaim, kein OOM.
    if snap["swap_used_mib"] >= 8192 and snap["mem_available_mib"] < 4096:
        raise Abort(
            f"Swap-Druck bei {where}: swap={snap['swap_used_mib']} "
            f"available={snap['mem_available_mib']}"
        )
    try:
        dmesg = subprocess.check_output(
            ["dmesg", "-T", "--level=err,crit,alert,emerg"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        if "Out of memory" in dmesg or "oom-kill" in dmesg.lower():
            tail = "\n".join(dmesg.strip().splitlines()[-8:])
            raise Abort(f"OOM im Kernel-Log bei {where}: {tail[-400:]}")
    except Abort:
        raise
    except Exception:
        pass
    return snap


def stop_models() -> None:
    text = subprocess.check_output(["ollama", "ps"], text=True)
    for line in text.splitlines()[1:]:
        name = line.split()[0] if line.strip() else ""
        if name:
            subprocess.run(["ollama", "stop", name], check=False)
    time.sleep(2)
    check_stable("after-stop")


def post(path: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"{path} HTTP {exc.code}: {body}") from exc
    elapsed = round(time.perf_counter() - t0, 3)
    data = json.loads(raw)
    data["_elapsed_s"] = elapsed
    return data


def stream_chat(payload: dict, timeout: int = 300) -> dict:
    body = deepcopy(payload)
    body["stream"] = True
    req = urllib.request.Request(
        f"{OLLAMA}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    ttft = None
    content = []
    thinking = []
    last = {}
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line:
                continue
            chunk = json.loads(line)
            if ttft is None:
                ttft = round(time.perf_counter() - t0, 3)
            msg = chunk.get("message") or {}
            if msg.get("content"):
                content.append(msg["content"])
            if msg.get("thinking"):
                thinking.append(msg["thinking"])
            last = chunk
    elapsed = round(time.perf_counter() - t0, 3)
    last["_elapsed_s"] = elapsed
    last["_ttft_s"] = ttft
    last["_content"] = "".join(content)
    last["_thinking"] = "".join(thinking)
    return last


def tok_s(data: dict) -> float | None:
    eval_count = data.get("eval_count") or 0
    eval_ns = data.get("eval_duration") or 0
    if eval_count and eval_ns:
        return round(eval_count / (eval_ns / 1e9), 2)
    return None


def summarize_chat(data: dict, extra: dict | None = None) -> dict:
    msg = data.get("message") or {}
    tcs = msg.get("tool_calls") or []
    names = []
    for tc in tcs:
        fn = tc.get("function") if isinstance(tc, dict) else {}
        names.append((fn or {}).get("name") or tc.get("name"))
    out = {
        "elapsed_s": data.get("_elapsed_s"),
        "ttft_s": data.get("_ttft_s"),
        "load_duration_s": round((data.get("load_duration") or 0) / 1e9, 3),
        "prompt_eval_count": data.get("prompt_eval_count"),
        "prompt_eval_duration_s": round((data.get("prompt_eval_duration") or 0) / 1e9, 3),
        "eval_count": data.get("eval_count"),
        "eval_duration_s": round((data.get("eval_duration") or 0) / 1e9, 3),
        "tok_s": tok_s(data),
        "done_reason": data.get("done_reason"),
        "content_head": (data.get("_content") or msg.get("content") or "")[:280],
        "thinking_head": (data.get("_thinking") or msg.get("thinking") or "")[:160],
        "has_tool_call": bool(tcs),
        "tool_names": names,
        "memory_load_called": any(n and "memory_load" in str(n) for n in names),
    }
    if extra:
        out.update(extra)
    return out


def mean(values: list[float | None]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 3)


def show_ctx(model: str) -> int | None:
    text = subprocess.check_output(["ollama", "show", model], text=True)
    for line in text.splitlines():
        if "num_ctx" in line:
            try:
                return int(line.split()[-1])
            except ValueError:
                return None
    return None


def run_text_suite(model: str) -> dict:
    check_stable(f"before-text-{model}")
    stop_models()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": TEXT_PROMPT}],
        "think": False,
        "keep_alive": "10m",
        "options": {**SAMPLE, "num_predict": 120},
    }
    cold = stream_chat(payload)
    cold_sum = summarize_chat(cold, {"kind": "cold", "resources": check_stable(f"cold-{model}")})
    warms = []
    for i in range(3):
        warm = stream_chat(payload)
        warms.append(summarize_chat(warm, {"kind": "warm", "n": i + 1, "resources": check_stable(f"warm-{model}-{i}")}))
    ps = ollama_ps()
    return {
        "model": model,
        "configured_num_ctx": show_ctx(model),
        "runtime_context": ps.get("context"),
        "processor": ps.get("processor"),
        "ps": ps,
        "cold": cold_sum,
        "warm": warms,
        "warm_mean": {
            "elapsed_s": mean([w["elapsed_s"] for w in warms]),
            "ttft_s": mean([w["ttft_s"] for w in warms]),
            "tok_s": mean([w["tok_s"] for w in warms]),
            "prompt_eval_count": mean([w["prompt_eval_count"] for w in warms]),
            "eval_count": mean([w["eval_count"] for w in warms]),
        },
    }


def chat_tools(model: str, prompt: str, tools: list, num_predict: int = 80) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "tools": tools,
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {**SAMPLE, "temperature": 0, "num_predict": num_predict},
    }
    t0 = time.perf_counter()
    data = post("/api/chat", payload, timeout=240)
    data["_elapsed_s"] = round(time.perf_counter() - t0, 3)
    return summarize_chat(data, {"tool_schema_count": len(tools), "resources": check_stable(f"tools-{model}")})


def openai_replay(model: str, capture_name: str, extra_tools: list | None = None) -> dict:
    body = json.loads((CAPTURE_DIR / capture_name).read_text(encoding="utf-8"))
    payload = deepcopy(body)
    payload["model"] = model
    payload["stream"] = False
    payload.pop("stream_options", None)
    payload["think"] = False
    payload["enable_thinking"] = False
    payload["reasoning_effort"] = "none"
    if extra_tools:
        payload["tools"] = list(payload.get("tools") or []) + extra_tools
    t0 = time.perf_counter()
    data = post("/v1/chat/completions", payload, timeout=300)
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    tcs = msg.get("tool_calls") or []
    names = []
    for tc in tcs:
        fn = tc.get("function") if isinstance(tc, dict) else {}
        names.append((fn or {}).get("name") or tc.get("name"))
    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    configured = show_ctx(model)
    truncated = bool(prompt_tokens and configured and prompt_tokens in {4096, 4098} or (configured and prompt_tokens and prompt_tokens >= configured))
    return {
        "capture": capture_name,
        "model": model,
        "tool_schema_count": len(payload.get("tools") or []),
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "finish_reason": choice.get("finish_reason"),
        "has_tool_call": bool(tcs),
        "tool_names": names,
        "memory_load_called": any(n and "memory_load" in str(n) for n in names),
        "content_head": (msg.get("content") or "")[:280],
        "reasoning_head": str(msg.get("reasoning") or msg.get("reasoning_content") or "")[:160],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": usage.get("completion_tokens"),
        "configured_num_ctx": configured,
        "overflow_snap_4098": prompt_tokens in {4096, 4098},
        "prompt_at_or_over_ctx": bool(configured and prompt_tokens and prompt_tokens >= configured),
        "resources": check_stable(f"replay-{model}-{capture_name}"),
        "ps": ollama_ps(),
    }


def long_prompt(model: str) -> dict:
    filler = "Projektkontext: lokale KI, MCP local-tools, kein Cloud-Fallback. " * 420
    prompt = (
        "Lies den folgenden langen Kontext. Am Ende rufe memory_load auf. "
        + filler
        + "\nENDE. Rufe jetzt memory_load mit workspace=/home/mike/Projects/Linux Lokales KI auf."
    )
    result = chat_tools(model, prompt, MEMORY_TOOL_CANON, num_predict=80)
    result["prompt_chars"] = len(prompt)
    result["ps"] = ollama_ps()
    result["overflow_snap_4098"] = result.get("prompt_eval_count") in {4096, 4098}
    return result


def vision_probe(model: str) -> dict:
    png = REPO / ".agent" / "tmp" / "quality-cutover-e2e.png"
    if not png.is_file():
        return {"skipped": True, "reason": f"missing {png}"}
    import base64

    b64 = base64.b64encode(png.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Nenne nur den sichtbaren Titel des Dokuments. Ein kurzer Satz.",
                "images": [b64],
            }
        ],
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {**SAMPLE, "temperature": 0.1, "num_predict": 40},
    }
    t0 = time.perf_counter()
    data = post("/api/chat", payload, timeout=240)
    data["_elapsed_s"] = round(time.perf_counter() - t0, 3)
    return summarize_chat(data, {"resources": check_stable(f"vision-{model}"), "ps": ollama_ps()})


def handle_abort(exc: Abort) -> None:
    payload = {
        "abort": str(exc),
        "baseline": BASELINE,
        "last": snapshot("abort"),
    }
    dump_json(ABORT_PATH, payload)
    print("ABORT", json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    raise SystemExit(2)


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: handle_abort(Abort("SIGTERM")))
    report: dict = {
        "baseline": BASELINE,
        "ref_model": REF,
        "cand_model": CAND,
        "ref_ctx": show_ctx(REF),
        "cand_ctx": show_ctx(CAND),
        "ref_id": None,
        "cand_id": None,
    }
    listing = subprocess.check_output(["ollama", "list"], text=True)
    report["ollama_list"] = listing
    try:
        check_stable("start")
        prior = OUT / "partial.json"
        if prior.is_file():
            old = json.loads(prior.read_text(encoding="utf-8"))
            if old.get("text_8k") and old.get("text_16k"):
                report["text_8k"] = old["text_8k"]
                report["text_16k"] = old["text_16k"]
                print("REUSE text suites from partial.json", flush=True)
        if "text_8k" not in report:
            print("TEXT SUITE", REF, flush=True)
            report["text_8k"] = run_text_suite(REF)
            dump_json(OUT / "partial.json", report)
        if "text_16k" not in report:
            print("TEXT SUITE", CAND, flush=True)
            report["text_16k"] = run_text_suite(CAND)
            dump_json(OUT / "partial.json", report)

        tools: dict = {}
        for model, key in ((REF, "8k"), (CAND, "16k")):
            print("TOOLS", model, flush=True)
            stop_models()
            tools[key] = {
                "short_chat": summarize_chat(
                    post(
                        "/api/chat",
                        {
                            "model": model,
                            "messages": [{"role": "user", "content": "Antworte nur mit OK."}],
                            "stream": False,
                            "think": False,
                            "keep_alive": "10m",
                            "options": {**SAMPLE, "num_predict": 8, "temperature": 0},
                        },
                    ),
                    {"resources": check_stable(f"short-{model}")},
                ),
                "canonical_tool": chat_tools(model, TOOL_PROMPT_CANON, MEMORY_TOOL_CANON),
                "short_tool": chat_tools(model, TOOL_PROMPT_SHORT, MEMORY_TOOL_SHORT),
                "replay_current_12tools": openai_replay(model, "captured-after-eager-empty.json"),
                "replay_overflow_44tools": openai_replay(model, "captured-serve-request.json"),
                "long_prompt": long_prompt(model),
            }
            tools[key]["vision"] = vision_probe(model)
            dump_json(OUT / "partial.json", {**report, "tools": tools})
        report["tools"] = tools
        report["final"] = check_stable("done")
        dump_json(OUT / "compare.json", report)
        print(json.dumps({
            "ref_ctx": report["ref_ctx"],
            "cand_ctx": report["cand_ctx"],
            "text_8k_warm_mean": report["text_8k"]["warm_mean"],
            "text_16k_warm_mean": report["text_16k"]["warm_mean"],
            "text_8k_cold": report["text_8k"]["cold"],
            "text_16k_cold": report["text_16k"]["cold"],
            "runtime_ctx": {
                "8k": report["text_8k"]["runtime_context"],
                "16k": report["text_16k"]["runtime_context"],
            },
            "tools_16k_overflow_prompt_tokens": tools["16k"]["replay_overflow_44tools"].get("prompt_tokens"),
            "tools_8k_overflow_prompt_tokens": tools["8k"]["replay_overflow_44tools"].get("prompt_tokens"),
            "tools_16k_memory_44": tools["16k"]["replay_overflow_44tools"].get("memory_load_called"),
            "tools_8k_memory_44": tools["8k"]["replay_overflow_44tools"].get("memory_load_called"),
        }, indent=2, ensure_ascii=False))
        print("WROTE", OUT / "compare.json", flush=True)
    except Abort as exc:
        dump_json(OUT / "partial.json", report)
        handle_abort(exc)


if __name__ == "__main__":
    os.chdir(REPO)
    main()
