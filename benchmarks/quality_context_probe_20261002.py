#!/usr/bin/env python3
"""Additive local-quality context probe: 16K / 24K / 32K.

Does NOT retarget local-quality or local-fast. Creates bench aliases only.
Stops ascending on hard abort (OOM-like pressure) or severe artifacts.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path("/home/mike/Projects/Linux Lokales KI")
OUT = REPO / "benchmarks" / "quality-context-probe-20261002"
OLLAMA = "http://127.0.0.1:11434"
LEVELS = [
    ("bench-qwen38-27b-16k", 16384, REPO / "config/modelfiles/bench-qwen38-27b-16k.Modelfile"),
    ("bench-qwen38-27b-24k", 24576, REPO / "config/modelfiles/bench-qwen38-27b-24k.Modelfile"),
    ("bench-qwen38-27b-32k", 32768, REPO / "config/modelfiles/bench-qwen38-27b-32k.Modelfile"),
]
PROD = "local-quality"


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
    data = {"tag": tag, **nvidia(), **mem(), "ps": ps()}
    if data["mem_available_mib"] < 1024:
        raise Abort(f"RAM-Not bei {tag}: {data['mem_available_mib']} MiB")
    if data["swap_used_mib"] >= 12288 and data["mem_available_mib"] < 3072:
        raise Abort(f"Swap-Druck bei {tag}: swap={data['swap_used_mib']} avail={data['mem_available_mib']}")
    return data


def post(path: str, payload: dict, timeout: int = 420) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
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


def ensure_alias(name: str, ctx: int, modelfile: Path) -> None:
    listing = subprocess.check_output(["ollama", "list"], text=True)
    if name in listing or f"{name}:latest" in listing:
        show = subprocess.check_output(["ollama", "show", name, "--modelfile"], text=True)
        if f"PARAMETER num_ctx {ctx}" not in show and f"num_ctx {ctx}" not in show:
            print(f"RECREATE {name} ctx={ctx}", flush=True)
            subprocess.check_call(["ollama", "create", name, "-f", str(modelfile)])
        else:
            print(f"OK alias {name}", flush=True)
        return
    print(f"CREATE {name}", flush=True)
    subprocess.check_call(["ollama", "create", name, "-f", str(modelfile)])


def artifact_flags(text: str) -> list[str]:
    flags: list[str] = []
    if not text or not text.strip():
        flags.append("empty")
        return flags
    if re.search(r"(.)\1{40,}", text):
        flags.append("char_repeat")
    words = re.findall(r"\w+", text.lower())
    if len(words) >= 12:
        for i in range(len(words) - 8):
            window = words[i : i + 8]
            if len(set(window)) == 1:
                flags.append("word_loop")
                break
    if text.count("```") >= 6 and len(text) > 800:
        flags.append("fence_spam")
    # obvious garbage token soup
    if len(text) > 200 and len(re.findall(r"[^\w\s\.,;:!\?\-'/\"()\[\]{}]", text)) / max(len(text), 1) > 0.25:
        flags.append("symbol_soup")
    return flags


def filler(tokens_approx: int) -> str:
    # ~1 token ≈ 4 chars for German-ish filler; keep deterministic.
    unit = "Kontextfüllung für den Qualitäts-Benchmark. "
    need = max(tokens_approx * 4, 200)
    return (unit * ((need // len(unit)) + 1))[:need]


def probe_level(model: str, ctx: int) -> dict:
    result: dict = {"model": model, "num_ctx": ctx, "ok": True, "artifacts": [], "tests": {}}
    stop_all()
    result["baseline"] = snap(f"{ctx}-baseline")

    print(f"=== {model} ctx={ctx} cold ===", flush=True)
    cold = post(
        "/api/chat",
        {
            "model": model,
            "messages": [{"role": "user", "content": "Antworte nur mit dem Wort OK."}],
            "stream": False,
            "think": False,
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_predict": 8},
        },
    )
    content = ((cold.get("message") or {}).get("content") or "").strip()
    arts = artifact_flags(content)
    if "OK" not in content.upper():
        arts.append("missing_ok")
    result["tests"]["cold"] = {
        "elapsed_s": cold["_elapsed_s"],
        "load_s": round((cold.get("load_duration") or 0) / 1e9, 3),
        "prompt_eval_count": cold.get("prompt_eval_count"),
        "eval_count": cold.get("eval_count"),
        "tok_s": tok_s(cold),
        "content": content[:80],
        "artifacts": arts,
        "resources": snap(f"{ctx}-cold"),
    }
    if arts:
        result["artifacts"].extend([f"cold:{a}" for a in arts])

    print(f"=== {model} tool ===", flush=True)
    tool = post(
        "/api/chat",
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": 'Call tool memory_load with workspace="/home/mike/Projects/Linux Lokales KI". No essay.',
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "memory_load",
                        "description": "Load .agent memory",
                        "parameters": {
                            "type": "object",
                            "properties": {"workspace": {"type": "string"}},
                            "required": ["workspace"],
                        },
                    },
                }
            ],
            "stream": False,
            "think": False,
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_predict": 96},
        },
    )
    msg = tool.get("message") or {}
    tcs = msg.get("tool_calls") or []
    tool_arts: list[str] = []
    if not tcs:
        tool_arts.append("no_tool_call")
    else:
        fn = (tcs[0].get("function") or {})
        if fn.get("name") != "memory_load":
            tool_arts.append("wrong_tool")
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                tool_arts.append("bad_args_json")
                args = {}
        if not isinstance(args, dict) or "workspace" not in args:
            tool_arts.append("missing_workspace_arg")
    result["tests"]["tool"] = {
        "elapsed_s": tool["_elapsed_s"],
        "tok_s": tok_s(tool),
        "prompt_eval_count": tool.get("prompt_eval_count"),
        "has_tool_call": bool(tcs),
        "tool_calls": tcs,
        "content": (msg.get("content") or "")[:120],
        "artifacts": tool_arts,
        "resources": snap(f"{ctx}-tool"),
    }
    if tool_arts:
        result["artifacts"].extend([f"tool:{a}" for a in tool_arts])

    # Fill ~55% of context with deterministic filler, ask for a pinned answer.
    fill_tokens = int(ctx * 0.55)
    print(f"=== {model} filled ~{fill_tokens} tok ===", flush=True)
    body = filler(fill_tokens) + "\n\nAm Ende steht die Aufgabe: Antworte mit genau: KONTEXT-OK-" + str(ctx)
    filled = post(
        "/api/chat",
        {
            "model": model,
            "messages": [{"role": "user", "content": body}],
            "stream": False,
            "think": False,
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_predict": 32},
        },
        timeout=600,
    )
    fcontent = ((filled.get("message") or {}).get("content") or "").strip()
    farts = artifact_flags(fcontent)
    expected = f"KONTEXT-OK-{ctx}"
    if expected not in fcontent.replace(" ", ""):
        # allow minor whitespace
        if expected not in fcontent:
            farts.append("wrong_marker")
    pec = filled.get("prompt_eval_count") or 0
    # Hard snap to much smaller window is a bad sign.
    if pec and pec < min(4096, ctx // 4):
        farts.append(f"prompt_snap_{pec}")
    result["tests"]["filled"] = {
        "elapsed_s": filled["_elapsed_s"],
        "tok_s": tok_s(filled),
        "prompt_eval_count": pec,
        "eval_count": filled.get("eval_count"),
        "content": fcontent[:160],
        "artifacts": farts,
        "fill_chars": len(body),
        "resources": snap(f"{ctx}-filled"),
    }
    if farts:
        result["artifacts"].extend([f"filled:{a}" for a in farts])

    # Severe gate for ascending further
    severe = [a for a in result["artifacts"] if any(x in a for x in ("char_repeat", "word_loop", "symbol_soup", "no_tool_call", "prompt_snap"))]
    result["severe"] = severe
    result["ok"] = not severe and "wrong_marker" not in ",".join(result["artifacts"])
    result["final"] = snap(f"{ctx}-final")
    result["ps"] = ps()
    return result


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # Safety: productive alias unchanged
    prod_show = subprocess.check_output(["ollama", "show", PROD, "--modelfile"], text=True)
    if "PARAMETER num_ctx 16384" not in prod_show and "num_ctx 16384" not in prod_show:
        raise SystemExit("ABBRUCH: local-quality ist nicht mehr 16384 — Stopp vor Benchmark.")

    report: dict = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "productive_local_quality_ctx": 16384,
        "note": "Additive bench aliases only. No cutover.",
        "levels": [],
        "recommendation": None,
    }

    for name, ctx, mf in LEVELS:
        ensure_alias(name, ctx, mf)

    highest_ok = None
    try:
        for name, ctx, _mf in LEVELS:
            level = probe_level(name, ctx)
            report["levels"].append(level)
            (OUT / f"level-{ctx}.json").write_text(json.dumps(level, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps({"ctx": ctx, "ok": level["ok"], "artifacts": level["artifacts"], "severe": level["severe"]}, ensure_ascii=False), flush=True)
            if level["ok"]:
                highest_ok = ctx
            else:
                print(f"STOP ascending after ctx={ctx} artifacts={level['artifacts']}", flush=True)
                break
    except Abort as exc:
        report["abort"] = str(exc)
        print("ABORT", exc, flush=True)
    finally:
        stop_all()

    report["highest_ok_ctx"] = highest_ok
    if highest_ok is None:
        report["recommendation"] = "Kein Level ohne Artefakte. local-quality bleibt 16384."
    elif highest_ok == 16384:
        report["recommendation"] = "16K stabil. 24K/32K nicht empfohlen ohne weiteren Fix. Kein Cutover."
    elif highest_ok == 24576:
        report["recommendation"] = "24K ohne schwere Artefakte. Optional später Cutover nur nach Freigabe. 32K nicht freigeben."
    else:
        report["recommendation"] = "32K ohne schwere Artefakte in diesem Probe. Cutover trotzdem nur nach expliziter Freigabe."

    # Confirm productive alias still 16k
    prod_after = subprocess.check_output(["ollama", "show", PROD, "--modelfile"], text=True)
    report["local_quality_still_16384"] = "num_ctx 16384" in prod_after
    report["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (OUT / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("SUMMARY", json.dumps({
        "highest_ok_ctx": highest_ok,
        "recommendation": report["recommendation"],
        "local_quality_still_16384": report["local_quality_still_16384"],
        "abort": report.get("abort"),
    }, ensure_ascii=False, indent=2), flush=True)
    return 0 if report.get("abort") is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
