#!/usr/bin/env python3
"""QUALITY 6-tool E2E after Qwen 0.24.2. proceed_once only. No YOLO."""

from pathlib import Path

import quality_essay_e2e as e2e

PROJECT = "/home/mike/Projects/Linux Lokales KI"
e2e.OUT = Path(PROJECT) / "benchmarks" / "runtime-update-20260921"
e2e.PDF = f"{PROJECT}/.agent/tmp/runtime-update/qwen0242-e2e.pdf"
e2e.PNG = f"{PROJECT}/.agent/tmp/runtime-update/qwen0242-e2e.png"
e2e.PROMPT = f"""One session. Real MCP tools. Wait for permission. No YOLO. No /tmp.

There are exactly 6 tool calls. Do not skip number 5. Do not count memory_update as step 5.

1. mcp__local-tools__memory_load workspace="{PROJECT}"
2. mcp__local-tools__pdf_create output="{e2e.PDF}" title="Qwen 0.24.2 QUALITY E2E" text="Qwen Code 0.24.2 on Ollama 0.34.2. QUALITY 16384. FAST stays local-fast."
3. mcp__local-tools__pdf_read path="{e2e.PDF}"
4. mcp__local-tools__pdf_render path="{e2e.PDF}" output="{e2e.PNG}" page=1
5. mcp__local-tools__pdf_vision_qa path="{e2e.PDF}"
6. mcp__local-tools__memory_update workspace="{PROJECT}" summary="Qwen 0.24.2 QUALITY E2E completed in one serve session." decisions="Runtime update installed Qwen Code 0.24.2 with the three host patches. Ollama stays 0.34.2. No YOLO. FAST stays default." decision_title="Qwen 0.24.2 QUALITY E2E 2026-09-21"

After pdf_render you MUST call pdf_vision_qa before any memory_update. After each successful tool, call the next tool immediately. One short status sentence max between tools. Stop after memory_update.
"""

if __name__ == "__main__":
    try:
        e2e.main()
    finally:
        try:
            e2e.restore_default()
            print("[restore] default local-fast", flush=True)
        except Exception as exc:
            print(f"[restore] FAIL {exc}", flush=True)
