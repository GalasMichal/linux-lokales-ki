"""One local Brave window for the browser agent. No shell, no model JavaScript."""

from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

from browser_policy import (
    REF_PREFIX,
    check_navigation_url,
    check_request_url,
    classify_control,
    is_dangerous_action,
    is_executable_download,
)
from errors import ToolError

PROFILE_DIR = Path(os.environ.get("BROWSER_AGENT_PROFILE", "/srv/ai/cache/browser-agent"))
HOME_DIR = Path(os.environ.get("BROWSER_AGENT_HOME", "/srv/ai/cache/browser-agent-home"))
DOWNLOAD_DIR = Path(os.environ.get("BROWSER_AGENT_DOWNLOADS", "/srv/ai/workspaces/browser-downloads"))
SCREENSHOT_DIR = Path(os.environ.get("BROWSER_AGENT_SCREENSHOTS", "/srv/ai/workspaces/browser-screenshots"))
BRAVE = os.environ.get("BROWSER_EXECUTABLE", "/usr/bin/brave-browser")
TEXT_LIMIT = 6000
ELEMENT_LIMIT = 80
LAUNCH_ARGS = [
    "--ozone-platform=wayland",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-component-update",
    "--disable-sync",
    "--disable-translate",
    "--password-store=basic",
    "--disable-features=Translate,OptimizationHints,MediaRouter",
]


def _safe_name(name: str) -> str:
    base = Path(name or "download.bin").name
    cleaned = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in base)[:120]
    return cleaned or "download.bin"


