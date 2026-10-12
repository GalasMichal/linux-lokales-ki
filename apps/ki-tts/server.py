#!/usr/bin/env python3
"""Local-only Piper TTS (CPU). Binds 127.0.0.1 only — no LAN, no cloud."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from aiohttp import web

HOST = "127.0.0.1"
PORT = int(os.environ.get("KI_TTS_PORT", "8792"))
PIPER_BIN = Path(os.environ.get("KI_PIPER_BIN", "/srv/ai/apps/piper/piper/piper"))
VOICE_ROOT = Path(os.environ.get("KI_PIPER_VOICES", "/srv/ai/models/piper/voices"))

LANG_VOICES: dict[str, str] = {
    "de": "de_DE-thorsten-medium",
    "en": "en_US-lessac-medium",
    "pl": "pl_PL-gosia-medium",
    "es": "es_ES-davefx-medium",
    "fr": "fr_FR-siwis-medium",
    "tr": "tr_TR-dfki-medium",
}

MAX_TEXT_CHARS = 500


class AppError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def voice_model(lang: str) -> Path:
    code = lang.strip().lower()[:2]
    if code not in LANG_VOICES:
        raise AppError(f"Unsupported lang '{lang}'. Allowed: {', '.join(sorted(LANG_VOICES))}")
    base = VOICE_ROOT / code / LANG_VOICES[code]
    onnx = base.with_suffix(".onnx")
    if not onnx.is_file():
        raise AppError(f"Voice model missing for '{code}': {onnx}", 503)
    return onnx


def parse_synthesize(body: dict[str, Any]) -> tuple[str, str]:
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise AppError("text must be a non-empty string")
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        raise AppError(f"text must be at most {MAX_TEXT_CHARS} characters")
    lang = body.get("lang", "de")
    if not isinstance(lang, str):
        raise AppError("lang must be a string")
    return text, lang


def synthesize_wav(text: str, lang: str) -> bytes:
    if not PIPER_BIN.is_file():
        raise AppError(f"Piper binary not found: {PIPER_BIN}", 503)
    model = voice_model(lang)
    with tempfile.TemporaryDirectory(prefix="ki-tts-") as tmp:
        out = Path(tmp) / f"{uuid.uuid4().hex}.wav"
        proc = subprocess.run(
            [
                str(PIPER_BIN),
                "--model",
                str(model),
                "--output_file",
                str(out),
            ],
            input=text.encode("utf-8"),
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not out.is_file():
            detail = proc.stderr.decode("utf-8", errors="replace")[:400]
            raise AppError(f"Piper failed: {detail or proc.returncode}", 500)
        return out.read_bytes()


async def api_status(_request: web.Request) -> web.Response:
    voices: dict[str, str] = {}
    missing: list[str] = []
    for lang, name in LANG_VOICES.items():
        path = VOICE_ROOT / lang / f"{name}.onnx"
        voices[lang] = str(path)
        if not path.is_file():
            missing.append(lang)
    return web.json_response(
        {
            "ok": PIPER_BIN.is_file() and not missing,
            "host": HOST,
            "port": PORT,
            "piper_bin": str(PIPER_BIN),
            "voice_root": str(VOICE_ROOT),
            "languages": sorted(LANG_VOICES),
            "voices": voices,
            "missing": missing,
        }
    )


async def api_synthesize(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise AppError("Invalid JSON body")
    if not isinstance(body, dict):
        raise AppError("JSON body must be an object")
    text, lang = parse_synthesize(body)
    data = synthesize_wav(text, lang)
    return web.Response(body=data, content_type="audio/wav")


@web.middleware
async def error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except AppError as exc:
        return web.json_response({"error": exc.message}, status=exc.status)


def create_app() -> web.Application:
    app = web.Application(middlewares=[error_middleware])
    app.router.add_get("/api/tts/status", api_status)
    app.router.add_post("/api/tts/synthesize", api_synthesize)
    return app


def main() -> None:
    web.run_app(create_app(), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
