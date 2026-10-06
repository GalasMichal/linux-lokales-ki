#!/usr/bin/env python3
"""A14 QUALITY agent E2E for acceptance. Reuses essay harness. proceed_once only."""

from pathlib import Path

import quality_essay_e2e as e2e

PROJECT = "/home/mike/Projects/Linux Lokales KI"
e2e.OUT = Path(PROJECT) / "benchmarks" / "acceptance-a01-a14-20260921"
e2e.PDF = f"{PROJECT}/.agent/tmp/a01-a14/a14-e2e.pdf"
e2e.PNG = f"{PROJECT}/.agent/tmp/a01-a14/a14-e2e.png"
e2e.PROMPT = f"""One session. Real MCP tools. Wait for permission. No YOLO. No /tmp.

Order:
1. mcp__local-tools__memory_load workspace="{PROJECT}"
2. mcp__local-tools__pdf_create output="{e2e.PDF}" title="A14 QUALITY acceptance" text="A01-A14 acceptance. Qwen3.8 27B QUALITY 16384. FAST stays local-fast."
3. mcp__local-tools__pdf_read path="{e2e.PDF}"
4. mcp__local-tools__pdf_render path="{e2e.PDF}" output="{e2e.PNG}" page=1
5. mcp__local-tools__pdf_vision_qa path="{e2e.PDF}"
6. mcp__local-tools__memory_update workspace="{PROJECT}" summary="A14 QUALITY E2E completed in one serve session." decisions="A01-A14 acceptance ran a full QUALITY agent chain after the MCP boot-cycle fix. No YOLO. FAST stays default." decision_title="A01-A14 QUALITY E2E 2026-09-21"

Do not replace unrelated STATE/TASKS. After each successful tool, call the next tool immediately. One short status sentence max between tools. Stop after memory_update.
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