class BrowserSession:
    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[Callable[[BrowserSession], Any], queue.Queue]] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="browser-agent", daemon=True)
        self._thread.start()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._refs: dict[str, dict[str, str]] = {}

    def call(self, fn: Callable[["BrowserSession"], Any], timeout: int = 90) -> Any:
        box: queue.Queue = queue.Queue(1)
        self._queue.put((fn, box))
        try:
            status, payload = box.get(timeout=timeout)
        except queue.Empty as exc:
            raise ToolError("Browser-Aktion hat das Zeitlimit überschritten.") from exc
        if status == "err":
            if isinstance(payload, ToolError):
                raise payload
            raise ToolError(str(payload))
        return payload

    def _loop(self) -> None:
        while True:
            fn, box = self._queue.get()
            try:
                box.put(("ok", fn(self)))
            except Exception as exc:  # noqa: BLE001 — returned to the MCP client as ToolError
                box.put(("err", exc if isinstance(exc, ToolError) else ToolError(str(exc))))

    def _ensure(self) -> None:
        if self._page is not None:
            return
        if not Path(BRAVE).is_file():
            raise ToolError(f"Brave wurde nicht gefunden: {BRAVE}")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ToolError("Playwright ist im lokalen Werkzeugdienst nicht installiert.") from exc
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        (HOME_DIR / "config").mkdir(parents=True, exist_ok=True)
        (HOME_DIR / "cache").mkdir(parents=True, exist_ok=True)
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        browser_env = os.environ.copy()
        browser_env["HOME"] = str(HOME_DIR)
        browser_env["XDG_CONFIG_HOME"] = str(HOME_DIR / "config")
        browser_env["XDG_CACHE_HOME"] = str(HOME_DIR / "cache")
        browser_env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        browser_env.setdefault("WAYLAND_DISPLAY", "wayland-0")
        browser_env.setdefault("DISPLAY", ":0")
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=BRAVE,
            headless=False,
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
            locale="de-DE",
            args=LAUNCH_ARGS,
            env=browser_env,
        )
        self._browser = self._context.browser
        self._context.route("**/*", self._route)
        self._context.on("download", self._on_download)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

    def _route(self, route) -> None:
        if check_request_url(route.request.url):
            route.continue_()
            return
        route.abort()

    def _on_download(self, download) -> None:
        name = _safe_name(download.suggested_filename)
        if is_executable_download(name):
            download.cancel()
            return
        target = DOWNLOAD_DIR / f"{int(time.time())}-{name}"
        download.save_as(str(target))

    def _clear_refs(self) -> None:
        self._refs = {}

    def open(self, url: str) -> dict[str, Any]:
        target = check_navigation_url(url)
        self._ensure()
        assert self._page is not None
        self._clear_refs()
        try:
            self._page.goto(target, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            raise ToolError(f"Seite konnte nicht geöffnet werden: {exc}") from exc
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        self._ensure()
        assert self._page is not None
        current = self._page.url
        if current and current != "about:blank":
            check_navigation_url(current)
        raw = self._page.evaluate(_SNAPSHOT_JS, ELEMENT_LIMIT)
        text = str(raw.get("text") or "")[:TEXT_LIMIT]
        refs: dict[str, dict[str, str]] = {}
        counts = {prefix: 0 for prefix in set(REF_PREFIX.values())}
        elements = []
        for item in raw.get("elements") or []:
            kind = classify_control(str(item.get("tag") or ""), str(item.get("role") or ""), str(item.get("type") or ""))
            if not kind:
                continue
            href = str(item.get("href") or "")
            if href and not check_request_url(href):
                continue
            name = " ".join(str(item.get("name") or "").split())[:160]
            if is_dangerous_action(name):
                continue
            prefix = REF_PREFIX[kind]
            counts[prefix] += 1
            ref = f"{prefix}{counts[prefix]}"
            refs[ref] = {"kind": kind, "name": name, "href": href, "type": str(item.get("type") or "")}
            elements.append({"ref": ref, "kind": kind, "name": name, "href": href, "type": str(item.get("type") or "")})
            self._page.evaluate(
                "(pair) => { const node = document.querySelector(pair.selector); if (node) node.setAttribute('data-agent-ref', pair.ref); }",
                {"selector": item.get("selector"), "ref": ref},
            )
        self._refs = refs
        lines = [f"[{item['ref']}] {item['kind']} \"{item['name']}\"" for item in elements]
        return {
            "ok": True,
            "url": current,
            "title": self._page.title(),
            "text": text,
            "elements": elements,
            "snapshot": "\n".join(lines),
        }

    def click(self, ref: str) -> dict[str, Any]:
        item = self._require_ref(ref)
        if is_dangerous_action(item["name"]):
            raise ToolError("Diese Aktion kann nach außen wirken und ist in Phase 1 gesperrt.")
        if item["href"] and not check_request_url(item["href"]):
            raise ToolError("Dieses Ziel ist gesperrt.")
        assert self._page is not None
        try:
            self._page.locator(f'[data-agent-ref="{ref}"]').click(timeout=10000)
            self._page.wait_for_load_state("domcontentloaded", timeout=15000)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"Klick fehlgeschlagen: {exc}") from exc
        self._clear_refs()
        return {"ok": True, "clicked": ref, "url": self._page.url, "title": self._page.title()}

    def type_text(self, ref: str, text: str) -> dict[str, Any]:
        item = self._require_ref(ref)
        if item["kind"] not in {"input", "textarea"}:
            raise ToolError("In dieses Element kann kein Text geschrieben werden.")
        if item["type"].lower() in {"password", "file", "hidden"}:
            raise ToolError("Passwort-, Datei- und versteckte Felder sind gesperrt.")
        value = text or ""
        if len(value) > 2000:
            raise ToolError("Text ist zu lang.")
        assert self._page is not None
        try:
            self._page.locator(f'[data-agent-ref="{ref}"]').fill(value, timeout=10000)
        except Exception as exc:
            raise ToolError(f"Eingabe fehlgeschlagen: {exc}") from exc
        self._clear_refs()
        return {"ok": True, "typed": ref, "chars": len(value)}

    def scroll(self, direction: str = "down", amount: int = 600) -> dict[str, Any]:
        self._ensure()
        assert self._page is not None
        way = (direction or "down").lower()
        if way not in {"down", "up"}:
            raise ToolError("Richtung muss down oder up sein.")
        try:
            pixels = int(amount)
        except (TypeError, ValueError) as exc:
            raise ToolError("Scroll-Menge ist ungültig.") from exc
        pixels = max(100, min(pixels, 1600))
        delta = pixels if way == "down" else -pixels
        self._page.mouse.wheel(0, delta)
        self._page.wait_for_timeout(300)
        self._clear_refs()
        shot = self.snapshot()
        shot["scrolled"] = way
        shot["amount"] = pixels
        return shot

    def back(self) -> dict[str, Any]:
        self._ensure()
        assert self._page is not None
        self._clear_refs()
        try:
            response = self._page.go_back(wait_until="domcontentloaded", timeout=15000)
        except Exception as exc:
            raise ToolError(f"Zurück fehlgeschlagen: {exc}") from exc
        if response is None and self._page.url in {"", "about:blank"}:
            raise ToolError("Es gibt keine vorherige Seite.")
        return self.snapshot()

    def screenshot(self) -> dict[str, Any]:
        self._ensure()
        assert self._page is not None
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        self._sweep(SCREENSHOT_DIR, "browser-", 3600)
        path = SCREENSHOT_DIR / f"browser-{time.strftime('%Y%m%d-%H%M%S')}.png"
        self._page.screenshot(path=str(path), full_page=False)
        if not path.is_file() or path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise ToolError("Screenshot ist kein gültiges PNG.")
        return {"ok": True, "path": str(path), "bytes": path.stat().st_size, "url": self._page.url}

    def close(self) -> dict[str, Any]:
        self._clear_refs()
        self._sweep(SCREENSHOT_DIR, "browser-", 3600)
        browser = self._browser
        playwright = self._playwright
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        return {"ok": True, "closed": True}

    def _require_ref(self, ref: str) -> dict[str, str]:
        key = (ref or "").strip()
        if not key or len(key) > 6 or key[0] not in "lbistc" or not key[1:].isdigit():
            raise ToolError("Unbekannte Element-ID. Zuerst browser_snapshot ausführen. Keine eigene ID erfinden.")
        item = self._refs.get(key)
        if not item:
            raise ToolError("Unbekannte Element-ID. Zuerst browser_snapshot ausführen. Keine eigene ID erfinden.")
        return item

    @staticmethod
    def _sweep(directory: Path, prefix: str, max_age: int) -> None:
        if not directory.is_dir():
            return
        now = time.time()
        for path in directory.glob(f"{prefix}*"):
            if not path.is_file():
                continue
            if max_age == 0 or now - path.stat().st_mtime > max_age:
                path.unlink(missing_ok=True)


