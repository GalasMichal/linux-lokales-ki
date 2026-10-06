#!/usr/bin/env python3
"""Additive 32k load probe. Stops on OOM-like pressure. Does not retarget aliases."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path("/home/mike/Projects/Linux Lokales KI")
OUT = REPO / "benchmarks" / "ctx16k-20260916"
MODEL = "bench-qwen38-27b-32k"
PARENT = "qwen3.8:27b"
OLLAMA = "http://127.0.0.1:11434"
CAPTURE = REPO / "benchmarks/toolcall-debug-20260915/captured-serve-request.json"


class Abort(RuntimeError):
    pass


def nvidia() -> dict:
    raw = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
        text=True,
    ).strip()
    used, total, util = [x.strip() for x in raw.split(",")]
    return {"vram_used_mib": int(used), "vram_total_mib": int(total), "gpu_util": int(util)}


def mem() -> dict:
    vals = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, rest = line.split(":", 1)
        vals[k] = int(rest.strip().split()[0])
    return {
        "mem_available_mib": vals["MemAvailable"] // 1024,
        "swap_used_mib": (vals["SwapTotal"] - vals["SwapFree"]) // 1024,
    }


def ps() -> str:
    return subprocess.check_output(["ollama", "ps"], text=True)


def snap(tag: str) -> dict:
    data = {"tag": tag, **nvidia(), **mem(), "ps": ps(), "ollama": subprocess.call(["systemctl", "is-active", "--quiet", "ollama.service"]) == 0}
    if not data["ollama"]:
        raise Abort(f"Ollama tot bei {tag}")
    if data["mem_available_mib"] < 1024:
        raise Abort(f"RAM-Not bei {tag}: {data['mem_available_mib']}")
    if data["swap_used_mib"] >= 8192 and data["mem_available_mib"] < 4096:
        raise Abort(f"Swap-Druck bei {tag}")
    return data


def post(path: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(f"{OLLAMA}{path}", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    data["_elapsed_s"] = round(time.perf_counter() - t0, 3)
    return data


def tok_s(data: dict) -> float | None:
    n, ns = data.get("eval_count") or 0, data.get("eval_duration") or 0
    return round(n / (ns / 1e9), 2) if n and ns else None


def stop_all() -> None:
    text = subprocess.check_output(["ollama", "ps"], text=True)
    for line in text.splitlines()[1:]:
        name = line.split()[0] if line.strip() else ""
        if name:
            subprocess.run(["ollama", "stop", name], check=False)
    time.sleep(2)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"baseline": snap("baseline")}
    try:
        mf = REPO / "config/modelfiles/bench-qwen38-27b-32k.Modelfile"
        if subprocess.call(["ollama", "list"], stdout=subprocess.PIPE) == 0:
            listing = subprocess.check_output(["ollama", "list"], text=True)
            if MODEL not in listing:
                print("CREATE", MODEL, flush=True)
                subprocess.check_call(["ollama", "create", MODEL, "-f", str(mf)])
        stop_all()
        show = subprocess.check_output(["ollama", "show", MODEL], text=True)
        ctx = None
        for line in show.splitlines():
            if "num_ctx" in line:
                ctx = int(line.split()[-1])
        assert ctx == 32768, ctx
        report["show_num_ctx"] = ctx
        print("COLD CHAT", flush=True)
        cold = post("/api/chat", {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Antworte nur mit OK."}],
            "stream": False,
            "think": False,
            "keep_alive": "8m",
            "options": {"temperature": 0, "num_predict": 8},
        })
        report["cold"] = {
            "elapsed_s": cold["_elapsed_s"],
            "load_s": round((cold.get("load_duration") or 0) / 1e9, 3),
            "prompt_eval_count": cold.get("prompt_eval_count"),
            "eval_count": cold.get("eval_count"),
            "tok_s": tok_s(cold),
            "content": (cold.get("message") or {}).get("content"),
            "resources": snap("cold"),
        }
        print("WARM CHAT", flush=True)
        warm = post("/api/chat", {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Antworte nur mit OK."}],
            "stream": False,
            "think": False,
            "keep_alive": "8m",
            "options": {"temperature": 0, "num_predict": 8},
        })
        report["warm"] = {
            "elapsed_s": warm["_elapsed_s"],
            "tok_s": tok_s(warm),
            "prompt_eval_count": warm.get("prompt_eval_count"),
            "resources": snap("warm"),
        }
        print("TOOL", flush=True)
        tool = post("/api/chat", {
            "model": MODEL,
            "messages": [{"role": "user", "content": 'Call memory_load with workspace="/home/mike/Projects/Linux Lokales KI". No essay.'}],
            "tools": [{"type": "function", "function": {"name": "memory_load", "description": "Load .agent memory", "parameters": {"type": "object", "properties": {"workspace": {"type": "string"}}, "required": ["workspace"]}}}],
            "stream": False,
            "think": False,
            "keep_alive": "8m",
            "options": {"temperature": 0, "num_predict": 80},
        })
        msg = tool.get("message") or {}
        tcs = msg.get("tool_calls") or []
        report["tool"] = {
            "elapsed_s": tool["_elapsed_s"],
            "tok_s": tok_s(tool),
            "has_tool_call": bool(tcs),
            "tool_names": [((c.get("function") or {}).get("name")) for c in tcs],
            "prompt_eval_count": tool.get("prompt_eval_count"),
            "resources": snap("tool"),
        }
        print("REPLAY 44 TOOLS", flush=True)
        body = json.loads(CAPTURE.read_text())
        body["model"] = MODEL
        body["stream"] = False
        body.pop("stream_options", None)
        body["think"] = False
        body["enable_thinking"] = False
        body["reasoning_effort"] = "none"
        replay = post("/v1/chat/completions", body, timeout=360)
        choice = (replay.get("choices") or [{}])[0]
        rmsg = choice.get("message") or {}
        rtcs = rmsg.get("tool_calls") or []
        usage = replay.get("usage") or {}
        report["replay_44"] = {
            "elapsed_s": replay["_elapsed_s"],
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "has_tool_call": bool(rtcs),
            "tool_names": [((c.get("function") or {}).get("name")) for c in rtcs],
            "overflow_snap_4098": usage.get("prompt_tokens") in {4096, 4098, 8192, 8194},
            "content_head": (rmsg.get("content") or "")[:240],
            "resources": snap("replay"),
            "ps": ps(),
        }
        report["final"] = snap("final")
        report["pass_load"] = bool(
            report["cold"]["resources"]["ps"].find("32768") >= 0
            or "32768" in report["warm"]["resources"]["ps"]
        )
        (OUT / "probe-32k.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "ctx": ctx,
            "cold": report["cold"],
            "warm": report["warm"],
            "tool": report["tool"],
            "replay_44": {k: report["replay_44"][k] for k in report["replay_44"] if k != "resources"},
            "final_vram": report["final"]["vram_used_mib"],
            "final_swap": report["final"]["swap_used_mib"],
        }, indent=2, ensure_ascii=False))
        print("WROTE probe-32k.json", flush=True)
    except Abort as exc:
        report["abort"] = str(exc)
        (OUT / "probe-32k.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("ABORT", exc, flush=True)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
