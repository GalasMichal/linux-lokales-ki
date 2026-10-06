#!/usr/bin/env python3
"""KWin and AT-SPI bridge for the desktop agent. Runs on system Python, not the MCP venv."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

from desktop_policy import (
    blocked_control_reason,
    check_type_text,
    classify_window,
    is_password_role,
    normalize_key,
    require_point_inside,
)
from errors import ToolError

BUS_NAME = "dev.localki.DesktopBridge"
OBJECT_PATH = "/Bridge"
INTERFACE = BUS_NAME
SCRIPT_PATH = Path("/srv/ai/cache/desktop-agent/bridge.js")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
INTERESTING_ROLES = {
    "push button",
    "button",
    "toggle button",
    "check box",
    "radio button",
    "entry",
    "text",
    "password text",
    "combo box",
    "page tab",
    "link",
    "spin button",
}
MENU_ROLES = {"menu item"}
KWIN_LIST_SCRIPT = r"""
function clean(value) {
    return String(value).split("|").join("/").split("\n").join(" ");
}
try {
    var parts = [];
    var windows = workspace.windowList();
    for (var n = 0; n < windows.length; n++) {
        var w = windows[n];
        var g = w.frameGeometry;
        var outName = "";
        try { outName = w.output ? String(w.output.name) : ""; } catch (e) { outName = ""; }
        parts.push([
            clean(w.internalId), clean(w.caption), clean(w.resourceClass), clean(w.resourceName),
            clean(w.pid), w.active ? "1" : "0", w.minimized ? "1" : "0",
            clean(g.x), clean(g.y), clean(g.width), clean(g.height), clean(outName)
        ].join("|"));
    }
    callDBus("dev.localki.DesktopBridge", "/Bridge", "dev.localki.DesktopBridge", "Push", parts.join("\n"));
} catch (err) {
    callDBus("dev.localki.DesktopBridge", "/Bridge", "dev.localki.DesktopBridge", "Push", "ERR\t" + err);
}
"""
KWIN_ID = re.compile(r"\{[0-9a-fA-F-]+\}")


class Bridge(dbus.service.Object):
    def __init__(self, bus: dbus.Bus) -> None:
        self.payload = ""
        self.ready = threading.Event()
        name = dbus.service.BusName(BUS_NAME, bus)
        super().__init__(name, OBJECT_PATH)

    @dbus.service.method(INTERFACE, in_signature="s", out_signature="")
    def Push(self, text: str) -> None:
        self.payload = str(text)
        self.ready.set()


def _as_int(value: str) -> int:
    return int(float(value))


def _run(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def _kwin_call(script_body: str) -> str:
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    loop = GLib.MainLoop()
    bridge = Bridge(bus)
    threading.Thread(target=loop.run, daemon=True).start()
    time.sleep(0.15)
    SCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCRIPT_PATH.write_text(script_body, encoding="utf-8")
    _run(["busctl", "--user", "call", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", "unloadScript", "s", str(SCRIPT_PATH)])
    loaded = _run(["busctl", "--user", "call", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", "loadScript", "s", str(SCRIPT_PATH)])
    if loaded.returncode != 0:
        loop.quit()
        raise ToolError(f"KWin-Skript konnte nicht geladen werden: {loaded.stderr.strip()}")
    token = loaded.stdout.strip().split()
    script_id = int(token[-1]) if token else 0
    object_path = f"/Scripting/Script{script_id}"
    ran = _run(["busctl", "--user", "call", "org.kde.KWin", object_path, "org.kde.kwin.Script", "run"])
    ready = bridge.ready.wait(5)
    loop.quit()
    _run(["busctl", "--user", "call", "org.kde.KWin", object_path, "org.kde.kwin.Script", "stop"])
    _run(["busctl", "--user", "call", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", "unloadScript", "s", str(SCRIPT_PATH)])
    if ran.returncode != 0 or not ready:
        raise ToolError("KWin hat keine Fensterdaten geliefert.")
    if bridge.payload.startswith("ERR\t"):
        raise ToolError(f"KWin-Skript: {bridge.payload[4:]}")
    return bridge.payload


def list_windows() -> list[dict[str, object]]:
    payload = _kwin_call(KWIN_LIST_SCRIPT)
    windows: list[dict[str, object]] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 12:
            continue
        flags = classify_window(parts[2], parts[3], parts[1])
        windows.append(
            {
                "kwin_id": parts[0],
                "title": parts[1],
                "resource_class": parts[2],
                "resource_name": parts[3],
                "pid": _as_int(parts[4] or "0"),
                "focused": parts[5] == "1",
                "minimized": parts[6] == "1",
                "x": _as_int(parts[7]),
                "y": _as_int(parts[8]),
                "width": _as_int(parts[9]),
                "height": _as_int(parts[10]),
                "monitor": parts[11],
                **flags,
            }
        )
    return windows


def focus_window(kwin_id: str) -> None:
    if not KWIN_ID.fullmatch(kwin_id):
        raise ToolError("Ungültige Fenster-ID.")
    script = f"""
