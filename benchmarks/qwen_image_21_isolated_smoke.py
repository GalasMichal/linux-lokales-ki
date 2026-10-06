#!/usr/bin/env python3
"""Isolated Qwen-Image-2.1 edit smoke against ComfyUI 0.37.0 on :8189."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import time
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BENCH = REPO / "benchmarks" / "qwen-image-21-smoke-20260921"
TREE = Path("/srv/ai/apps/ComfyUI-0.37.0")
COMFY_INPUT = TREE / "input"
COMFY_OUTPUT = TREE / "output"
SOURCE_NAME = "qwen21_smoke_source.png"
PROMPT = (
    "Change only the apple in <image1> from red to bright green. "
    "Keep the white table, lighting, composition and everything else unchanged."
)
OFFICIAL_DIFFS = [
    "clip_name: qwen3vl_8b_int8_convrot.safetensors -> qwen3vl_8b_w4a8.safetensors",
    "QwenImage21Cache.device: auto -> cpu",
    "QwenImage21Cache.dtype: default -> int8",
    "subgraph flattened to API nodes; ComfySwitchNode omitted (official default switch=false uses encoder latent)",
    "SaveImageAdvanced -> SaveImage",
    "single LoadImage instead of two template assets",
    "TextEncodeQwenImage21.resolution explicit 512/1024 (official subgraph widget is 0 = keep source size; 1024 WxH only used if switch=true)",
]


def get(url: str, timeout: int = 10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def cpu_times() -> tuple[int, int]:
    parts = Path("/proc/stat").read_text().splitlines()[0].split()
    values = [int(part) for part in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def cpu_percent(prev: tuple[int, int] | None) -> tuple[float | None, tuple[int, int]]:
    current = cpu_times()
    if prev is None:
        return None, current
    total = current[0] - prev[0]
    idle = current[1] - prev[1]
    if total <= 0:
        return None, current
    return round(100.0 * (1.0 - idle / total), 1), current


def nvidia_smi() -> dict[str, int] | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    total, used, free, util = [int(part.strip()) for part in out.splitlines()[0].split(",")]
    return {"total_mib": total, "used_mib": used, "free_mib": free, "util_percent": util}


def meminfo() -> dict[str, float]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0])
    return {
        "mem_available_gib": round(values.get("MemAvailable", 0) / 1024 / 1024, 2),
        "mem_used_gib": round((values.get("MemTotal", 0) - values.get("MemAvailable", 0)) / 1024 / 1024, 2),
        "swap_used_gib": round((values.get("SwapTotal", 0) - values.get("SwapFree", 0)) / 1024 / 1024, 2),
    }


def png_info(path: Path) -> dict:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"FAIL PNG-Signatur fehlt: {path}")
    width, height = struct.unpack(">II", data[16:24])
    digest = hashlib.sha256(data).hexdigest()
    nonzero = any(b != 0 for b in data[100:4000])
    return {"path": str(path), "width": width, "height": height, "bytes": len(data), "sha256": digest, "nonzero_payload": nonzero}


def wait_ready(base: str, seconds: int = 90) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        stats = get(f"{base}/system_stats", timeout=3)
        if isinstance(stats, dict) and stats:
            return stats
        time.sleep(1)
    raise SystemExit("FAIL /system_stats antwortet nicht auf :8189")


def image_input_key(object_info: dict) -> str:
    del object_info
    return "images.image_1"


def build_graph(resolution: int, seed: int, prefix: str, image_key: str) -> dict:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": "qwen_image_2.1_int8_convrot.safetensors", "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen3vl_8b_w4a8.safetensors",
                "type": "qwen_image",
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"},
        },
        "4": {
            "class_type": "QwenImage21Cache",
            "inputs": {"model": ["1", 0], "device": "cpu", "dtype": "int8"},
        },
        "5": {"class_type": "LoadImage", "inputs": {"image": SOURCE_NAME}},
        "6": {
            "class_type": "TextEncodeQwenImage21",
            "inputs": {
                "clip": ["2", 0],
                "prompt": PROMPT,
                "negative_prompt": "",
                "vae": ["3", 0],
                "resolution": resolution,
                image_key: ["5", 0],
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["6", 1],
                "latent_image": ["6", 2],
                "seed": seed,
                "steps": 25,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": prefix, "images": ["8", 0]},
        },
    }


def run_job(base: str, graph: dict, timeout: int, label: str) -> dict:
    started = time.monotonic()
    before_gpu = nvidia_smi()
    before_mem = meminfo()
    cpu_prev = None
    _, cpu_prev = cpu_percent(None)
    peak_gpu = before_gpu["used_mib"] if before_gpu else 0
    peak_ram = before_mem["mem_used_gib"]
    peak_swap = before_mem["swap_used_gib"]
    peak_cpu = 0.0
    peak_gpu_util = before_gpu["util_percent"] if before_gpu else 0
    payload = json.dumps({"prompt": graph, "client_id": f"qwen21-{label}"}).encode()
    req = urllib.request.Request(
        f"{base}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        accepted = json.loads(response.read().decode())
    node_errors = accepted.get("node_errors") or {}
    if node_errors or not accepted.get("prompt_id"):
        raise RuntimeError(f"FAIL {label} Prompt abgelehnt: {accepted}")
    prompt_id = accepted["prompt_id"]
    history = None
    first_progress = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        gpu = nvidia_smi()
        mem = meminfo()
        if gpu:
            peak_gpu = max(peak_gpu, gpu["used_mib"])
            peak_gpu_util = max(peak_gpu_util, gpu["util_percent"])
        peak_ram = max(peak_ram, mem["mem_used_gib"])
        peak_swap = max(peak_swap, mem["swap_used_gib"])
        cpu, cpu_prev = cpu_percent(cpu_prev)
        if cpu is not None:
            peak_cpu = max(peak_cpu, cpu)
        if first_progress is None:
            queue = get(f"{base}/queue", timeout=5)
            running = (queue or {}).get("queue_running") if isinstance(queue, dict) else None
            if isinstance(running, list) and any(prompt_id in json.dumps(item) for item in running):
                first_progress = round(time.monotonic() - started, 3)
            elif gpu and gpu["util_percent"] >= 8:
                first_progress = round(time.monotonic() - started, 3)
        time.sleep(0.75)
        current = get(f"{base}/history/{prompt_id}", timeout=5)
        if isinstance(current, dict) and prompt_id in current:
            history = current[prompt_id]
            if first_progress is None:
                first_progress = round(time.monotonic() - started, 3)
            break
    if history is None:
        raise RuntimeError(f"FAIL {label} Timeout nach {timeout}s")
    status = history.get("status") or {}
    if status.get("status_str") == "error":
        raise RuntimeError(f"FAIL {label} ComfyUI-Fehler: {status.get('messages')}")
    images = ((history.get("outputs") or {}).get("9") or {}).get("images") or []
    if not images:
        raise RuntimeError(f"FAIL {label} keine Ausgabe: {history.get('outputs')}")
    filename = images[0]["filename"]
    source = COMFY_OUTPUT / filename
    if not source.is_file():
        raise RuntimeError(f"FAIL {label} Datei fehlt: {source}")
    info = png_info(source)
    dest = BENCH / "output" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    info = png_info(dest)
    if not info["nonzero_payload"]:
        raise RuntimeError(f"FAIL {label} PNG wirkt leer")
    runtime = round(time.monotonic() - started, 3)
    return {
        "ok": True,
        "label": label,
        "prompt_id": prompt_id,
        "runtime_seconds": runtime,
        "first_progress_seconds": first_progress,
        "png": info,
        "vram_before": before_gpu,
        "vram_peak_used_mib": peak_gpu,
        "vram_peak_util_percent": peak_gpu_util,
        "vram_after": nvidia_smi(),
        "ram_before": before_mem,
        "ram_peak_used_gib": peak_ram,
        "swap_peak_used_gib": peak_swap,
        "cpu_peak_percent": peak_cpu,
        "ram_after": meminfo(),
    }


def validate_models(object_info: dict) -> None:
    missing = [name for name in ("UNETLoader", "CLIPLoader", "VAELoader", "TextEncodeQwenImage21", "QwenImage21Cache", "KSampler", "LoadImage") if name not in object_info]
    if missing:
        raise SystemExit(f"FAIL Nodes fehlen: {missing}")
    unets = object_info["UNETLoader"]["input"]["required"]["unet_name"][0]
    clips = object_info["CLIPLoader"]["input"]["required"]["clip_name"][0]
    vaes = object_info["VAELoader"]["input"]["required"]["vae_name"][0]
    if "qwen_image_2.1_int8_convrot.safetensors" not in unets:
        raise SystemExit("FAIL DiT int8 wird nicht erkannt")
    if "qwen3vl_8b_w4a8.safetensors" not in clips:
        raise SystemExit("FAIL w4a8-Encoder wird nicht erkannt")
    if "qwen_image_2.1_vae_bf16.safetensors" not in vaes:
        raise SystemExit("FAIL 2.1-VAE wird nicht erkannt")
    if "qwen3vl_8b_bf16.safetensors" in clips:
        print("WARN bf16-Encoder Datei sichtbar, Graph lädt sie nicht", flush=True)


def main() -> int:
    global TREE, COMFY_INPUT, COMFY_OUTPUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8189")
    parser.add_argument("--tree", default=str(TREE), help="ComfyUI tree for input/output staging")
    parser.add_argument("--stage", choices=["validate", "512", "768", "1024", "all"], default="all")
    args = parser.parse_args()
    TREE = Path(args.tree)
    COMFY_INPUT = TREE / "input"
    COMFY_OUTPUT = TREE / "output"
    stats = wait_ready(args.base)
    argv = (stats.get("system") or {}).get("argv")
    object_info = get(f"{args.base}/object_info", timeout=30)
    if not isinstance(object_info, dict):
        raise SystemExit("FAIL /object_info")
    validate_models(object_info)
    image_key = image_input_key(object_info)
    src = BENCH / "input" / "source.png"
    COMFY_INPUT.mkdir(parents=True, exist_ok=True)
    staged = COMFY_INPUT / SOURCE_NAME
    shutil.copy2(src, staged)
    graph_512 = build_graph(512, 42, "qwen21_smoke_512", image_key)
    graph_768 = build_graph(768, 42, "qwen21_smoke_768", image_key)
    graph_1024 = build_graph(1024, 42, "qwen21_smoke_1024", image_key)
    (BENCH / "api-workflow-512.json").write_text(json.dumps(graph_512, indent=2) + "\n")
    (BENCH / "api-workflow-768.json").write_text(json.dumps(graph_768, indent=2) + "\n")
    (BENCH / "api-workflow-1024.json").write_text(json.dumps(graph_1024, indent=2) + "\n")
    (BENCH / "official-diffs.json").write_text(json.dumps({"prompt": PROMPT, "diffs": OFFICIAL_DIFFS, "image_key": image_key}, indent=2) + "\n")
    result = {
        "ok": True,
        "comfy_version": (stats.get("system") or {}).get("comfyui_version"),
        "argv": argv,
        "image_key": image_key,
        "official_diffs": OFFICIAL_DIFFS,
        "prompt": PROMPT,
        "source": json.loads((BENCH / "input" / "source.json").read_text()),
        "vram_idle": nvidia_smi(),
        "ram_idle": meminfo(),
    }
    if args.stage in {"validate", "all"}:
        clips = object_info["CLIPLoader"]["input"]["required"]["clip_name"][0]
        result["validate"] = {
            "ok": True,
            "w4a8_seen": "qwen3vl_8b_w4a8.safetensors" in clips,
            "bf16_encoder_seen": "qwen3vl_8b_bf16.safetensors" in clips,
            "nodes_ok": True,
            "image_key": image_key,
        }
    fatal = False
    if args.stage in {"512", "all"}:
        try:
            result["edit_512"] = run_job(args.base, graph_512, 420, "512")
            width = result["edit_512"]["png"]["width"]
            if width < 480:
                raise RuntimeError(f"FAIL 512 Auflösung {result['edit_512']['png']}")
        except (RuntimeError, urllib.error.URLError) as exc:
            result["edit_512"] = {"ok": False, "error": str(exc), "vram_after": nvidia_smi(), "ram_after": meminfo()}
            fatal = True
    if args.stage in {"1024", "all"} and not fatal:
        if args.stage == "all" and not result.get("edit_512", {}).get("ok"):
            result["edit_1024"] = {"ok": False, "skipped": True, "reason": "512 fehlte"}
        else:
            try:
                result["edit_1024"] = run_job(args.base, graph_1024, 600, "1024")
            except (RuntimeError, urllib.error.URLError) as exc:
                result["edit_1024"] = {"ok": False, "error": str(exc), "vram_after": nvidia_smi(), "ram_after": meminfo()}
                result["ok"] = False
    if args.stage == "768":
        try:
            result["edit_768"] = run_job(args.base, graph_768, 540, "768")
        except (RuntimeError, urllib.error.URLError) as exc:
            result["edit_768"] = {"ok": False, "error": str(exc), "vram_after": nvidia_smi(), "ram_after": meminfo()}
            result["ok"] = False
    if fatal:
        result["ok"] = False
    (BENCH / f"smoke-{args.stage}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if fatal or (args.stage in {"512"} and not result.get("edit_512", {}).get("ok")):
        return 1
    if args.stage == "1024" and not result.get("edit_1024", {}).get("ok"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
