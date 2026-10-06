#!/usr/bin/env python3
"""Live browser-agent checks through the deployed local MCP server."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path

from mcp import Client

MCP_URL = "http://127.0.0.1:8765/mcp"
OUT = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/browser-agent-20260921")


def mem() -> float:
    vals = {}
    for line in open("/proc/meminfo"):
        key, raw = line.split(":", 1)
        vals[key] = int(raw.strip().split()[0])
    return round(vals["MemAvailable"] / 1024 / 1024, 2)


def payload(result) -> dict:
    if getattr(result, "is_error", False):
        raise RuntimeError(str(result))
    data = getattr(result, "structured_content", None) or getattr(result, "data", None)
    if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
        data = data["result"]
    if not isinstance(data, dict):
        text = ""
        for block in getattr(result, "content", []) or []:
            text += getattr(block, "text", "") or ""
        data = json.loads(text) if text else {}
    if data.get("ok") is False:
        raise RuntimeError(data.get("error") or "Browser-Tool fehlgeschlagen")
    return data


async def call(client: Client, name: str, arguments: dict | None = None) -> dict:
    result = await client.call_tool(name, arguments or {})
    return payload(result)


async def expect_block(client: Client, url: str) -> str:
    result = await client.call_tool("browser_open", {"url": url})
    data = getattr(result, "structured_content", None) or {}
    if isinstance(data, dict) and data.get("ok") is False:
        return str(data.get("error"))
    text = ""
    for block in getattr(result, "content", []) or []:
        text += getattr(block, "text", "") or ""
    if "gesperrt" in text or '"ok": false' in text or '"ok":false' in text:
        return text[:240]
    raise RuntimeError(f"Nicht blockiert: {url} -> {text[:240]}")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"ram_before": mem(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    async with Client(MCP_URL) as client:
        names = [tool.name for tool in (await client.list_tools()).tools]
        report["tools"] = names
        opened = await call(client, "browser_open", {"url": "https://example.com/"})
        report["ram_during"] = mem()
        report["open"] = {"url": opened.get("url"), "title": opened.get("title"), "snapshot": opened.get("snapshot")}
        if "example.com" not in str(opened.get("url")) or "Example Domain" not in str(opened.get("title")):
            raise RuntimeError(f"BROWSER-OPEN fehlgeschlagen: {opened.get('url')} {opened.get('title')}")
        if "Example Domain" not in str(opened.get("text")):
            raise RuntimeError("BROWSER-READ fehlgeschlagen")
        link = next(item for item in opened["elements"] if item["kind"] == "link")
        clicked = await call(client, "browser_click", {"ref": link["ref"]})
        after = await call(client, "browser_snapshot")
        report["click"] = {"ref": link["ref"], "url": after.get("url"), "title": after.get("title")}
        if "iana.org" not in str(after.get("url")):
            raise RuntimeError(f"BROWSER-CLICK landete auf {after.get('url')}")
        back = await call(client, "browser_back")
        report["back"] = back.get("url")
        if "example.com" not in str(back.get("url")):
            raise RuntimeError(f"BROWSER-BACK landete auf {back.get('url')}")
        shot = await call(client, "browser_screenshot")
        src = Path(shot["path"])
        dest = OUT / "example.png"
        shutil.copy2(src, dest)
        report["screenshot"] = {"path": str(dest), "bytes": dest.stat().st_size, "png": dest.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"}
        if not report["screenshot"]["png"]:
            raise RuntimeError("BROWSER-SCREENSHOT ist kein PNG")
        invalid = await client.call_tool("browser_click", {"ref": "l99"})
        invalid_text = json.dumps(getattr(invalid, "structured_content", None) or {}, ensure_ascii=False)
        for block in getattr(invalid, "content", []) or []:
            invalid_text += getattr(block, "text", "") or ""
        report["invalid"] = "Unbekannte" in invalid_text
        if not report["invalid"]:
            raise RuntimeError(f"BROWSER-INVALID-ID nicht sauber: {invalid_text[:300]}")
        blocked = {}
        for url in ("file:///etc/passwd", "javascript:alert(1)", "http://127.0.0.1:9/"):
            blocked[url] = await expect_block(client, url)
        report["blocked"] = blocked
        form = await call(client, "browser_open", {"url": "https://httpbin.org/forms/post"})
        field = next(
            item
            for item in form["elements"]
            if item["kind"] == "input" and item.get("type") not in {"submit", "password", "file", "hidden"}
        )
        typed = await call(client, "browser_type", {"ref": field["ref"], "text": "lokaler-browser-test"})
        report["type"] = {"ref": field["ref"], "chars": typed.get("chars")}
        if typed.get("chars") != 20:
            raise RuntimeError(f"BROWSER-TYPE fehlgeschlagen: {typed}")
        scrolled = await call(client, "browser_scroll", {"direction": "down", "amount": 400})
        report["scroll"] = {"scrolled": scrolled.get("scrolled"), "url": scrolled.get("url")}
        if scrolled.get("scrolled") != "down":
            raise RuntimeError("BROWSER-SCROLL fehlgeschlagen")
        closed = await call(client, "browser_close")
        report["close"] = closed
    time.sleep(1)
    report["ram_after"] = mem()
    report["agent_procs"] = subprocess.run(
        ["bash", "-lc", "ps -ef | awk '/user-data-dir=\\/srv\\/ai\\/cache\\/browser-agent/ && !/awk/'"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    report["ok"] = report["agent_procs"] == ""
    (OUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
