#!/usr/bin/env python3
"""Interactive QUALITY Vision-QA E2E via qwen serve. Votes proceed_once. No YOLO."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "apps" / "local-tools"
sys.path.insert(0, str(TOOLS))

from pdf_tools import ensure_pdf_imports  # noqa: E402
from quality_cutover_e2e import MODEL_ID, PROJECT, nvidia, ollama_ps  # noqa: E402
from quality_cutover_e2e_multiturn import run_turn  # noqa: E402

OUT = Path(PROJECT) / "benchmarks" / "vision-qa-20260915"
BAD_PDF = Path(PROJECT) / ".agent" / "tmp" / "vision-qa-bad.pdf"
CLEAN_PDF = Path(PROJECT) / ".agent" / "tmp" / "vision-qa-clean.pdf"
BAD_PNG = Path(PROJECT) / ".agent" / "tmp" / "vision-qa-bad.png"
CLEAN_PNG = Path(PROJECT) / ".agent" / "tmp" / "vision-qa-clean.png"


def make_bad_pdf(path: Path) -> None:
    ensure_pdf_imports()
    import pymupdf

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((-70, 180), "CLIPPED_LEFT heading hangs off the page", fontsize=18)
    page.insert_text((80, 300), "OVERLAP_A colliding title block", fontsize=22)
    page.insert_text((95, 306), "OVERLAP_B second title covering the first", fontsize=22)
    doc.save(path)
    doc.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_bad_pdf(BAD_PDF)
    if CLEAN_PDF.exists():
        CLEAN_PDF.unlink()
    t0 = time.perf_counter()
    before = {"nvidia": nvidia(), "ollama_ps": ollama_ps()}
    turns_spec = [
        {
            "expect": "memory_load",
            "path": None,
            "text": (
                f'Call ONLY mcp__local-tools__memory_load with workspace="{PROJECT}". '
                "Stop immediately after the tool returns."
            ),
        },
        {
            "expect": "pdf_render",
            "path": str(BAD_PNG),
            "text": (
                f'Call ONLY mcp__local-tools__pdf_render with path="{BAD_PDF}", '
                f'output="{BAD_PNG}", page=1. Stop immediately after the tool returns.'
            ),
        },
        {
            "expect": "pdf_vision_qa",
            "path": None,
            "text": (
                f'Call ONLY mcp__local-tools__pdf_vision_qa with path="{BAD_PDF}", pages="1". '
                "Stop immediately after the tool returns."
            ),
        },
        {
            "expect": "pdf_create",
            "path": str(CLEAN_PDF),
            "text": (
                f'Call ONLY mcp__local-tools__pdf_create with output="{CLEAN_PDF}", '
                'title="Vision QA Clean", '
                'text="Invoice 2026-09-15. This replacement page has normal margins, readable body text, '
                'and no overlapping headings. Layout is clean for visual QA." '
                "Stop immediately after the tool returns."
            ),
        },
        {
            "expect": "pdf_render",
            "path": str(CLEAN_PNG),
            "text": (
                f'Call ONLY mcp__local-tools__pdf_render with path="{CLEAN_PDF}", '
                f'output="{CLEAN_PNG}", page=1. Stop immediately after the tool returns.'
            ),
        },
        {
            "expect": "pdf_vision_qa",
            "path": None,
            "text": (
                f'Call ONLY mcp__local-tools__pdf_vision_qa with path="{CLEAN_PDF}", pages="1". '
                "Stop immediately after the tool returns."
            ),
        },
        {
            "expect": "memory_update",
            "path": None,
            "text": (
                f'Call ONLY mcp__local-tools__memory_update with workspace="{PROJECT}", '
                'summary="PDF Vision-QA E2E ran via qwen serve.", '
                'decisions="2026-09-15 — pdf_vision_qa uses Ollama /api/chat local-quality, optional after technical QA.", '
                'decision_title="PDF Vision-QA E2E". Do not replace STATE.md or TASKS.md. '
                "Stop immediately after the tool returns."
            ),
        },
    ]
    turns = []
    for spec in turns_spec:
        turns.append(run_turn(spec, t0, model_id="local-quality(openai)"))
        time.sleep(1)
    report = {
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "before": before,
        "after": {"nvidia": nvidia(), "ollama_ps": ollama_ps()},
        "model": MODEL_ID,
        "bad_pdf": str(BAD_PDF),
        "clean_pdf": str(CLEAN_PDF),
        "bad_pdf_exists": BAD_PDF.is_file(),
        "clean_pdf_exists": CLEAN_PDF.is_file(),
        "turns": [
            {
                "expect": item["expect"],
                "sessionId": item["sessionId"],
                "votes": len(item["votes"]),
                "completed": item["completed"],
                "thoughts": item["thoughts"],
                "tools": [
                    {"name": x.get("name") or x.get("title"), "status": x.get("status")}
                    for x in item["tools"]
                ],
            }
            for item in turns
        ],
    }
    path = OUT / "e2e.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    print("WROTE", path, flush=True)
    vision_turns = [item for item in turns if item["expect"] == "pdf_vision_qa"]
    ok = (
        all(item["completed"] and item["votes"] for item in turns)
        and CLEAN_PDF.is_file()
        and BAD_PNG.is_file()
        and len(vision_turns) >= 2
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
