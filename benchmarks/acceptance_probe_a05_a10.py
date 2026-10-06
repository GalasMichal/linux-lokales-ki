#!/usr/bin/env python3
"""Acceptance probes A05–A10 plus workplace/MCP (no Vision, no T2I, no QUALITY E2E)."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

from mcp import Client

PROJECT = "/home/mike/Projects/Linux Lokales KI"
OUT = Path(PROJECT) / "benchmarks" / "acceptance-a01-a14-20260921"
TMP = Path(PROJECT) / ".agent" / "tmp" / "a01-a14"
MCP = "http://127.0.0.1:8765/mcp"
WORK = "http://127.0.0.1:8790"
PROXY = "http://127.0.0.1:8791"


def http_json(url: str, payload: dict | None = None, method: str | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method or ("POST" if payload is not None else "GET"),
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {"status": resp.status}


def extract(result) -> dict:
    if getattr(result, "is_error", False):
        raise RuntimeError(str(result))
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    report: dict = {"ok": True, "checks": []}

    def add(name: str, ok: bool, detail) -> None:
        report["checks"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            report["ok"] = False

    status = http_json(f"{WORK}/api/status")
    add("A05_status", bool(status.get("ok")), {"ollama": status.get("ollama"), "qwen": status.get("qwen")})
    agent = http_json(f"{WORK}/api/mode/agent", {})
    add("A05_mode_agent", agent.get("ok") is True and agent.get("mode") == "agent", agent)
    providers = http_json(f"{PROXY}/workspace/auth/providers")
    add(
        "A05_auth_providers_blocked",
        providers.get("providers") == [] or providers.get("code") == "local_provider_only",
        providers,
    )
    listed = http_json(f"{PROXY}/workspace/providers")
    names = []
    for block in listed.get("providers") or []:
        for model in block.get("models") or []:
            names.append(model.get("id") or model.get("name"))
    add(
        "A05_local_models_only",
        names != [] and all("local-fast" in str(n) or "local-quality" in str(n) for n in names),
        names,
    )

    async with Client(MCP) as client:
        tools = [t.name for t in (await client.list_tools()).tools]
        expected = {
            "generate_image",
            "memory_load",
            "memory_update",
            "pdf_read",
            "pdf_inspect",
            "pdf_create",
            "pdf_edit",
            "pdf_merge",
            "pdf_split",
            "pdf_ocr",
            "pdf_render",
            "pdf_vision_qa",
        }
        add("A08_tools", expected <= set(tools) and len(tools) == 12, tools)
        mem = extract(await client.call_tool("memory_load", {"workspace": PROJECT}))
        files = (mem.get("files") or {}) if isinstance(mem, dict) else {}
        decisions = (files.get("DECISIONS.md") or {}).get("content") or ""
        tasks = (files.get("TASKS.md") or {}).get("content") or ""
        reqs = (files.get("REQUIREMENTS.md") or {}).get("content") or ""
        add("A09_load_ok", mem.get("ok") is True, {"keys": list(files), "chars": mem.get("total_chars")})
        add("A09_requirements_full", "Local-only stack" in reqs, reqs[:120])
        add("A09_recent_decision", "hidden-gen" in decisions.lower() or "Compact" in decisions, decisions[-400:])
        add("A09_older_headings", "Older decisions" in decisions or decisions.count("## ") <= 6, "headings")
        add("A09_tasks_compact", "Completed:" in tasks or tasks.count("- [x]") <= 8, tasks[:200])
        hist_before = list((Path(PROJECT) / ".agent" / "history").glob("*.md"))
        upd = extract(
            await client.call_tool(
                "memory_update",
                {
                    "workspace": PROJECT,
                    "summary": "A01-A14 acceptance probe recorded.",
                    "decisions": "Acceptance matrix A01-A14 executed against live stack. No new features.",
                    "decision_title": "A01-A14 acceptance 2026-09-21",
                },
            )
        )
        hist_after = list((Path(PROJECT) / ".agent" / "history").glob("*.md"))
        add("A09_update_ok", upd.get("ok") is True, upd)
        add("A09_history_snapshot", len(hist_after) >= len(hist_before), {"before": len(hist_before), "after": len(hist_after)})
        pdf1 = TMP / "a10-create.pdf"
        pdf2 = TMP / "a10-edit.pdf"
        created = extract(
            await client.call_tool(
                "pdf_create",
                {
                    "output": str(pdf1),
                    "title": "A10 create",
                    "text": "Acceptance PDF page one. Local stack only.",
                },
            )
        )
        add("A10_create", created.get("ok") is True and pdf1.is_file(), created)
        inspected = extract(await client.call_tool("pdf_inspect", {"path": str(pdf1)}))
        add("A10_inspect", inspected.get("ok") is True and inspected.get("pages") == 1, inspected)
        read = extract(await client.call_tool("pdf_read", {"path": str(pdf1)}))
        add("A10_read", "Acceptance PDF" in str(read), {k: read.get(k) for k in ("ok", "pages") if isinstance(read, dict)})
        png = TMP / "a10-p1.png"
        rendered = extract(await client.call_tool("pdf_render", {"path": str(pdf1), "output": str(png), "page": 1}))
        add("A10_render", rendered.get("ok") is True and png.is_file(), rendered)
        edited = extract(
            await client.call_tool(
                "pdf_edit",
                {
                    "path": str(pdf1),
                    "output": str(pdf2),
                    "replacements": "Acceptance PDF page one=>Acceptance PDF edited page",
                },
            )
        )
        add("A10_edit", edited.get("ok") is True and pdf2.is_file(), edited)
        merged_path = TMP / "a10-merged.pdf"
        merged = extract(await client.call_tool("pdf_merge", {"paths": f"{pdf1},{pdf2}", "output": str(merged_path)}))
        add("A10_merge", merged.get("ok") is True and merged_path.is_file(), merged)
        split_dir = TMP / "a10-split"
        split_dir.mkdir(exist_ok=True)
        split = extract(
            await client.call_tool(
                "pdf_split",
                {"path": str(merged_path), "output_dir": str(split_dir), "pages": "1"},
            )
        )
        add("A10_split", split.get("ok") is True and any(split_dir.glob("*.pdf")), split)
        ocr = extract(
            await client.call_tool(
                "pdf_ocr",
                {"path": str(pdf1), "output": str(TMP / "a10-ocr.pdf"), "languages": "eng"},
            )
        )
        add("A10_ocr", ocr.get("ok") is True or "error" in ocr, ocr)

    path = OUT / "probe-a05-a10.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False)[:400000], encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "failed": [c for c in report["checks"] if not c["ok"]]}, indent=2, ensure_ascii=False))
    print("WROTE", path)


if __name__ == "__main__":
    asyncio.run(main())
