#!/usr/bin/env python3
"""Local-only desktop control surface for the AI stack.

The public UI binds to 127.0.0.1:8790. A second local-only listener on
127.0.0.1:8791 proxies the installed Qwen Code Web Shell. The proxy keeps
Qwen unmodified and only relaxes its frame policy for the local workplace UI.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import time
import uuid
import re
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


HOST = "127.0.0.1"
UI_PORT = int(os.environ.get("KI_WORKPLACE_PORT", "8790"))
QWEN_PROXY_PORT = int(os.environ.get("KI_QWEN_PROXY_PORT", "8791"))
QWEN_UPSTREAM = os.environ.get("KI_QWEN_UPSTREAM", "http://127.0.0.1:4170")
COMFY_URL = "http://127.0.0.1:8188"
OLLAMA_URL = "http://127.0.0.1:11434"

ROOT = Path(__file__).resolve().parent
WWW = ROOT / "www"
WORKFLOW_FILE = ROOT / "workflows" / "flux2-klein-t2i-api-v1.json"
COMFY_OUTPUT = Path("/srv/ai/apps/ComfyUI/output")
COMFY_MODELS = Path("/srv/ai/models/comfyui")
ARCHIVE_ROOT = Path("/mnt/ai-archive")
IMAGE_ARCHIVE = ARCHIVE_ROOT / "images" / "inbox"

WORKFLOW_ID = "flux2-klein-t2i-v1"
MODEL_FILES = {
    "diffusion_model": COMFY_MODELS / "diffusion_models" / "flux-2-klein-4b-fp8.safetensors",
    "text_encoder": COMFY_MODELS / "text_encoders" / "qwen_3_4b.safetensors",
    "vae": COMFY_MODELS / "vae" / "flux2-vae.safetensors",
}
ALLOWED_SIZES = {512, 768, 1024}
MAX_PROMPT_CHARS = 4000
IMAGE_TIMEOUT_SECONDS = 240
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
ALLOWED_QWEN_MODELS = {
    "local-fast",
    "local-fast(openai)",
    "openai:local-fast",
    "local-quality",
    "local-quality(openai)",
    "openai:local-quality",
}


class AppError(RuntimeError):
    """Expected, user-facing application error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@lru_cache(maxsize=8)
