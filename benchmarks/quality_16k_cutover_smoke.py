#!/usr/bin/env python3
"""Smoke productive local-quality after 16k cutover. No YOLO."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://127.0.0.1:11434"
MODEL = "local-quality"
OUT = Path(__file__).resolve().parent / "quality-16k-cutover-20260916"
OUT.mkdir(parents=True, exist_ok=True)


def ollama_json(path: str, payload: dict, timeout: int = 240) -> dict:
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def nvidia() -> dict:
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


def meminfo() -> dict:
    vals = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, rest = line.split(":", 1)
        vals[key] = int(rest.strip().split()[0])
    return {
        "mem_total_mib": vals["MemTotal"] // 1024,
        "mem_available_mib": vals["MemAvailable"] // 1024,
        "swap_used_mib": (vals["SwapTotal"] - vals["SwapFree"]) // 1024,
    }


def parse_ps() -> dict:
    text = subprocess.check_output(["ollama", "ps"], text=True)
    return {"raw": text, "loaded": len(text.splitlines()) > 1}


def tok_s(data: dict) -> float | None:
    eval_count = data.get("eval_count") or 0
    eval_ns = data.get("eval_duration") or 0
    if eval_count and eval_ns:
        return round(eval_count / (eval_ns / 1e9), 2)
    return None


def chat(prompt: str, num_predict: int = 80, tools: list | None = None) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "keep_alive": "8m",
        "options": {"num_predict": num_predict, "temperature": 0},
    }
    if tools:
        payload["tools"] = tools
    t0 = time.perf_counter()
    data = ollama_json("/api/chat", payload, timeout=240)
    data["_elapsed_s"] = round(time.perf_counter() - t0, 3)
    return data


def main() -> None:
    show = subprocess.check_output(["ollama", "show", MODEL], text=True)
    ctx = None
    for line in show.splitlines():
        if "num_ctx" in line:
            ctx = line.split()[-1]
            break
    load = chat("Antworte nur mit dem Wort OK.", 8)
    time.sleep(0.5)
    stats = {
        "model": MODEL,
        "num_ctx": ctx,
        "ps": parse_ps(),
        "nvidia": nvidia(),
        "ram": meminfo(),
        "override_sha": subprocess.check_output(
            ["sha256sum", "/etc/systemd/system/ollama.service.d/override.conf"], text=True
        ).split()[0],
        "load": {
            "content": (load.get("message") or {}).get("content"),
            "eval_count": load.get("eval_count"),
            "prompt_eval_count": load.get("prompt_eval_count"),
            "load_s": round((load.get("load_duration") or 0) / 1e9, 3),
            "prompt_eval_s": round((load.get("prompt_eval_duration") or 0) / 1e9, 3),
            "tok_s": tok_s(load),
            "elapsed_s": load["_elapsed_s"],
            "ttft_s": round(
                ((load.get("load_duration") or 0) + (load.get("prompt_eval_duration") or 0)) / 1e9, 3
            ),
        },
    }
    coding = chat(
        "Schreibe eine Python-Funktion add(a, b), die a+b zurückgibt. Nur der Funktionskörper, kein Text.",
        60,
    )
    stats["coding"] = {
        "content": (coding.get("message") or {}).get("content"),
        "tok_s": tok_s(coding),
        "elapsed_s": coding["_elapsed_s"],
        "eval_count": coding.get("eval_count"),
    }
    tools = [
        {
            "type": "function",
            "function": {
                "name": "memory_load",
                "description": "Load compact .agent memory.",
                "parameters": {
                    "type": "object",
                    "properties": {"workspace": {"type": "string"}},
                    "required": ["workspace"],
                },
            },
        }
    ]
    tool = chat(
        "Rufe das Tool memory_load mit workspace=/home/mike/Projects/Linux Lokales KI auf. Keine Freitext-Antwort.",
        80,
        tools=tools,
    )
    msg = tool.get("message") or {}
    stats["tool"] = {
        "content": msg.get("content"),
        "tool_calls": msg.get("tool_calls"),
        "tok_s": tok_s(tool),
        "elapsed_s": tool["_elapsed_s"],
        "eval_count": tool.get("eval_count"),
        "prompt_eval_count": tool.get("prompt_eval_count"),
    }
    stats["nvidia_after"] = nvidia()
    stats["ps_after"] = parse_ps()
    stats["pass"] = bool(
        stats["num_ctx"] == "16384"
        and "16384" in (stats["ps_after"].get("raw") or "")
        and (stats["load"]["tok_s"] or 0) >= 8
        and stats["nvidia_after"]["vram_used_mib"] >= 12000
        and stats["tool"]["tool_calls"]
        and stats["override_sha"] == "7fb44d5fbe5363ca9196bc92a95cb0d23766b4f853c491de19e134efa6d89bf4"
    )
    out = OUT / "smoke.json"
    out.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(
        {k: stats[k] for k in ("num_ctx", "load", "coding", "tool", "nvidia", "nvidia_after", "pass", "ram")},
        indent=2,
        ensure_ascii=False,
    ))
    print("ps_after", stats["ps_after"]["raw"])
    print("wrote", out)
    if not stats["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
