#!/usr/bin/env python3
"""Isolated FLUX.2-[klein] API regression against ComfyUI 0.38.0 on :8189."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import time
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / "apps" / "ki-workplace" / "workflows" / "flux2-klein-t2i-api-v1.json"
TREE = Path("/srv/ai/apps/ComfyUI-0.38.0")
OUTPUT = TREE / "output"
A12_PROMPT = "A14 acceptance smoke. Simple red apple on a white table. No text."
A12_WORKFLOW_SHA = "d9d752d52b1430bd3756908885146daea41279e29a7b6e3a9e05705572f39953"
MODEL_SHA = {
    "diffusion_model": "97ed34fe0567e436200f2faee3939b88f2b5d99f8af2a4dc16532c4245c0ccb6",
    "text_encoder": "6c671498573ac2f7a5501502ccce8d2b08ea6ca2f661c458e708f36b36edfc5a",
    "vae": "868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3",
}
FLUX_NODES = (
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "EmptyFlux2LatentImage",
    "CLIPTextEncode",
    "ConditioningZeroOut",
    "RandomNoise",
    "KSamplerSelect",
    "Flux2Scheduler",
    "CFGGuider",
    "SamplerCustomAdvanced",
    "VAEDecode",
    "SaveImage",
)
QWEN21_NODES = ("TextEncodeQwenImage21", "QwenImage21Cache")


def get(url: str, timeout: int = 10) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def nvidia_smi() -> dict[str, int] | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    total, used, free = [int(part.strip()) for part in out.splitlines()[0].split(",")]
    return {"total_mib": total, "used_mib": used, "free_mib": free}


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"FAIL PNG-Signatur fehlt: {path}")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wait_ready(base: str, seconds: int = 120) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        stats = get(f"{base}/system_stats", timeout=3)
        if isinstance(stats, dict) and stats:
            return stats
        time.sleep(1)
    raise SystemExit("FAIL /system_stats antwortet nicht auf :8189")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8189")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    started = time.monotonic()
    before_gpu = nvidia_smi()
    stats = wait_ready(args.base)
    argv = stats.get("system", {}).get("argv") if isinstance(stats.get("system"), dict) else None

    object_info = get(f"{args.base}/object_info", timeout=30)
    if not isinstance(object_info, dict):
        raise SystemExit("FAIL /object_info")
    missing_flux = [name for name in FLUX_NODES if name not in object_info]
    missing_qwen = [name for name in QWEN21_NODES if name not in object_info]
    if missing_flux:
        raise SystemExit(f"FAIL FLUX-Nodes fehlen: {missing_flux}")
    if missing_qwen:
        raise SystemExit(f"FAIL Qwen-Image-2.1-Nodes fehlen: {missing_qwen}")
    models = object_info["UNETLoader"]["input"]["required"]["unet_name"][0]
    if "flux-2-klein-4b-fp8.safetensors" not in models:
        raise SystemExit("FAIL FLUX-Gewicht wird nicht erkannt")
    if "qwen_image_2.1_int8_convrot.safetensors" not in models:
        raise SystemExit("FAIL Qwen-Image-2.1-Gewicht wird nicht erkannt")

    template = json.loads(WORKFLOW.read_text())
    canon = json.dumps(template, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    workflow_sha = hashlib.sha256(canon).hexdigest()
    if workflow_sha != A12_WORKFLOW_SHA:
        raise SystemExit(f"FAIL Workflow-Hash {workflow_sha} != {A12_WORKFLOW_SHA}")
    job = "iso038512"
    graph = deepcopy(template)
    graph["4"]["inputs"]["text"] = A12_PROMPT
    graph["6"]["inputs"]["width"] = 512
    graph["6"]["inputs"]["height"] = 512
    graph["7"]["inputs"]["noise_seed"] = 42
    graph["9"]["inputs"]["width"] = 512
    graph["9"]["inputs"]["height"] = 512
    graph["13"]["inputs"]["filename_prefix"] = f"isolated_038_{job}"

    payload = json.dumps({"prompt": graph, "client_id": f"isolated-{job}"}).encode()
    req = urllib.request.Request(
        f"{args.base}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    peak = before_gpu["used_mib"] if before_gpu else 0
    with urllib.request.urlopen(req, timeout=20) as response:
        accepted = json.loads(response.read().decode())
    prompt_id = accepted.get("prompt_id")
    if not prompt_id:
        raise SystemExit(f"FAIL Prompt abgelehnt: {accepted}")

    history = None
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        gpu = nvidia_smi()
        if gpu:
            peak = max(peak, gpu["used_mib"])
        current = get(f"{args.base}/history/{prompt_id}", timeout=5)
        if isinstance(current, dict) and prompt_id in current:
            history = current[prompt_id]
            break
        time.sleep(0.75)
    if history is None:
        raise SystemExit(f"FAIL Timeout nach {args.timeout}s")
    status = history.get("status") or {}
    if status.get("status_str") == "error":
        raise SystemExit(f"FAIL ComfyUI-Fehler: {status.get('messages')}")
    images = ((history.get("outputs") or {}).get("13") or {}).get("images") or []
    if not images:
        raise SystemExit("FAIL keine Ausgabe")
    filename = images[0]["filename"]
    source = OUTPUT / filename
    if not source.is_file():
        raise SystemExit(f"FAIL Datei fehlt: {source}")
    width, height = png_size(source)
    if (width, height) != (512, 512):
        raise SystemExit(f"FAIL Auflösung {width}x{height}")
    runtime = round(time.monotonic() - started, 3)
    after_gpu = nvidia_smi()
    result = {
        "ok": True,
        "comfy_version": "0.38.0",
        "prompt_id": prompt_id,
        "runtime_seconds": runtime,
        "png": str(source),
        "png_sha256": file_sha(source),
        "width": width,
        "height": height,
        "workflow_sha256": workflow_sha,
        "model_sha256": MODEL_SHA,
        "vram_before_mib": before_gpu,
        "vram_peak_used_mib": peak,
        "vram_after_mib": after_gpu,
        "argv": argv,
        "missing_flux": missing_flux,
        "missing_qwen21": missing_qwen,
    }
    marker = TREE / ".isolated-flux-pass.json"
    marker.write_text(json.dumps(result, indent=2) + "\n")
    out_dir = REPO / "benchmarks" / "comfyui-0.38-upgrade-20261001"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "isolated-flux.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if runtime > 180:
        print(f"WARN runtime {runtime}s deutlich über A12 64.9s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
