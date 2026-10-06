#!/usr/bin/env python3
"""Isolated A/B extras for hidden-gen: FAST 3-tool + compact content replay.

Does not change production settings except via quality_essay_ab restore.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

OUT = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/quality-hidden-gen-20260916")
OLLAMA = "http://127.0.0.1:11434"


def post(path: str, body: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        OLLAMA + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def replay_compact_head(stream: bool, max_tokens: int) -> dict:
    """Prove compact output is normal content, not reasoning_content."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are the component that summarizes a conversation when its context "
                "window is about to overflow. First, wrap your reasoning in an <analysis> "
                "block. Then produce <state_snapshot> XML."
            ),
        },
        {
            "role": "user",
            "content": "User asked to call memory_load then pdf_create then pdf_read. memory_load succeeded. First, reason in your <analysis> block. Then, produce the <state_snapshot> XML.",
        },
    ]
    t0 = time.perf_counter()
    if stream:
        req = urllib.request.Request(
            OLLAMA + "/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "local-quality",
                    "messages": messages,
                    "stream": True,
                    "max_tokens": max_tokens,
                    "think": False,
                    "enable_thinking": False,
                    "reasoning_effort": "none",
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        content = []
        reasoning = []
        finish = None
        usage = None
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk in {"", "[DONE]"}:
                    continue
                obj = json.loads(chunk)
                if obj.get("usage"):
                    usage = obj["usage"]
                choice = (obj.get("choices") or [{}])[0]
                finish = choice.get("finish_reason") or finish
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    content.append(delta["content"])
                if delta.get("reasoning_content"):
                    reasoning.append(delta["reasoning_content"])
        text = "".join(content)
        think = "".join(reasoning)
        return {
            "path": "/v1/chat/completions",
            "stream": True,
            "max_tokens": max_tokens,
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "finish_reason": finish,
            "usage": usage,
            "content_chars": len(text),
            "content_head": text[:240],
            "reasoning_chars": len(think),
        }
    body = post(
        "/v1/chat/completions",
        {
            "model": "local-quality",
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
            "think": False,
            "enable_thinking": False,
            "reasoning_effort": "none",
        },
        timeout=180,
    )
    msg = ((body.get("choices") or [{}])[0]).get("message") or {}
    return {
        "path": "/v1/chat/completions",
        "stream": False,
        "max_tokens": max_tokens,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "finish_reason": (body.get("choices") or [{}])[0].get("finish_reason"),
        "usage": body.get("usage"),
        "content_chars": len(msg.get("content") or ""),
        "content_head": (msg.get("content") or "")[:240],
        "reasoning_chars": len(str(msg.get("reasoning_content") or "")),
        "message_keys": sorted(msg.keys()),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for stream, max_tokens, name in (
        (True, 256, "D-stream-256"),
        (False, 256, "D-nostream-256"),
        (False, 1024, "F-1024"),
        (False, 1536, "F-1536"),
    ):
        print(f"replay {name}", flush=True)
        rec = replay_compact_head(stream, max_tokens)
        rec["variant"] = name
        rows.append(rec)
        print(json.dumps({k: rec[k] for k in rec if k != "content_head"}, ensure_ascii=False), flush=True)
    path = OUT / "replay-compact-head.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print("WROTE", path, flush=True)


if __name__ == "__main__":
    main()
