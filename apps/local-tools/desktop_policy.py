"""Rules for the local desktop agent. No display or input imports."""

from __future__ import annotations

from errors import ToolError

MAX_TYPE_CHARS = 2000
ALLOWED_KEYS = {
    "escape": "escape",
    "esc": "escape",
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "shift+tab": "shift+tab",
    "ctrl+a": "ctrl+a",
    "ctrl+c": "ctrl+c",
    "ctrl+v": "ctrl+v",
}
TERMINAL_TOKENS = (
    "konsole",
    "kitty",
    "alacritty",
    "xterm",
    "gnome-terminal",
    "wezterm",
    "foot",
    "ghostty",
    "tilix",
    "yakuake",
    "ptyxis",
    "terminator",
    "kgx",
    "blackbox",
)
BROWSER_TOKENS = (
    "brave",
    "firefox",
    "chrome",
    "chromium",
    "librewolf",
    "vivaldi",
    "microsoft-edge",
)
MESSENGER_TOKENS = (
    "chatgpt",
    "signal",
    "telegram",
    "discord",
    "element",
    "neochat",
    "slack",
    "thunderbird",
    "kmail",
    "geary",
)
AUTH_TOKENS = (
    "polkit",
    "ksecretd",
    "kwallet",
    "kpasswd",
    "ssh-askpass",
    "gcr-prompter",
    "gnome-keyring",
    "policykit",
)
IDE_TOKENS = ("cursor", "code-oss", "codium", "devtools", "developer-tools")
BLOCK_PHRASES = (
    ("papierkorb leeren", "Papierkorb leeren ist gesperrt."),
    ("empty trash", "Papierkorb leeren ist gesperrt."),
    ("in papierkorb", "Löschen ist gesperrt."),
    ("konto löschen", "Kontolöschung ist gesperrt."),
    ("account löschen", "Kontolöschung ist gesperrt."),
    ("account delete", "Kontolöschung ist gesperrt."),
    ("delete account", "Kontolöschung ist gesperrt."),
    ("endgültig löschen", "Endgültiges Löschen ist gesperrt."),
    ("herunterfahren", "Herunterfahren ist gesperrt."),
    ("neu starten", "Neustart ist gesperrt."),
    ("neustart", "Neustart ist gesperrt."),
    ("shutdown", "Herunterfahren ist gesperrt."),
    ("reboot", "Neustart ist gesperrt."),
    ("passwort ändern", "Passwort ändern ist gesperrt."),
    ("kennwort ändern", "Passwort ändern ist gesperrt."),
    ("passwort anzeigen", "Passwort anzeigen ist gesperrt."),
    ("kennwort anzeigen", "Passwort anzeigen ist gesperrt."),
    ("show password", "Passwort anzeigen ist gesperrt."),
    ("firewall", "Firewall-Änderung ist gesperrt."),
    ("git push", "Git-Push ist gesperrt."),
    ("in den warenkorb", "Kauf ist gesperrt."),
    ("add to cart", "Kauf ist gesperrt."),
    ("kaufen", "Kauf ist gesperrt."),
    ("bestellen", "Bestellen ist gesperrt."),
    ("bezahlen", "Bezahlen ist gesperrt."),
    ("checkout", "Bezahlen ist gesperrt."),
    ("banking", "Banking ist gesperrt."),
    ("überweisen", "Banking ist gesperrt."),
    ("nachricht senden", "Senden ist gesperrt."),
    ("e-mail senden", "E-Mail senden ist gesperrt."),
    ("email senden", "E-Mail senden ist gesperrt."),
    ("senden", "Senden ist gesperrt."),
    ("posten", "Veröffentlichen ist gesperrt."),
    ("hochladen", "Hochladen ist gesperrt."),
    ("upload", "Hochladen ist gesperrt."),
    ("installieren", "Installieren ist gesperrt."),
    ("verschieben", "Verschieben ist gesperrt."),
    ("umbenennen", "Umbenennen ist gesperrt."),
    ("überschreiben", "Überschreiben ist gesperrt."),
    ("löschen", "Löschen ist gesperrt."),
    ("delete", "Löschen ist gesperrt."),
    ("rename", "Umbenennen ist gesperrt."),
)


