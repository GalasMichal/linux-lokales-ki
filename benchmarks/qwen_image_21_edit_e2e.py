#!/usr/bin/env python3
"""Live EDIT-1 / EDIT-1024 / MULTI / PATH / SIZE / TYPE / MCP / FLUX regression."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from mcp import Client
import asyncio


PROJECT = Path("/home/mike/Projects/Linux Lokales KI")
OUT = PROJECT / "benchmarks" / "qwen-image-21-edit-20260921"
SOURCE = PROJECT / "benchmarks" / "qwen-image-21-smoke-20260921" / "input" / "source.png"
WORK = "http://127.0.0.1:8790"
MCP = "http://127.0.0.1:8765/mcp"
FLUX_SHA = "d9d752d52b1430bd3756908885146daea41279e29a7b6e3a9e05705572f39953"
FLUX_DIT = "97ed34fe"
EDIT_TIMEOUT = 480


def http_json(url: str, payload: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            body = {"error": raw or str(exc)}
        return exc.code, body


def sh(*args: str) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    return (proc.stdout or proc.stderr or "").strip()


def gpu() -> dict:
    line = sh(
        "nvidia-smi",
        "--query-gpu=memory.used,memory.free",
        "--format=csv,noheader,nounits",
    )
    parts = [p.strip() for p in line.split(",")]
    return {"used_mib": int(parts[0]), "free_mib": int(parts[1])}


def unit(name: str) -> str:
    return sh("systemctl", "--user", "is-active", name) or "unknown"


def png_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    return path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cleanup_state() -> dict:
    return {
        "comfyui": unit("comfyui.service"),
        "qwen": unit("qwen-code-web.service"),
        "gpu": gpu(),
        "staged": sorted(Path("/srv/ai/apps/ComfyUI-0.37.0/input").glob("ki_edit_*")),
    }


async def mcp_edit(arguments: dict) -> dict:
    async with Client(MCP) as client:
        result = await client.call_tool("edit_image", arguments)
        structured = result.structured_content or {}
        actual = structured.get("result", structured)
        return {"is_error": result.is_error, "result": actual}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"cases": {}, "ok": True}
    workspace = Path("/srv/ai/workspaces/qwen-image-21-edit-tests")
    workspace.mkdir(parents=True, exist_ok=True)
    input_png = workspace / "apple.png"
    ref_png = workspace / "ref.png"
    shutil.copy2(SOURCE, input_png)
    shutil.copy2(SOURCE, ref_png)
    input_hash = sha256(input_png)

    def record(name: str, payload: dict, ok: bool) -> None:
        entry = {**payload, "ok": bool(ok)}
        report["cases"][name] = entry
        if not ok:
            report["ok"] = False
        (OUT / f"{name}.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n")

    # PATH
    status, body = http_json(f"{WORK}/api/images/edit", {"instruction": "x", "input_path": "/etc/hostname"})
    record("PATH", {"status": status, "body": body, "comfy": unit("comfyui.service")}, status == 400 and unit("comfyui.service") != "active")

    # TYPE
    bad = workspace / "notes.txt"
    bad.write_text("not an image\n")
    status, body = http_json(f"{WORK}/api/images/edit", {"instruction": "x", "input_path": str(bad)})
    record("TYPE", {"status": status, "body": body}, status == 400)

    # SIZE
    huge = workspace / "huge.png"
    huge.write_bytes(input_png.read_bytes() + b"\x00" * (25 * 1024 * 1024 + 1))
    status, body = http_json(f"{WORK}/api/images/edit", {"instruction": "x", "input_path": str(huge)})
    huge.unlink()
    record("SIZE", {"status": status, "body": body}, status == 400)

    instruction = "Change only the apple from red to bright green. Keep everything else unchanged."

    # EDIT-1 / 1024
    t0 = time.monotonic()
    status, body = http_json(
        f"{WORK}/api/images/edit",
        {
            "instruction": instruction,
            "input_path": str(input_png),
            "width": 1024,
            "height": 1024,
            "seed": 42,
        },
        timeout=EDIT_TIMEOUT,
    )
    runtime = round(time.monotonic() - t0, 3)
    output = Path(body.get("output_path") or "")
    manifest = Path(body.get("manifest_path") or body.get("manifest") or "")
    cleanup = cleanup_state()
    ok = (
        status == 200
        and body.get("ok") is True
        and png_ok(output)
        and manifest.is_file()
        and body.get("output_sha256") != input_hash
        and body.get("workflow_id") == "qwen-image-21-edit-v1"
        and runtime < 420
        and cleanup["comfyui"] != "active"
        and cleanup["qwen"] != "active"
        and not cleanup["staged"]
    )
    record(
        "EDIT-1024",
        {
            "status": status,
            "body": body,
            "runtime": runtime,
            "cleanup": {**cleanup, "staged": [str(p) for p in cleanup["staged"]]},
        },
        ok,
    )

    # MULTI
    t0 = time.monotonic()
    status, body = http_json(
        f"{WORK}/api/images/edit",
        {
            "instruction": instruction,
            "input_path": str(input_png),
            "reference_paths": [str(ref_png)],
            "width": 512,
            "height": 512,
            "seed": 42,
        },
        timeout=EDIT_TIMEOUT,
    )
    runtime = round(time.monotonic() - t0, 3)
    output = Path(body.get("output_path") or "")
    ok = bool(status == 200 and body.get("ok") is True and png_ok(output) and body.get("reference_sha256"))
    record("MULTI", {"status": status, "body": body, "runtime": runtime}, ok)

    # MCP
    mcp_payload = asyncio.run(
        mcp_edit(
            {
                "instruction": instruction,
                "input_path": str(input_png),
                "width": 512,
                "height": 512,
                "seed": 42,
            }
        )
    )
    actual = mcp_payload.get("result") or {}
    output = Path(actual.get("output_path") or "")
    ok = (
        not mcp_payload.get("is_error")
        and actual.get("ok") is True
        and png_ok(output)
        and actual.get("workflow_id") == "qwen-image-21-edit-v1"
        and isinstance(actual.get("quantization"), dict)
    )
    record("MCP", mcp_payload, ok)

    # FLUX regression
    t0 = time.monotonic()
    status, body = http_json(
        f"{WORK}/api/images/generate",
        {
            "prompt": "Ein kleiner roter Wuerfel auf einem neutralen grauen Hintergrund, Studiofotografie",
            "width": 512,
            "height": 512,
            "seed": 42,
        },
        timeout=300,
    )
    runtime = round(time.monotonic() - t0, 3)
    http_json(f"{WORK}/api/gpu/cleanup", {}, timeout=120)
    flux_ok = status == 200 and body.get("ok") is True
    manifest_path = Path(body.get("manifest") or "")
    workflow_sha = None
    model_sha = None
    if manifest_path.is_file():
        man = json.loads(manifest_path.read_text())
        workflow_sha = man.get("workflow_sha256")
        model_sha = (man.get("model_sha256") or {}).get("diffusion_model", "")
        flux_ok = flux_ok and workflow_sha == FLUX_SHA and str(model_sha).startswith(FLUX_DIT)
    record(
        "FLUX",
        {"status": status, "body": body, "runtime": runtime, "workflow_sha": workflow_sha, "dit_prefix": str(model_sha)[:16]},
        flux_ok,
    )

    cleanup = cleanup_state()
    report["cleanup_final"] = {**cleanup, "staged": [str(p) for p in cleanup["staged"]]}
    report["health"] = http_json("http://127.0.0.1:8765/health")[1]
    (OUT / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": report["ok"], "cases": {k: v["ok"] for k, v in report["cases"].items()}}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
