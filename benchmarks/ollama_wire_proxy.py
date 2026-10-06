#!/usr/bin/env python3
"""Localhost-only Ollama request logger. Forwards 127.0.0.1:11436 → 11434.

Logs request keys (tools, think, reasoning) without message bodies or secrets.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

UPSTREAM = "http://127.0.0.1:11434"
LOG = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ollama-wire.jsonl")
DUMP = Path("/tmp/ollama-last-request.json")
RESP_DUMP = Path("/tmp/ollama-last-response-meta.json")
HOST = "127.0.0.1"
PORT = 11436
REDACT = ("authorization", "x-api-key", "api-key")


def summarize(body: dict) -> dict:
    tools = body.get("tools") or []
    names = []
    for t in tools:
        if isinstance(t, dict):
            fn = t.get("function") if isinstance(t.get("function"), dict) else t
            names.append((fn or {}).get("name") or t.get("name"))
    msgs = body.get("messages") or []
    return {
        "model": body.get("model"),
        "stream": body.get("stream"),
        "tool_choice": body.get("tool_choice"),
        "tool_count": len(tools),
        "tool_names": names,
        "memory_load_visible": any(
            n and "memory_load" in str(n) for n in names
        ),
        "think": body.get("think"),
        "enable_thinking": body.get("enable_thinking"),
        "reasoning": body.get("reasoning"),
        "reasoning_effort": body.get("reasoning_effort"),
        "chat_template_kwargs": body.get("chat_template_kwargs"),
        "extra_keys": sorted(
            k
            for k in body.keys()
            if k
            not in {
                "model",
                "messages",
                "tools",
                "stream",
                "stream_options",
                "options",
            }
        ),
        "message_count": len(msgs) if isinstance(msgs, list) else None,
        "message_roles": [
            {
                "role": (m or {}).get("role"),
                "chars": len(str((m or {}).get("content") or "")),
            }
            for m in (msgs if isinstance(msgs, list) else [])
        ],
        "prompt_chars": sum(
            len(str((m or {}).get("content") or ""))
            for m in (msgs if isinstance(msgs, list) else [])
        ),
        "options": body.get("options"),
        "max_tokens": body.get("max_tokens"),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("proxy: " + (fmt % args) + "\n")

    def do_GET(self) -> None:
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def do_HEAD(self) -> None:
        self._forward()

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in REDACT and k.lower() != "host"
        }
        if raw and self.path.rstrip("/").endswith(
            ("/chat/completions", "/chat", "/api/chat")
        ):
            try:
                body = json.loads(raw.decode())
                rec = {
                    "path": self.path,
                    "summary": summarize(body) if isinstance(body, dict) else {},
                }
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with LOG.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if isinstance(body, dict):
                    DUMP.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                sys.stderr.write(f"proxy log skip: {exc}\n")
        req = Request(
            UPSTREAM + self.path,
            data=raw or None,
            method=self.command,
            headers=headers,
        )
        try:
            with urlopen(req, timeout=600) as resp:
                payload = resp.read()
                try:
                    text = payload.decode("utf-8", "replace")
                    tool_names = []
                    finish = None
                    content_head = ""
                    for line in text.splitlines():
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk in {"", "[DONE]"}:
                            continue
                        try:
                            obj = json.loads(chunk)
                        except Exception:
                            continue
                        choice = (obj.get("choices") or [{}])[0]
                        finish = choice.get("finish_reason") or finish
                        delta = choice.get("delta") or choice.get("message") or {}
                        if delta.get("content"):
                            content_head += str(delta.get("content"))
                        for tc in delta.get("tool_calls") or []:
                            fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                            name = fn.get("name") or (
                                tc.get("name") if isinstance(tc, dict) else None
                            )
                            if name:
                                tool_names.append(name)
                    RESP_DUMP.write_text(
                        json.dumps(
                            {
                                "bytes": len(payload),
                                "tool_calls": tool_names,
                                "finish_reason": finish,
                                "content_head": content_head[:500],
                            },
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                except Exception as exc:
                    sys.stderr.write(f"proxy resp log skip: {exc}\n")
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in {"transfer-encoding", "connection"}:
                        continue
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(payload)
        except Exception as exc:
            self.send_error(502, str(exc)[:200])


if __name__ == "__main__":
    LOG.parent.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ollama-wire-proxy {HOST}:{PORT} -> {UPSTREAM} log={LOG}", flush=True)
    httpd.serve_forever()
