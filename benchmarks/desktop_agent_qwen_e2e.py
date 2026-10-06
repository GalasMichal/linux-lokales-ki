#!/usr/bin/env python3
"""One Qwen serve turn for the local desktop agent. Votes proceed_once only."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))

from quality_cutover_e2e import EventCollector, http_json, sse_loop  # noqa: E402

OUT = BENCH / "desktop-agent-20260921"
PROMPT = (
    "Fokussiere den vorhandenen Kate-Texteditor mit der Datei desktop-agent-test.txt "
    'und schreibe "Hallo vom lokalen Desktop-Agenten". '
    "Lies danach den sichtbaren Text und stoppe. "
    "Nutze nur desktop_snapshot, desktop_focus, desktop_click und desktop_type. "
    "Keine Shell. Keine Browser-Werkzeuge. Kein Terminal. Kein Passwort."
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
        if "desktop_type" in short and "desktop_snapshot" in short and not last.get("hasActivePrompt"):
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
    short = [name.split("__")[-1] for name in names]

    def has(tool: str) -> bool:
        return any(tool in name for name in names)

    report = {
        "session": sid,
        "tools": names,
        "votes": votes,
        "texts": collector.texts[-3:],
        "ok": (
            has("desktop_snapshot")
            and has("desktop_type")
            and bool(votes)
            and all(vote == "proceed_once" for vote in votes)
            and not any("shell" in name.lower() or "browser_" in name for name in names)
        ),
    }
    (OUT / "qwen-e2e.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