def _blob(*parts: str) -> str:
    return " ".join(part.lower().replace("_", "-") for part in parts if part)


def _has_token(blob: str, tokens: tuple[str, ...]) -> bool:
    return any(token in blob for token in tokens)


def normalize_key(value: str) -> str:
    raw = value.strip().lower().replace(" ", "")
    raw = raw.replace("control+", "ctrl+").replace("strg+", "ctrl+")
    found = ALLOWED_KEYS.get(raw)
    if found is None:
        raise ToolError(
            "Diese Taste ist nicht erlaubt. Erlaubt sind nur Escape, Enter, Tab, "
            "Shift+Tab, Ctrl+A, Ctrl+C und Ctrl+V."
        )
    return found


def check_type_text(text: str) -> str:
    if not isinstance(text, str) or text == "":
        raise ToolError("Text ist leer.")
    if len(text) > MAX_TYPE_CHARS:
        raise ToolError("Text ist zu lang.")
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ToolError("Steuerzeichen im Text sind gesperrt.")
    return text


def require_point_inside(rel_x: int, rel_y: int, width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ToolError("Fenstergröße ist unbekannt. Neuer desktop_snapshot nötig.")
    if rel_x < 0 or rel_y < 0 or rel_x >= width or rel_y >= height:
        raise ToolError("Klick liegt außerhalb des Fensters.")


def blocked_control_reason(name: str, resource_class: str = "") -> str | None:
    lowered = name.strip().lower()
    if not lowered:
        return None
    for phrase, reason in BLOCK_PHRASES:
        if phrase in lowered:
            return reason
    if "systemsettings" in resource_class.lower() and lowered in {"anwenden", "apply", "ok"}:
        return "Systemeinstellungen dürfen nur angesehen werden."
    return None


def classify_window(resource_class: str, resource_name: str, title: str) -> dict[str, str | bool]:
    identity = _blob(resource_class, resource_name)
    title_blob = title.lower()
    terminal = _has_token(identity, TERMINAL_TOKENS) or title_blob.strip() in {
        "konsole",
        "terminal",
    }
    browser = _has_token(identity, BROWSER_TOKENS)
    messenger = _has_token(identity, MESSENGER_TOKENS)
    auth = _has_token(identity, AUTH_TOKENS) or any(
        phrase in title_blob
        for phrase in ("authentifizierung erforderlich", "authentication required", "policykit")
    )
    ide = _has_token(identity, IDE_TOKENS) or "developer tools" in title_blob or "devtools" in title_blob
    run_dialog = "krunner" in identity
    shell = "plasmashell" in identity or identity.strip() in {"kwin", "kwin-wayland"}
    crash_report = "drkonqi" in identity
    reason = ""
    if terminal:
        reason = "Eingabe in ein Terminal ist gesperrt."
    elif auth:
        reason = "Ein Passwortdialog darf beschrieben, aber nicht ausgefüllt werden."
    elif browser:
        reason = "Webseiten laufen über die browser_*-Werkzeuge, nicht über den Desktop."
    elif messenger:
        reason = "Mail und Messenger werden nicht bedient."
    elif ide:
        reason = "Eingabe in Cursor oder eine Entwicklerkonsole ist gesperrt."
    elif run_dialog:
        reason = "Der Ausführen-Dialog ist gesperrt."
    elif shell:
        reason = "Die Desktop-Oberfläche wird nicht bedient."
    elif crash_report:
        reason = "Der Absturzbericht wird nicht bedient."
    return {
        "terminal": terminal,
        "auth": auth,
        "browser": browser,
        "input_blocked": bool(reason),
        "input_block_reason": reason,
    }


def is_password_role(role: str) -> bool:
    lowered = role.replace("_", " ").strip().lower()
    return lowered in {"password text", "password"}
