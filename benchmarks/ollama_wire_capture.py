#!/usr/bin/env python3
"""Localhost Ollama capture proxy: 127.0.0.1:11436 → 11434.

Captures stream stats (content vs reasoning vs tool_calls) without API keys.
Bodies of messages are summarized; generated text heads are kept for diagnosis.
"""

from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

UPSTREAM = "http://127.0.0.1:11434"
HOST = "127.0.0.1"
PORT = 11436
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ollama-wire-capture")
REDACT = ("authorization", "x-api-key", "api-key")


def msg_summary(msg: dict) -> dict:
    content = msg.get("content")
    if isinstance(content, str):
        text = content
    else:
        text = json.dumps(content, ensure_ascii=False) if content is not None else ""
    rec = {
        "role": msg.get("role"),
        "content_chars": len(text),
        "content_head": text[:240],
        "has_tool_calls": bool(msg.get("tool_calls")),
        "tool_call_name": None,
        "reasoning_chars": len(str(msg.get("reasoning_content") or msg.get("reasoning") or "")),
    }
    tcs = msg.get("tool_calls") or []
    if tcs and isinstance(tcs[0], dict):
        fn = tcs[0].get("function") or {}
        rec["tool_call_name"] = fn.get("name")
        rec["tool_call_arg_chars"] = len(str(fn.get("arguments") or ""))
    if msg.get("tool_call_id"):
        rec["tool_call_id"] = msg.get("tool_call_id")
    if msg.get("name"):
        rec["name"] = msg.get("name")
    return rec


def request_summary(body: dict) -> dict:
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
        "max_tokens": body.get("max_tokens"),
        "think": body.get("think"),
        "enable_thinking": body.get("enable_thinking"),
        "reasoning": body.get("reasoning"),
        "reasoning_effort": body.get("reasoning_effort"),
        "tool_count": len(tools),
        "tool_names": names,
        "message_count": len(msgs) if isinstance(msgs, list) else None,
        "messages": [msg_summary(m) for m in msgs] if isinstance(msgs, list) else [],
        "extra_keys": sorted(
            k
            for k in body.keys()
            if k not in {"model", "messages", "tools", "stream", "stream_options"}
        ),
    }


def parse_sse(payload: bytes) -> dict:
    content = []
    reasoning = []
    tool_names = []
    tool_args = []
    finish = None
    usage = None
    chunk_count = 0
    keys_seen = set()
    delta_keys = set()
    for line in payload.decode("utf-8", "replace").splitlines():
        if not line.startswith("data:"):
            continue
        chunk = line[5:].strip()
        if chunk in {"", "[DONE]"}:
            continue
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        chunk_count += 1
        keys_seen.update(obj.keys())
        if obj.get("usage"):
            usage = obj.get("usage")
        choice = (obj.get("choices") or [{}])[0]
        finish = choice.get("finish_reason") or finish
        delta = choice.get("delta") or choice.get("message") or {}
        if isinstance(delta, dict):
            delta_keys.update(delta.keys())
            if delta.get("content"):
                content.append(str(delta.get("content")))
            for key in ("reasoning_content", "reasoning"):
                if delta.get(key):
                    reasoning.append(str(delta.get(key)))
            for tc in delta.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                if fn.get("name"):
                    tool_names.append(fn.get("name"))
                if fn.get("arguments"):
                    tool_args.append(str(fn.get("arguments")))
    text = "".join(content)
    think = "".join(reasoning)
    args = "".join(tool_args)
    return {
        "chunk_count": chunk_count,
        "finish_reason": finish,
        "usage": usage,
        "response_keys": sorted(keys_seen),
        "delta_keys": sorted(delta_keys),
        "content_chars": len(text),
        "content_head": text[:400],
        "content_tail": text[-400:] if len(text) > 400 else text,
        "reasoning_chars": len(think),
        "reasoning_head": think[:400],
        "tool_call_names": tool_names,
        "tool_arg_chars": len(args),
        "tool_arg_head": args[:300],
    }


class Handler(BaseHTTPRequestHandler):
    seq = 0

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
        t0 = time.perf_counter()
        req = Request(UPSTREAM + self.path, data=raw or None, method=self.command, headers=headers)
        try:
            with urlopen(req, timeout=600) as resp:
                payload = resp.read()
                elapsed = round(time.perf_counter() - t0, 3)
                if raw and self.path.rstrip("/").endswith(("/chat/completions", "/chat", "/api/chat")):
                    Handler.seq += 1
                    rec = {
                        "seq": Handler.seq,
                        "ts": time.strftime("%H:%M:%S"),
                        "path": self.path,
                        "elapsed_s": elapsed,
                        "status": resp.status,
                    }
                    try:
                        body = json.loads(raw.decode())
                        rec["request"] = request_summary(body) if isinstance(body, dict) else {}
                    except Exception as exc:
                        rec["request_error"] = str(exc)
                    rec["response"] = parse_sse(payload)
                    OUT.mkdir(parents=True, exist_ok=True)
                    with (OUT / "wire.jsonl").open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    (OUT / f"turn-{Handler.seq:02d}.json").write_text(
                        json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    print(
                        f"[turn {Handler.seq}] {elapsed}s finish={rec['response'].get('finish_reason')} "
                        f"content={rec['response'].get('content_chars')} "
                        f"reasoning={rec['response'].get('reasoning_chars')} "
                        f"tools={rec['response'].get('tool_call_names')} "
                        f"args={rec['response'].get('tool_arg_chars')}",
                        flush=True,
                    )
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
    OUT.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"capture-proxy {HOST}:{PORT} -> {UPSTREAM} out={OUT}", flush=True)
    httpd.serve_forever()