try {{
    var wanted = "{kwin_id}";
    var found = false;
    var all = workspace.windowList();
    for (var i = 0; i < all.length; i++) {{
        if (String(all[i].internalId) === wanted) {{
            all[i].minimized = false;
            workspace.activeWindow = all[i];
            found = true;
        }}
    }}
    callDBus("dev.localki.DesktopBridge", "/Bridge", "dev.localki.DesktopBridge", "Push", found ? "focused" : "missing");
}} catch (err) {{
    callDBus("dev.localki.DesktopBridge", "/Bridge", "dev.localki.DesktopBridge", "Push", "ERR\\t" + err);
}}
"""
    result = _kwin_call(script)
    if result != "focused":
        raise ToolError("Fenster ist nicht mehr vorhanden. Neuer desktop_snapshot nötig.")


def list_monitors() -> list[dict[str, object]]:
    proc = _run(["kscreen-doctor", "-o"])
    if proc.returncode != 0:
        raise ToolError(f"Monitore konnten nicht gelesen werden: {proc.stderr.strip()}")
    text = ANSI.sub("", proc.stdout)
    monitors: list[dict[str, object]] = []
    for block in text.split("Output:"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        name_match = re.match(r"\d+\s+(\S+)\s+", lines[0])
        geometry = re.search(r"Geometry:\s*(-?\d+),(-?\d+)\s+(\d+)x(\d+)", block)
        scale = re.search(r"Scale:\s*([0-9.]+)", block)
        if name_match is None or geometry is None:
            continue
        enabled = any(line == "enabled" for line in lines[1:4])
        monitors.append(
            {
                "name": name_match.group(1),
                "x": int(geometry.group(1)),
                "y": int(geometry.group(2)),
                "width": int(geometry.group(3)),
                "height": int(geometry.group(4)),
                "scale": float(scale.group(1)) if scale else 1.0,
                "enabled": enabled,
            }
        )
    if not monitors:
        raise ToolError("Kein Monitor gefunden.")
    return monitors


def save_screenshot(path: str) -> None:
    target = Path(path)
    if not str(target).startswith("/srv/ai/workspaces/desktop-screenshots/"):
        raise ToolError("Screenshot-Pfad ist nicht erlaubt.")
    target.parent.mkdir(parents=True, exist_ok=True)
    home = Path("/srv/ai/cache/desktop-agent-home")
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "cache").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / "config")
    env["XDG_CACHE_HOME"] = str(home / "cache")
    proc = subprocess.run(
        ["spectacle", "-b", "-n", "-f", "-o", str(target)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
        env=env,
    )
    magic = target.read_bytes()[:8] if target.is_file() else b""
    if proc.returncode != 0 or magic != b"\x89PNG\r\n\x1a\n":
        raise ToolError(f"Screenshot fehlgeschlagen: {proc.stderr.strip() or proc.returncode}")


def _ensure_a11y() -> None:
    bus = dbus.SessionBus()
    proxy = bus.get_object("org.a11y.Bus", "/org/a11y/bus")
    props = dbus.Interface(proxy, "org.freedesktop.DBus.Properties")
    if not bool(props.Get("org.a11y.Status", "IsEnabled")):
        props.Set("org.a11y.Status", "IsEnabled", dbus.Boolean(True))
        time.sleep(0.3)


def _app_pid(app: object) -> int:
    for name in ("get_process_id", "getProcessId"):
        fn = getattr(app, name, None)
        if callable(fn):
            try:
                return int(fn())
            except (TypeError, ValueError):
                continue
    return -1


def _walk(node: object, depth: int, limit: list[int], found: list[object]) -> None:
    if depth > 12 or limit[0] <= 0:
        return
    limit[0] -= 1
    found.append(node)
    try:
        count = node.get_child_count()
    except Exception:
        return
    for index in range(count):
        try:
            _walk(node.get_child_at_index(index), depth + 1, limit, found)
        except Exception:
            continue


def _frame_for(window: dict[str, object]) -> object | None:
    import pyatspi

    desktop = pyatspi.Registry.getDesktop(0)
    title = str(window.get("title") or "")
    pid = int(window.get("pid") or -1)
    resource = str(window.get("resource_name") or "").lower()
    resource_class = str(window.get("resource_class") or "").lower()
    for index in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(index)
        app_pid = _app_pid(app)
        if pid > 0 and app_pid > 0 and app_pid != pid:
            continue
        try:
            app_name = (app.get_name() or "").lower()
        except Exception:
            app_name = ""
        pid_match = pid > 0 and app_pid == pid
        name_match = bool(resource) and bool(app_name) and resource in app_name
        class_match = bool(app_name) and app_name in resource_class
        if not pid_match and not name_match and not class_match:
            continue
        nodes: list[object] = []
        _walk(app, 0, [200], nodes)
        first_frame = None
        for node in nodes:
            try:
                if node.getRoleName() != "frame":
                    continue
            except Exception:
                continue
            first_frame = first_frame or node
            name = node.get_name() or ""
            if title and (title in name or name in title or title.split("—")[0].strip() in name):
                return node
        if pid_match or name_match or class_match:
            return first_frame or app
    return None


def _window_by_id(kwin_id: str) -> dict[str, object]:
    for window in list_windows():
        if window["kwin_id"] == kwin_id:
            return window
    raise ToolError("Fenster ist nicht mehr vorhanden. Neuer desktop_snapshot nötig.")


def _require_input_window(kwin_id: str) -> dict[str, object]:
    window = _window_by_id(kwin_id)
    if window.get("minimized"):
        raise ToolError("Das Fenster ist minimiert. Zuerst desktop_focus.")
    if window.get("input_blocked"):
        raise ToolError(str(window["input_block_reason"]))
    _ensure_a11y()
    if _frame_has_password(window):
        raise ToolError("Ein Passwortdialog darf beschrieben, aber nicht ausgefüllt werden.")
    return window


def _frame_has_password(window: dict[str, object]) -> bool:
    if window.get("auth"):
        return True
    frame = _frame_for(window)
    if frame is None:
        return False
    nodes: list[object] = []
    _walk(frame, 0, [200], nodes)
    for node in nodes:
        try:
            if is_password_role(node.getRoleName() or ""):
                return True
        except Exception:
            continue
    return False


def _interesting_nodes(root: object) -> list[object]:
    nodes: list[object] = []
    _walk(root, 0, [700], nodes)
    ranked: dict[str, list[object]] = {}
    for node in nodes:
        try:
            role = node.getRoleName() or ""
        except Exception:
            continue
        if role in INTERESTING_ROLES or role in MENU_ROLES:
            ranked.setdefault(role, []).append(node)
    ordered: list[object] = []
    for role in (
        "text",
        "entry",
        "password text",
        "button",
        "push button",
        "link",
        "page tab",
        "combo box",
        "toggle button",
        "radio button",
        "check box",
        "spin button",
        "menu item",
    ):
        ordered.extend(ranked.get(role, []))
    return ordered[:80]


def _elements(window: dict[str, object]) -> list[dict[str, object]]:
    frame = _frame_for(window)
    if frame is None:
        return []
    elements: list[dict[str, object]] = []
    for node in _interesting_nodes(frame):
        try:
            role = node.getRoleName() or ""
        except Exception:
            continue
        try:
            name = node.get_name() or ""
        except Exception:
            name = ""
        text = ""
        if not is_password_role(role):
            try:
                document = node.queryText()
                count = min(int(document.characterCount), 400)
                if count > 0:
                    text = document.getText(0, count)
            except Exception:
                text = ""
        bounds = _bounds(node)
        elements.append(
            {
                "index": len(elements),
                "role": role,
                "name": name,
                "text": text,
                "password": is_password_role(role),
                "x": bounds[0],
                "y": bounds[1],
                "width": bounds[2],
                "height": bounds[3],
            }
        )
    return elements


def _bounds(node: object) -> tuple[int, int, int, int]:
    try:
        import pyatspi

        component = node.queryComponent()
        x, y = component.getPosition(pyatspi.DESKTOP_COORDS)
        width, height = component.getSize()
        return int(x), int(y), int(width), int(height)
    except Exception:
        return -1, -1, 0, 0


def _node_at(window: dict[str, object], index: int) -> object:
    frame = _frame_for(window)
    if frame is None:
        raise ToolError("Zu diesem Fenster gibt es keine Bedienungshilfe-Daten.")
    nodes = _interesting_nodes(frame)
    if index < 0 or index >= len(nodes):
        raise ToolError("Element-ID gehört nicht mehr zu diesem Fenster. Neuer desktop_snapshot nötig.")
    return nodes[index]


def _editable(node: object) -> object:
    try:
        if is_password_role(node.getRoleName() or ""):
            raise ToolError("Ein Passwortfeld wird nicht ausgefüllt.")
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError("Das Feld kann nicht gelesen werden.") from exc
    try:
        return node.queryEditableText()
    except Exception as exc:
        raise ToolError("Das Ziel ist kein Textfeld.") from exc


def _text(node: object) -> object:
    try:
        return node.queryText()
    except Exception as exc:
        raise ToolError("Das Ziel hat keinen Text.") from exc


def _target_text(window: dict[str, object], element_index: int | None) -> object:
    if element_index is not None:
        return _node_at(window, element_index)
    frame = _frame_for(window)
    if frame is None:
        raise ToolError("Zu diesem Fenster gibt es keine Bedienungshilfe-Daten.")
    best = None
    best_area = -1
    for node in _interesting_nodes(frame):
        try:
            role = node.getRoleName() or ""
        except Exception:
            continue
        if is_password_role(role) or role not in {"text", "entry"}:
            continue
        try:
            node.queryEditableText()
        except Exception:
            continue
        _x, _y, width, height = _bounds(node)
        area = max(0, width) * max(0, height)
        if area >= best_area:
            best = node
            best_area = area
    if best is None:
        raise ToolError("Kein Textfeld in diesem Fenster.")
    return best


def _check_control(node: object, resource_class: str) -> None:
    try:
        name = node.get_name() or ""
    except Exception:
        name = ""
    reason = blocked_control_reason(name, resource_class)
    if reason:
        raise ToolError(reason)
    try:
        action = node.queryAction()
        count = int(action.nActions)
    except Exception:
        return
    for index in range(count):
        try:
            action_name = action.getName(index) or ""
        except Exception:
            continue
        reason = blocked_control_reason(action_name, resource_class)
        if reason:
            raise ToolError(reason)


def type_text(kwin_id: str, text: str, element_index: int | None) -> dict[str, object]:
    window = _require_input_window(kwin_id)
    node = _target_text(window, element_index)
    _check_control(node, str(window.get("resource_class") or ""))
    editor = _editable(node)
    document = _text(node)
    offset = max(0, int(document.caretOffset))
    if not editor.insertText(offset, text, len(text)):
        raise ToolError("Text konnte nicht eingefügt werden.")
    return {"inserted": len(text)}


def click(kwin_id: str, element_index: int | None, rel_x: int | None, rel_y: int | None) -> dict[str, object]:
    window = _require_input_window(kwin_id)
    if element_index is not None:
        node = _node_at(window, element_index)
    else:
        if rel_x is None or rel_y is None:
            raise ToolError("Klick braucht eine Element-ID oder eine Position im Fenster.")
        require_point_inside(rel_x, rel_y, int(window["width"]), int(window["height"]))
        node = _node_at_point(window, int(window["x"]) + rel_x, int(window["y"]) + rel_y)
    _check_control(node, str(window.get("resource_class") or ""))
    try:
        if is_password_role(node.getRoleName() or ""):
            raise ToolError("Ein Passwortfeld wird nicht bedient.")
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError("Element kann nicht gelesen werden.") from exc
    try:
        action = node.queryAction()
        if int(action.nActions) > 0:
            action.doAction(0)
            return {"clicked": True, "method": "action"}
    except ToolError:
        raise
    except Exception:
        pass
    try:
        if not node.queryComponent().grabFocus():
            raise ToolError("Element kann nicht fokussiert werden.")
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError("Element kann nicht bedient werden.") from exc
    return {"clicked": True, "method": "focus"}


def _node_at_point(window: dict[str, object], screen_x: int, screen_y: int) -> object:
    frame = _frame_for(window)
    if frame is None:
        raise ToolError("Zu diesem Fenster gibt es keine Bedienungshilfe-Daten.")
    nodes: list[object] = []
    _walk(frame, 0, [250], nodes)
    best = None
    best_area = None
    left = int(window["x"])
    top = int(window["y"])
    right = left + int(window["width"])
    bottom = top + int(window["height"])
    for node in nodes:
        x, y, width, height = _bounds(node)
        if width <= 0 or height <= 0:
            continue
        if x < left or y < top or x + width > right or y + height > bottom:
            continue
        if not (x <= screen_x < x + width and y <= screen_y < y + height):
            continue
        area = width * height
        if best_area is None or area < best_area:
            best = node
            best_area = area
    if best is None:
        raise ToolError("An dieser Stelle ist kein bedienbares Element. Kein globaler Klick.")
    return best


def press_key(kwin_id: str, key: str) -> dict[str, object]:
    window = _require_input_window(kwin_id)
    normalized = normalize_key(key)
    node = _target_text(window, None)
    editor = _editable(node)
    document = _text(node)
    if normalized == "ctrl+a":
        count = int(document.characterCount)
        if count <= 0:
            raise ToolError("Kein Text zum Markieren.")
        if not document.addSelection(0, count):
            document.setSelection(0, 0, count)
        return {"key": normalized, "selected_chars": count}
    if normalized == "ctrl+c":
        if int(document.getNSelections()) < 1:
            raise ToolError("Nichts markiert. Zuerst Ctrl+A.")
        start, end = document.getSelection(0)
        if int(end) <= int(start):
            raise ToolError("Nichts markiert. Zuerst Ctrl+A.")
        editor.copyText(int(start), int(end))
        return {"key": normalized, "copied_chars": int(end) - int(start)}
    if normalized == "ctrl+v":
        offset = max(0, int(document.caretOffset))
        if not editor.pasteText(offset):
            raise ToolError("Einfügen aus der Zwischenablage ist fehlgeschlagen.")
        return {"key": normalized}
    if normalized == "enter":
        offset = max(0, int(document.caretOffset))
        if not editor.insertText(offset, "\n", 1):
            raise ToolError("Enter konnte nicht in das Textfeld geschrieben werden.")
        return {"key": normalized}
    if normalized == "tab":
        return _move_focus(window, 1)
    if normalized == "shift+tab":
        return _move_focus(window, -1)
    frame = _frame_for(window)
    if frame is None or not frame.queryComponent().grabFocus():
        raise ToolError("Escape wird nicht global injiziert und konnte das Fenster nicht fokussieren.")
    return {"key": normalized, "method": "frame-focus"}


def _move_focus(window: dict[str, object], step: int) -> dict[str, object]:
    frame = _frame_for(window)
    if frame is None:
        raise ToolError("Zu diesem Fenster gibt es keine Bedienungshilfe-Daten.")
    nodes: list[object] = []
    _walk(frame, 0, [250], nodes)
    focusable = []
    for node in nodes:
        try:
            role = node.getRoleName() or ""
        except Exception:
            continue
        if role in INTERESTING_ROLES and not is_password_role(role):
            focusable.append(node)
    if not focusable:
        raise ToolError("Kein Feld für Tab gefunden.")
    current = 0
    try:
        import pyatspi

        for index, node in enumerate(focusable):
            if node.getState().contains(pyatspi.STATE_FOCUSED):
                current = index
                break
    except Exception:
        current = 0
    target = focusable[(current + step) % len(focusable)]
    _check_control(target, str(window.get("resource_class") or ""))
    if not target.queryComponent().grabFocus():
        raise ToolError("Tab konnte das nächste Feld nicht fokussieren.")
    return {"key": "tab" if step > 0 else "shift+tab", "method": "focus"}


def scroll(kwin_id: str, direction: str) -> dict[str, object]:
    if direction not in {"up", "down"}:
        raise ToolError("Scrollrichtung ist nur up oder down.")
    window = _require_input_window(kwin_id)
    node = _target_text(window, None)
    document = _text(node)
    count = int(document.characterCount)
    caret = max(0, int(document.caretOffset))
    step = 600
    target = min(max(0, count - 1), caret + step) if direction == "down" else max(0, caret - step)
    document.setCaretOffset(target)
    try:
        import pyatspi

        document.scrollSubstringTo(target, target, pyatspi.SCROLL_ANYWHERE)
    except Exception as exc:
        raise ToolError("Scrollen ist in diesem Fenster über die Bedienungshilfe nicht möglich.") from exc
    return {"scrolled": direction, "caret": target}


def dispatch(payload: dict[str, object]) -> dict[str, object]:
    command = str(payload.get("cmd") or "")
    if command == "snapshot":
        windows = list_windows()
        _ensure_a11y()
        for window in windows:
            if window.get("auth") or window.get("input_blocked"):
                continue
            if _frame_has_password(window):
                window["auth"] = True
                window["input_blocked"] = True
                window["input_block_reason"] = "Ein Passwortdialog darf beschrieben, aber nicht ausgefüllt werden."
        focused = next((window for window in windows if window.get("focused")), None)
        elements = _elements(focused) if focused is not None else []
        return {"monitors": list_monitors(), "windows": windows, "elements": elements}
    if command == "focus":
        focus_window(str(payload.get("kwin_id") or ""))
        return {"focused": True}
    if command == "screenshot":
        save_screenshot(str(payload.get("path") or ""))
        return {"path": payload.get("path")}
    if command == "type":
        index = payload.get("element_index")
        return type_text(
            str(payload.get("kwin_id") or ""),
            check_type_text(str(payload.get("text") or "")),
            None if index is None else int(index),
        )
    if command == "click":
        index = payload.get("element_index")
        rel_x = payload.get("rel_x")
        rel_y = payload.get("rel_y")
        return click(
            str(payload.get("kwin_id") or ""),
            None if index is None else int(index),
            None if rel_x is None else int(rel_x),
            None if rel_y is None else int(rel_y),
        )
    if command == "key":
        return press_key(str(payload.get("kwin_id") or ""), str(payload.get("key") or ""))
    if command == "scroll":
        return scroll(str(payload.get("kwin_id") or ""), str(payload.get("direction") or "down"))
    raise ToolError("Unbekannter Desktop-Befehl.")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = dispatch(payload)
        result["ok"] = True
    except ToolError as exc:
        result = {"ok": False, "error": str(exc)}
    except Exception as exc:
        result = {"ok": False, "error": f"Desktop-Helfer: {exc}"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