def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_image_request(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise AppError("Ungültige Anfrage.")

    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise AppError("Bitte einen Bildtext eingeben.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise AppError(f"Der Bildtext darf höchstens {MAX_PROMPT_CHARS} Zeichen haben.")

    try:
        width = int(data.get("width", 1024))
        height = int(data.get("height", 1024))
        seed = int(data.get("seed", 42))
    except (TypeError, ValueError) as exc:
        raise AppError("Breite, Höhe und Seed müssen ganze Zahlen sein.") from exc

    if width not in ALLOWED_SIZES or height not in ALLOWED_SIZES:
        raise AppError("Erlaubte Bildgrößen sind 512, 768 oder 1024 Pixel.")
    if not 0 <= seed <= 18_446_744_073_709_551_615:
        raise AppError("Der Seed liegt außerhalb des erlaubten Bereichs.")

    return {"prompt": prompt, "width": width, "height": height, "seed": seed}


def build_workflow(template: dict[str, Any], request: dict[str, Any], job_id: str) -> dict[str, Any]:
    workflow = deepcopy(template)
    workflow["4"]["inputs"]["text"] = request["prompt"]
    workflow["6"]["inputs"]["width"] = request["width"]
    workflow["6"]["inputs"]["height"] = request["height"]
    workflow["7"]["inputs"]["noise_seed"] = request["seed"]
    workflow["9"]["inputs"]["width"] = request["width"]
    workflow["9"]["inputs"]["height"] = request["height"]
    workflow["13"]["inputs"]["filename_prefix"] = f"ki_arbeitsplatz_{job_id}"
    return workflow


def safe_comfy_output(filename: str, subfolder: str) -> Path:
    if Path(filename).name != filename:
        raise AppError("ComfyUI lieferte einen ungültigen Dateinamen.")
    relative = Path(subfolder) / filename if subfolder else Path(filename)
    candidate = (COMFY_OUTPUT / relative).resolve()
    root = COMFY_OUTPUT.resolve()
    if candidate != root and root not in candidate.parents:
        raise AppError("ComfyUI-Ausgabepfad liegt außerhalb des erlaubten Ordners.")
    return candidate


def filter_local_qwen_providers(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AppError("Qwen lieferte einen ungültigen Provider-Status.")
    result = deepcopy(payload)
    safe_providers = []
    for provider in result.get("providers") or []:
        if not isinstance(provider, dict) or provider.get("authType") != "openai":
            continue
        safe_models = []
        for model in provider.get("models") or []:
            model_id = model.get("modelId") if isinstance(model, dict) else None
            base_url = model.get("baseUrl") if isinstance(model, dict) else None
            if model_id in ALLOWED_QWEN_MODELS and base_url == f"{OLLAMA_URL}/v1":
                safe_models.append(model)
        if safe_models:
            clean = deepcopy(provider)
            clean["models"] = safe_models
            safe_providers.append(clean)
    result["providers"] = safe_providers
    current = result.get("current") or {}
    if (
        current.get("authType") != "openai"
        or current.get("modelId") not in ALLOWED_QWEN_MODELS
        or current.get("baseUrl") != f"{OLLAMA_URL}/v1"
    ):
        raise AppError("Qwen ist nicht auf ein erlaubtes lokales Modell eingestellt.")
    return result


def validate_qwen_proxy_mutation(path: str, method: str, body: bytes) -> None:
    method = method.upper()
    if path.startswith("/workspace/auth/") and method != "GET":
        raise AppError("Cloud-/Provider-Anmeldung ist im lokalen Arbeitsplatz gesperrt.")

    is_model_switch = method == "POST" and re.fullmatch(r"/session/[^/]+/model", path)
    is_session_create = method == "POST" and path in {"/session", "/sessions"}
    if not (is_model_switch or is_session_create) or not body:
        return
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AppError("Ungültige Qwen-Anfrage.") from exc
    if not isinstance(payload, dict):
        raise AppError("Ungültige Qwen-Anfrage.")
    model_id = payload.get("modelId") if is_model_switch else payload.get("modelServiceId")
    if model_id is not None and model_id not in ALLOWED_QWEN_MODELS:
        raise AppError(f"Modell '{model_id}' ist gesperrt. Erlaubt sind nur FAST und QUALITY über Ollama.")


async def run_command(*args: str, timeout: float = 20) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise AppError(f"Zeitüberschreitung bei: {' '.join(args[:3])}")
    return proc.returncode, stdout.decode(errors="replace").strip(), stderr.decode(errors="replace").strip()


async def service_active(unit: str) -> bool:
    code, _, _ = await run_command("systemctl", "--user", "is-active", "--quiet", unit, timeout=5)
    return code == 0


async def service_action(action: str, unit: str) -> None:
    if action not in {"start", "stop"}:
        raise AppError("Interne Dienstaktion nicht erlaubt.")
    code, out, err = await run_command("systemctl", "--user", action, unit, timeout=30)
    if code != 0:
        raise AppError(err or out or f"{unit} konnte nicht {action} ausgeführt werden.")


async def wait_http(session: ClientSession, url: str, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            async with session.get(url, timeout=ClientTimeout(total=2)) as response:
                if response.status < 500:
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


async def get_json(session: ClientSession, url: str, *, timeout: float = 3) -> Any | None:
    try:
        async with session.get(url, timeout=ClientTimeout(total=timeout)) as response:
            if response.status != 200:
                return None
            return await response.json()
    except Exception:
        return None


async def unload_ollama(session: ClientSession) -> list[str]:
    ps = await get_json(session, f"{OLLAMA_URL}/api/ps") or {}
    unloaded: list[str] = []
    for item in ps.get("models") or []:
        model = item.get("name") or item.get("model")
        if not isinstance(model, str) or not model:
            continue
        payload = {"model": model, "keep_alive": 0}
        async with session.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=ClientTimeout(total=30),
        ) as response:
            if response.status >= 300:
                text = await response.text()
                raise AppError(f"Ollama-Modell {model} konnte nicht entladen werden: {text[:300]}")
        unloaded.append(model)

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        current = await get_json(session, f"{OLLAMA_URL}/api/ps") or {}
        if not (current.get("models") or []):
            return unloaded
        await asyncio.sleep(0.5)
    raise AppError("Ollama meldet nach 20 Sekunden weiterhin ein geladenes Modell.")


async def ensure_agent_mode(app: web.Application) -> dict[str, Any]:
    if await service_active("comfyui.service"):
        await service_action("stop", "comfyui.service")
    await service_action("start", "qwen-code-web.service")
    ready = await wait_http(app["session"], f"{QWEN_UPSTREAM}/health", 20)
    if not ready:
        raise AppError("Qwen Code Web ist nach 20 Sekunden nicht erreichbar.")
    return {"ok": True, "mode": "agent", "message": "Agent bereit. Bilder-KI wurde beendet."}


async def ensure_image_mode(app: web.Application) -> dict[str, Any]:
    unloaded = await unload_ollama(app["session"])
    await service_action("start", "comfyui.service")
    ready = await wait_http(app["session"], f"{COMFY_URL}/system_stats", 45)
    if not ready:
        raise AppError("ComfyUI ist nach 45 Sekunden nicht erreichbar.")
    return {
        "ok": True,
        "mode": "images",
        "unloaded_models": unloaded,
        "message": "Bilder-KI bereit. Ollama-Modelle wurden entladen.",
    }


async def cleanup_gpu(app: web.Application) -> dict[str, Any]:
    """Stop GPU consumers after the last desktop window closes."""
    stopped: list[str] = []
    if await service_active("qwen-code-web.service"):
        await service_action("stop", "qwen-code-web.service")
        stopped.append("qwen-code-web.service")
    if await service_active("comfyui.service"):
        await service_action("stop", "comfyui.service")
        stopped.append("comfyui.service")
    unloaded = await unload_ollama(app["session"])
    await asyncio.sleep(1)
    return {
        "ok": True,
        "message": "GPU-Verbraucher wurden sauber beendet.",
        "stopped_services": stopped,
        "unloaded_models": unloaded,
        "gpu": await gpu_status(),
    }


async def gpu_status() -> dict[str, Any] | None:
    code, out, _ = await run_command(
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
        timeout=5,
    )
    if code != 0 or not out:
        return None
    parts = [part.strip() for part in out.splitlines()[0].split(",")]
    if len(parts) != 5:
        return None
    return {
        "name": parts[0],
        "total_mib": int(parts[1]),
        "used_mib": int(parts[2]),
        "free_mib": int(parts[3]),
        "utilization_percent": int(parts[4]),
    }


def memory_status() -> dict[str, float]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0])
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    return {
        "total_gib": round(total / 1024 / 1024, 2),
        "used_gib": round((total - available) / 1024 / 1024, 2),
        "swap_total_gib": round(swap_total / 1024 / 1024, 2),
        "swap_used_gib": round((swap_total - swap_free) / 1024 / 1024, 2),
    }


def disk_status(path: str) -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {
        "path": path,
        "total_gib": round(usage.total / 1024**3, 1),
        "used_gib": round(usage.used / 1024**3, 1),
        "free_gib": round(usage.free / 1024**3, 1),
    }


@web.middleware
async def local_only(request: web.Request, handler):
    if request.remote not in {"127.0.0.1", "::1"}:
        raise web.HTTPForbidden(text="Nur localhost ist erlaubt.")
    return await handler(request)


@web.middleware
async def security_headers(request: web.Request, handler):
    response = await handler(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: http://127.0.0.1:8188; "
        f"connect-src 'self' http://127.0.0.1:8188 http://127.0.0.1:{QWEN_PROXY_PORT}; "
        f"frame-src http://127.0.0.1:8188 http://127.0.0.1:{QWEN_PROXY_PORT}; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    return response


async def index(request: web.Request) -> web.Response:
    return web.FileResponse(WWW / "index.html")


async def api_status(request: web.Request) -> web.Response:
    app = request.app
    session = app["session"]
    version, ps = await asyncio.gather(
        get_json(session, f"{OLLAMA_URL}/api/version"),
        get_json(session, f"{OLLAMA_URL}/api/ps"),
    )
    services = await asyncio.gather(
        service_active("qwen-code-web.service"),
        service_active("comfyui.service"),
        service_active("open-webui.service"),
    )
    qwen_http, comfy_http, chat_http, gpu = await asyncio.gather(
        wait_http(session, f"{QWEN_UPSTREAM}/health", 1),
        wait_http(session, f"{COMFY_URL}/system_stats", 1),
        wait_http(session, "http://127.0.0.1:3000/health", 1),
        gpu_status(),
    )
    models = []
    for item in (ps or {}).get("models") or []:
        name = item.get("name") or item.get("model")
        if name:
            models.append(name)
    payload = {
        "ok": True,
        "ollama": {"running": version is not None, "version": (version or {}).get("version"), "models": models},
        "qwen": {"service": services[0], "ready": qwen_http, "url": QWEN_UPSTREAM},
        "comfyui": {"service": services[1], "ready": comfy_http, "url": COMFY_URL},
        "chat": {"service": services[2], "ready": chat_http, "url": "http://127.0.0.1:3000"},
        "gpu": gpu,
        "memory": memory_status(),
        "storage": {"active": disk_status("/srv/ai"), "archive": disk_status(str(ARCHIVE_ROOT))},
        "image_job_running": app["image_lock"].locked(),
        "bindings": [
            "127.0.0.1:11434",
            "127.0.0.1:3000",
            "127.0.0.1:4170",
            "127.0.0.1:8188",
            f"127.0.0.1:{UI_PORT}",
            f"127.0.0.1:{QWEN_PROXY_PORT}",
        ],
    }
    return web.json_response(payload)


async def api_mode(request: web.Request) -> web.Response:
    mode = request.match_info["mode"]
    try:
        if mode == "agent":
            payload = await ensure_agent_mode(request.app)
        elif mode == "images":
            payload = await ensure_image_mode(request.app)
        else:
            raise web.HTTPNotFound()
        return web.json_response(payload)
    except AppError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def api_gpu_cleanup(request: web.Request) -> web.Response:
    # If an image is still rendering or its manifest is being written, wait for
    # that protected job to finish before releasing ComfyUI and Ollama.
    try:
        async with request.app["image_lock"]:
            payload = await cleanup_gpu(request.app)
        return web.json_response(payload)
    except AppError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)


async def image_generate(request: web.Request) -> web.Response:
    lock: asyncio.Lock = request.app["image_lock"]
    if lock.locked():
        return web.json_response(
            {"ok": False, "error": "Es läuft bereits ein Bildauftrag. Bitte warten."},
            status=409,
        )

    try:
        data = parse_image_request(await request.json())
    except (json.JSONDecodeError, web.HTTPBadRequest, AppError) as exc:
        message = str(exc) if isinstance(exc, AppError) else "Ungültige JSON-Anfrage."
        return web.json_response({"ok": False, "error": message}, status=400)

    async with lock:
        started_monotonic = time.monotonic()
        started_at = utc_now()
        job_id = uuid.uuid4().hex[:12]
        try:
            await ensure_image_mode(request.app)
            if not WORKFLOW_FILE.is_file():
                raise AppError(f"Workflow fehlt: {WORKFLOW_FILE}")
            template = json.loads(WORKFLOW_FILE.read_text())
            workflow = build_workflow(template, data, job_id)

            session = request.app["session"]
            async with session.post(
                f"{COMFY_URL}/prompt",
                json={"prompt": workflow, "client_id": f"ki-arbeitsplatz-{job_id}"},
                timeout=ClientTimeout(total=20),
            ) as response:
                result = await response.json(content_type=None)
                if response.status >= 300 or not result.get("prompt_id"):
                    raise AppError(f"ComfyUI hat den Auftrag abgelehnt: {result}")
            prompt_id = result["prompt_id"]

            history: dict[str, Any] | None = None
            deadline = time.monotonic() + IMAGE_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                current = await get_json(session, f"{COMFY_URL}/history/{quote(prompt_id)}", timeout=5)
                if current and prompt_id in current:
                    history = current[prompt_id]
                    break
                await asyncio.sleep(0.75)
            if history is None:
                raise AppError(f"Bildauftrag überschritt {IMAGE_TIMEOUT_SECONDS} Sekunden.")

            status = history.get("status") or {}
            if status.get("status_str") == "error":
                messages = status.get("messages") or []
                raise AppError(f"ComfyUI-Fehler: {str(messages)[-1200:]}")

            images = ((history.get("outputs") or {}).get("13") or {}).get("images") or []
            if not images:
                raise AppError("ComfyUI meldet Abschluss, aber keine Bilddatei.")

            if not os.path.ismount(ARCHIVE_ROOT):
                raise AppError("Archiv-HDD ist nicht eingehängt. Bild wird nicht in den falschen Datenträger geschrieben.")

            day = datetime.now().strftime("%Y-%m-%d")
            destination = IMAGE_ARCHIVE / day / job_id
            destination.mkdir(parents=True, exist_ok=False)
            copied: list[dict[str, str]] = []
            previews: list[str] = []
            for image in images:
                filename = image.get("filename", "")
                subfolder = image.get("subfolder", "")
                source = safe_comfy_output(filename, subfolder)
                if not source.is_file():
                    raise AppError(f"ComfyUI-Ausgabe fehlt: {source}")
                target = destination / filename
                shutil.copy2(source, target)
                copied.append({"source": str(source), "archive": str(target)})
                previews.append(
                    f"{COMFY_URL}/view?filename={quote(filename)}&subfolder={quote(subfolder)}&type=output"
                )

            missing = [str(path) for path in MODEL_FILES.values() if not path.is_file()]
            if missing:
                raise AppError("Modellbestand ist unvollständig: " + ", ".join(missing))
            model_hashes = {
                name: await asyncio.to_thread(sha256_file, str(path))
                for name, path in MODEL_FILES.items()
            }
            workflow_hash = hashlib.sha256(canonical_json(template)).hexdigest()
            finished_at = utc_now()
            runtime = round(time.monotonic() - started_monotonic, 3)
            manifest = {
                "manifest_version": 1,
                "job_id": job_id,
                "comfy_prompt_id": prompt_id,
                "workflow_id": WORKFLOW_ID,
                "workflow_sha256": workflow_hash,
                "model_files": {name: str(path) for name, path in MODEL_FILES.items()},
                "model_sha256": model_hashes,
                "prompt": data["prompt"],
                "seed": data["seed"],
                "width": data["width"],
                "height": data["height"],
                "batch": 1,
                "steps": 4,
                "cfg": 1.0,
                "sampler": "euler",
                "started_at": started_at,
                "finished_at": finished_at,
                "runtime_seconds": runtime,
                "outputs": copied,
            }
            manifest_file = destination / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            return web.json_response(
                {
                    "ok": True,
                    "job_id": job_id,
                    "runtime_seconds": runtime,
                    "archive_directory": str(destination),
                    "manifest": str(manifest_file),
                    "previews": previews,
                }
            )
        except AppError as exc:
            return web.json_response({"ok": False, "job_id": job_id, "error": str(exc)}, status=500)
        except Exception as exc:
            return web.json_response(
                {"ok": False, "job_id": job_id, "error": f"Unerwarteter Fehler: {type(exc).__name__}: {exc}"},
                status=500,
            )


def filtered_request_headers(request: web.Request) -> dict[str, str]:
    return {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in HOP_BY_HOP and name.lower() != "host"
    }


def copy_proxy_headers(upstream, response: web.StreamResponse) -> None:
    for name, value in upstream.headers.items():
        lower = name.lower()
        if lower in HOP_BY_HOP or lower in {"x-frame-options", "content-security-policy"}:
            continue
        response.headers.add(name, value)
    csp = upstream.headers.get("Content-Security-Policy")
    if csp:
        csp = csp.replace(
            "frame-ancestors 'none'",
            f"frame-ancestors http://127.0.0.1:{UI_PORT}",
        )
        response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"


async def qwen_websocket_proxy(request: web.Request, target: str) -> web.WebSocketResponse:
    requested_protocols = [
        item.strip()
        for item in request.headers.get("Sec-WebSocket-Protocol", "").split(",")
        if item.strip()
    ]
    browser_ws = web.WebSocketResponse(protocols=requested_protocols, heartbeat=30)
    await browser_ws.prepare(request)
    headers = filtered_request_headers(request)
    for name in list(headers):
        if name.lower().startswith("sec-websocket-"):
            headers.pop(name)

    try:
        upstream_ws = await request.app["proxy_session"].ws_connect(
            target,
            protocols=requested_protocols,
            headers=headers,
            heartbeat=30,
            timeout=20,
        )
    except Exception as exc:
        await browser_ws.close(code=1011, message=f"Qwen-Verbindung fehlgeschlagen: {exc}".encode()[:120])
        return browser_ws

    async def browser_to_upstream() -> None:
        async for message in browser_ws:
            if message.type == WSMsgType.TEXT:
                await upstream_ws.send_str(message.data)
            elif message.type == WSMsgType.BINARY:
                await upstream_ws.send_bytes(message.data)
            elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                break

    async def upstream_to_browser() -> None:
        async for message in upstream_ws:
            if message.type == WSMsgType.TEXT:
                await browser_ws.send_str(message.data)
            elif message.type == WSMsgType.BINARY:
                await browser_ws.send_bytes(message.data)
            elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                break

    tasks = [asyncio.create_task(browser_to_upstream()), asyncio.create_task(upstream_to_browser())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*done, *pending, return_exceptions=True)
    await upstream_ws.close()
    await browser_ws.close()
    return browser_ws


async def qwen_proxy(request: web.Request) -> web.StreamResponse:
    target = f"{QWEN_UPSTREAM}{request.rel_url}"
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await qwen_websocket_proxy(request, target)

    body = await request.read()
    try:
        validate_qwen_proxy_mutation(request.path, request.method, body)
    except AppError as exc:
        return web.json_response({"error": str(exc), "code": "local_provider_only"}, status=403)

    if request.method == "GET" and request.path == "/workspace/auth/providers":
        return web.json_response(
            {
                "v": 1,
                "workspaceCwd": "/srv/ai/workspaces",
                "providers": [],
                "groups": [],
                "localOnly": True,
            }
        )

    special_provider_status = request.method == "GET" and request.path == "/workspace/providers"
    headers = filtered_request_headers(request)
    if special_provider_status:
        headers.pop("Accept-Encoding", None)
    async with request.app["proxy_session"].request(
        request.method,
        target,
        headers=headers,
        data=body if body else None,
        allow_redirects=False,
        timeout=ClientTimeout(total=None, sock_connect=10, sock_read=None),
    ) as upstream:
        if special_provider_status:
            raw = await upstream.read()
            if upstream.status != 200:
                return web.Response(status=upstream.status, body=raw, content_type="application/json")
            try:
                filtered = filter_local_qwen_providers(json.loads(raw))
            except (json.JSONDecodeError, AppError) as exc:
                return web.json_response({"error": str(exc), "code": "local_provider_filter_failed"}, status=503)
            return web.json_response(filtered)
        response = web.StreamResponse(status=upstream.status, reason=upstream.reason)
        copy_proxy_headers(upstream, response)
        await response.prepare(request)
        async for chunk in upstream.content.iter_chunked(64 * 1024):
            await response.write(chunk)
        await response.write_eof()
        return response


def create_ui_app(session: ClientSession) -> web.Application:
    app = web.Application(middlewares=[local_only, security_headers], client_max_size=64 * 1024)
    app["session"] = session
    app["image_lock"] = asyncio.Lock()
    app.router.add_get("/", index)
    app.router.add_get("/index.html", index)
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/mode/{mode}", api_mode)
    app.router.add_post("/api/gpu/cleanup", api_gpu_cleanup)
    app.router.add_post("/api/images/generate", image_generate)
    return app


def create_proxy_app(session: ClientSession) -> web.Application:
    app = web.Application(middlewares=[local_only], client_max_size=16 * 1024 * 1024)
    app["proxy_session"] = session
    app.router.add_route("*", "/{tail:.*}", qwen_proxy)
    return app


async def async_main() -> None:
    if HOST in {"0.0.0.0", "::", ""}:
        raise SystemExit("KI-Arbeitsplatz bindet ausschließlich an 127.0.0.1")
    timeout = ClientTimeout(total=60)
    async with ClientSession(timeout=timeout) as session, ClientSession(auto_decompress=False) as proxy_session:
        ui_runner = web.AppRunner(create_ui_app(session), access_log=None)
        proxy_runner = web.AppRunner(create_proxy_app(proxy_session), access_log=None)
        await ui_runner.setup()
        await proxy_runner.setup()
        await web.TCPSite(ui_runner, HOST, UI_PORT).start()
        await web.TCPSite(proxy_runner, HOST, QWEN_PROXY_PORT).start()
        print(f"KI-Arbeitsplatz: http://{HOST}:{UI_PORT}", flush=True)
        print(f"Qwen-Einbettungsproxy: http://{HOST}:{QWEN_PROXY_PORT}", flush=True)

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()
        await proxy_runner.cleanup()
        await ui_runner.cleanup()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
