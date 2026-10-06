#!/usr/bin/env python3
"""One local-fast turn that must discover a deferred MCP tool. proceed_once only."""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from quality_cutover_e2e import EventCollector, http_json, sse_loop, wait_for_turn
from quality_16k_cutover_e2e import compact_tools

WORKSPACE = "/srv/ai/workspaces"
MODEL_ID = "local-fast(openai)"
OUT = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/lazy-tool-budget-20260922")

PROMPTS = {
    "memory": 'Finde memory_load per tool_search und lade das Projekt-Memory. workspace ist "/home/mike/Projects/Linux Lokales KI". Danach stopp. Keine Shell. Kein YOLO.',
    "pdf": 'Erstelle ein kleines PDF und rendere Seite 1. Nutze tool_search, dann pdf_create und pdf_render. Ausgabe "/home/mike/Projects/Linux Lokales KI/.agent/tmp/lazy-pdf/page.pdf" und PNG daneben. Titel "Lazy". Text "Lazy tool loading." Danach stopp. Keine Shell.',
    "browser": "Öffne https://example.com mit dem Browser-Werkzeug. Nutze tool_search, dann browser_open. Danach stopp. Kein file, kein javascript, kein localhost, keine Shell.",
    "desktop": "Erfasse die vorhandenen Fenster. Nutze tool_search, dann desktop_snapshot. Tippe nichts. Danach stopp. Keine Shell.",
}


def run(label: str) -> dict:
    prompt = PROMPTS[label]
    t0 = time.perf_counter()
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    if created.get("attached"):
        http_json("DELETE", f"/session/{sid}")
        created = http_json("POST", "/session", {"cwd": WORKSPACE})
        sid = created["sessionId"]
    http_json("POST", f"/session/{sid}/model", {"modelId": MODEL_ID})
    stop = threading.Event()
    collector = EventCollector(sid)
    threading.Thread(target=sse_loop, args=(sid, collector, stop), daemon=True).start()
    time.sleep(0.5)
    http_json("POST", f"/session/{sid}/prompt", {"prompt": [{"type": "text", "text": prompt}]}, timeout=30)
    wait_for_turn(sid, collector, t0, time.strftime("%Y-%m-%d %H:%M:%S"))
    stop.set()
    tools = compact_tools(collector)
    names = [str(item.get("name") or "") for item in tools if item.get("status") == "completed"]
    report = {
        "label": label,
        "sessionId": sid,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "tools": tools,
        "completed_names": names,
        "votes": collector.votes,
        "proceed_once": all(v.get("optionId") == "proceed_once" for v in collector.votes if v.get("ok")),
        "yolo": any("yolo" in str(v.get("optionId") or "") for v in collector.votes),
    }
    dest = OUT / f"discover-{label}.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False)[:1_500_000], encoding="utf-8")
    print(json.dumps({"label": label, "session": sid, "names": names, "votes": len(collector.votes)}, indent=2), flush=True)
    return report


if __name__ == "__main__":
    run(sys.argv[1])
