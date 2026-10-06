"""Desktop-agent session. Window ids live only until the next snapshot."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

from desktop_policy import check_type_text, normalize_key, require_point_inside
from errors import ToolError

HELPER = Path(__file__).with_name("desktop_helper.py")
PYTHON = "/usr/bin/python3"
SCREENSHOT_DIR = Path("/srv/ai/workspaces/desktop-screenshots")
_LOCK = threading.Lock()
_STATE: dict[str, object] = {"windows": {}, "elements": {}, "controlled": ""}


def _call(payload: dict[str, object]) -> dict[str, object]:
    proc = subprocess.run(
        [PYTHON, str(HELPER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if not proc.stdout.strip():
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise ToolError(f"Desktop-Helfer ohne Ergebnis: {detail}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ToolError("Desktop-Helfer hat kein JSON geliefert.") from exc
    if not data.get("ok"):
        raise ToolError(str(data.get("error") or "Desktop-Aktion fehlgeschlagen."))
    return data


def _remember(raw: dict[str, object]) -> dict[str, object]:
    windows: dict[str, dict[str, object]] = {}
    listed = []
    focused_id = ""
    for index, window in enumerate(raw.get("windows") or [], start=1):
        if not isinstance(window, dict):
            continue
        public_id = f"w{index}"
        title = str(window.get("title") or window.get("resource_class") or "Fenster")
        record = dict(window)
        record["id"] = public_id
        record["label"] = f"[{public_id}] {title}"
        windows[public_id] = record
        listed.append({key: value for key, value in record.items() if key != "kwin_id"})
        if record.get("focused"):
            focused_id = public_id
    elements: dict[str, dict[str, object]] = {}
    listed_elements = []
    for index, element in enumerate(raw.get("elements") or [], start=1):
        if not isinstance(element, dict) or not focused_id:
            continue
        public_id = f"e{index}"
        elements[public_id] = {"window_id": focused_id, "index": int(element["index"])}
        listed_elements.append(
            {
                "id": public_id,
                "role": element.get("role"),
                "name": element.get("name"),
                "text": str(element.get("text") or "")[:120],
                "password": element.get("password"),
            }
        )
        if len(listed_elements) >= 20:
            break
    _STATE["windows"] = windows
    _STATE["elements"] = elements
    controlled = ""
    previous = str(_STATE.get("controlled_kwin") or "")
    for record in windows.values():
        if previous and record.get("kwin_id") == previous:
            controlled = str(record["id"])
    _STATE["controlled"] = controlled
    return {
        "ok": True,
        "monitors": raw.get("monitors") or [],
        "windows": listed,
        "focused_id": focused_id,
        "controlled_id": controlled,
        "elements": listed_elements,
    }


def _window(window_id: str) -> dict[str, object]:
    windows = _STATE.get("windows")
    if not isinstance(windows, dict) or window_id not in windows:
        raise ToolError("Unbekannte Fenster-ID. Neuer desktop_snapshot nötig. Es wird nichts anderes ausgeführt.")
    record = windows[window_id]
    if not isinstance(record, dict):
        raise ToolError("Unbekannte Fenster-ID. Neuer desktop_snapshot nötig. Es wird nichts anderes ausgeführt.")
    return record


def _resolve_window(window_id: str) -> dict[str, object]:
    chosen = window_id or str(_STATE.get("controlled") or "")
    if not chosen:
        raise ToolError("Zuerst desktop_snapshot und desktop_focus.")
    return _window(chosen)


def _screenshot_path() -> str:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return str(SCREENSHOT_DIR / f"desktop-{time.strftime('%Y%m%d-%H%M%S')}.png")


def _brief(snapshot: dict[str, object], extra: dict[str, object] | None = None) -> dict[str, object]:
    windows = []
    for window in snapshot.get("windows") or []:
        if not isinstance(window, dict):
            continue
        windows.append(
            {
                "id": window.get("id"),
                "label": window.get("label"),
                "focused": window.get("focused"),
                "input_block_reason": window.get("input_block_reason") or "",
            }
        )
    result = {
        "ok": True,
        "focused_id": snapshot.get("focused_id"),
        "controlled_id": snapshot.get("controlled_id"),
        "windows": windows,
    }
    if extra:
        result.update(extra)
    return result


def _visible_text(raw: dict[str, object]) -> str:
    best = ""
    for element in raw.get("elements") or []:
        if not isinstance(element, dict) or element.get("password"):
            continue
        text = str(element.get("text") or "")
        if len(text) > len(best):
            best = text
    return best[:300]


def desktop_snapshot() -> dict[str, object]:
    with _LOCK:
        raw = _call({"cmd": "snapshot"})
        path = _screenshot_path()
        shot = _call({"cmd": "screenshot", "path": path})
        result = _remember(raw)
        result["screenshot"] = shot.get("path")
        return result


def desktop_focus(window_id: str) -> dict[str, object]:
    with _LOCK:
        record = _window(window_id)
        _call({"cmd": "focus", "kwin_id": record["kwin_id"]})
        _STATE["controlled_kwin"] = record["kwin_id"]
        raw = _call({"cmd": "snapshot"})
        return _brief(_remember(raw))


def desktop_click(window_id: str = "", element_id: str = "", x: int = -1, y: int = -1) -> dict[str, object]:
    with _LOCK:
        record = _resolve_window(window_id)
        if record.get("input_blocked"):
            raise ToolError(str(record.get("input_block_reason") or "Eingabe in dieses Fenster ist gesperrt."))
        payload: dict[str, object] = {"cmd": "click", "kwin_id": record["kwin_id"]}
        if element_id:
            elements = _STATE.get("elements")
            if not isinstance(elements, dict) or element_id not in elements:
                raise ToolError("Unbekannte Element-ID. Neuer desktop_snapshot nötig. Es wird nichts anderes ausgeführt.")
            element = elements[element_id]
            if element.get("window_id") != record["id"]:
                raise ToolError("Element-ID gehört nicht zu diesem Fenster.")
            payload["element_index"] = element["index"]
        else:
            require_point_inside(x, y, int(record["width"]), int(record["height"]))
            payload["rel_x"] = x
            payload["rel_y"] = y
        _call(payload)
        _STATE["controlled_kwin"] = record["kwin_id"]
        raw = _call({"cmd": "snapshot"})
        return _brief(_remember(raw))


def desktop_type(window_id: str = "", text: str = "", element_id: str = "") -> dict[str, object]:
    with _LOCK:
        record = _resolve_window(window_id)
        if record.get("input_blocked"):
            raise ToolError(str(record.get("input_block_reason") or "Eingabe in dieses Fenster ist gesperrt."))
        payload: dict[str, object] = {
            "cmd": "type",
            "kwin_id": record["kwin_id"],
            "text": check_type_text(text),
        }
        if element_id:
            elements = _STATE.get("elements")
            if not isinstance(elements, dict) or element_id not in elements:
                raise ToolError("Unbekannte Element-ID. Neuer desktop_snapshot nötig. Es wird nichts anderes ausgeführt.")
            element = elements[element_id]
            if element.get("window_id") != record["id"]:
                raise ToolError("Element-ID gehört nicht zu diesem Fenster.")
            payload["element_index"] = element["index"]
        _call(payload)
        _STATE["controlled_kwin"] = record["kwin_id"]
        raw = _call({"cmd": "snapshot"})
        return _brief(_remember(raw), {"visible_text": _visible_text(raw)})


def desktop_scroll(window_id: str = "", direction: str = "down") -> dict[str, object]:
    with _LOCK:
        record = _resolve_window(window_id)
        if record.get("input_blocked"):
            raise ToolError(str(record.get("input_block_reason") or "Eingabe in dieses Fenster ist gesperrt."))
        _call({"cmd": "scroll", "kwin_id": record["kwin_id"], "direction": direction})
        _STATE["controlled_kwin"] = record["kwin_id"]
        raw = _call({"cmd": "snapshot"})
        return _brief(_remember(raw))


def desktop_key(window_id: str = "", key: str = "") -> dict[str, object]:
    with _LOCK:
        record = _resolve_window(window_id)
        if record.get("input_blocked"):
            raise ToolError(str(record.get("input_block_reason") or "Eingabe in dieses Fenster ist gesperrt."))
        result = _call({"cmd": "key", "kwin_id": record["kwin_id"], "key": normalize_key(key)})
        _STATE["controlled_kwin"] = record["kwin_id"]
        raw = _call({"cmd": "snapshot"})
        brief = _brief(_remember(raw), {"visible_text": _visible_text(raw)})
        brief["key_result"] = {key_name: value for key_name, value in result.items() if key_name != "ok"}
        return brief


def desktop_screenshot() -> dict[str, object]:
    with _LOCK:
        path = _screenshot_path()
        shot = _call({"cmd": "screenshot", "path": path})
        return {"ok": True, "screenshot": shot.get("path")}


def desktop_close() -> dict[str, object]:
    with _LOCK:
        _STATE["windows"] = {}
        _STATE["elements"] = {}
        _STATE["controlled"] = ""
        _STATE["controlled_kwin"] = ""
        cutoff = time.time() - 3600
        if SCREENSHOT_DIR.is_dir():
            for path in SCREENSHOT_DIR.glob("desktop-*.png"):
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
        return {"ok": True, "closed": True}