_SNAPSHOT_JS = """(limit) => {
  const nodes = Array.from(document.querySelectorAll('a,button,input,textarea,select,[role="button"],[role="link"],[role="checkbox"],[role="radio"]'));
  document.querySelectorAll('[data-agent-ref]').forEach((node) => node.removeAttribute('data-agent-ref'));
  const visible = nodes.filter((node) => {
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  }).slice(0, limit);
  visible.forEach((node, index) => node.setAttribute('data-agent-pick', String(index)));
  const elements = visible.map((node) => {
    const label = node.getAttribute('aria-label') || node.innerText || node.getAttribute('placeholder') || node.getAttribute('name') || node.getAttribute('value') || '';
    return {
      selector: '[data-agent-pick="' + node.getAttribute('data-agent-pick') + '"]',
      tag: node.tagName.toLowerCase(),
      role: node.getAttribute('role') || '',
      type: node.getAttribute('type') || '',
      name: label.replace(/\\s+/g, ' ').trim(),
      href: node.href || '',
    };
  });
  return { text: (document.body && document.body.innerText) || '', elements };
}"""


SESSION = BrowserSession()


def browser_open(url: str) -> dict[str, Any]:
    return SESSION.call(lambda s: s.open(url))


def browser_snapshot() -> dict[str, Any]:
    return SESSION.call(lambda s: s.snapshot())


def browser_click(ref: str) -> dict[str, Any]:
    return SESSION.call(lambda s: s.click(ref))


def browser_type(ref: str, text: str) -> dict[str, Any]:
    return SESSION.call(lambda s: s.type_text(ref, text))


def browser_scroll(direction: str = "down", amount: int = 600) -> dict[str, Any]:
    return SESSION.call(lambda s: s.scroll(direction, amount))


def browser_back() -> dict[str, Any]:
    return SESSION.call(lambda s: s.back())


def browser_screenshot() -> dict[str, Any]:
    return SESSION.call(lambda s: s.screenshot())


def browser_close() -> dict[str, Any]:
    return SESSION.call(lambda s: s.close())
