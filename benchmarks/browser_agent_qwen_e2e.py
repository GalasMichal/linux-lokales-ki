#!/usr/bin/env python3
"""One Qwen serve turn for the local browser agent. Votes proceed_once only."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))

from quality_cutover_e2e import BASE, EventCollector, http_json, sse_loop  # noqa: E402

OUT = BENCH / "browser-agent-20260921"
PROMPT = (
    "Öffne https://example.com, lies die Überschrift und sag mir, wohin der sichtbare Link führt. "
    "Öffne den Link danach. Nutze nur die lokalen Browser-Werkzeuge browser_open, browser_snapshot "
    "und browser_click. Keine Shell. Kein erfundenes Ergebnis."
)


def tool_names(collector: EventCollector) -> list[str]:
    names = []
    with collector.lock:
        items = list(collector.tools)
    for item in items:
        name = str(item.get("name") or item.get("title") or "")
        if name and (not names or names[-1] != name):
            names.append(name)
    return names


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    created = http_json("POST", "/session", {"cwd": "/srv/ai/workspaces"})
    sid = created["sessionId"]
    http_json("POST", f"/session/{sid}/model", {"modelId": "local-fast(openai)"})
    stop = threading.Event()
    collector = EventCollector(sid)
    threading.Thread(target=sse_loop, args=(sid, collector, stop), daemon=True).start()
    time.sleep(0.6)
    http_json("POST", f"/session/{sid}/prompt", {"prompt": [{"type": "text", "text": PROMPT}]})
    deadline = time.time() + 240
    last = {}
    while time.time() < deadline:
        last = http_json("GET", f"/session/{sid}/status")
        names = tool_names(collector)
        print(f"[wait] tools={names} votes={len(collector.votes)} active={last.get('hasActivePrompt')}", flush=True)
        short = [name.split("__")[-1] for name in names]
        if {"browser_open", "browser_click"}.issubset(set(short)) and not last.get("hasActivePrompt"):
            break
        if not last.get("hasActivePrompt") and names:
            time.sleep(2)
            if not http_json("GET", f"/session/{sid}/status").get("hasActivePrompt"):
                break
        time.sleep(2)
    stop.set()
    names = tool_names(collector)
    try:
        http_json("DELETE", f"/session/{sid}")
    except Exception:
        pass
    votes = [item.get("optionId") for item in collector.votes]
    report = {
        "session": sid,
        "tools": names,
        "votes": votes,
        "texts": collector.texts[-3:],
        "ok": (
            any(name.endswith("browser_open") or "browser_open" in name for name in names)
            and any("browser_click" in name for name in names)
            and votes
            and all(vote == "proceed_once" for vote in votes)
            and not any("shell" in name.lower() for name in names)
        ),
    }
    (OUT / "qwen-e2e.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
