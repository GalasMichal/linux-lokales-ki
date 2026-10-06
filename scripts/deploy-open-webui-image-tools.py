#!/usr/bin/env python3
"""Install or update the Open WebUI local image Tools adapter. Localhost only."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "apps" / "open-webui-tools" / "local_image_policy.py"
TOOLS = ROOT / "apps" / "open-webui-tools" / "local_images.py"
BACKUP_ROOT = Path("/mnt/ai-archive/backups")
WEBUI_DATA = Path("/srv/ai/apps/open-webui/data")
TOOL_ID = "local_images"
BASE = "http://127.0.0.1:3000"
ATTACH_MODELS = ("local-fast:latest", "local-quality:latest")


def tool_content() -> str:
    policy = POLICY.read_text()
    body_lines = []
    skipped_future = False
    for line in TOOLS.read_text().splitlines(True):
        if not skipped_future and line.startswith("from __future__ import"):
            skipped_future = True
            continue
        body_lines.append(line)
    return policy + "\n\n" + "".join(body_lines)


def request(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} HTTP {exc.code}: {exc.read()[:1200]!r}") from exc
    return json.loads(raw) if raw else {}


def request_allow_404(method: str, path: str, token: str, payload: dict | None = None) -> dict | None:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise SystemExit(f"{method} {path} HTTP {exc.code}: {exc.read()[:1200]!r}") from exc
    return json.loads(raw) if raw else {}


def signin(email: str, password: str) -> str:
    payload = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/auths/signin",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read())
    token = data.get("token")
    if not token:
        raise SystemExit("Open WebUI-Anmeldung lieferte kein Token.")
    return token


def backup() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / f"open-webui-image-tools-{stamp}"
    dest.mkdir(parents=True, exist_ok=False)
    shutil.copy2(WEBUI_DATA / "webui.db", dest / "webui.db")
    quadlet = Path.home() / ".config/containers/systemd/open-webui.container"
    if quadlet.is_file():
        shutil.copy2(quadlet, dest / "open-webui.container")
    (dest / "RESTORE.txt").write_text(
        "cp webui.db /srv/ai/apps/open-webui/data/webui.db && systemctl --user restart open-webui.service\n"
        "Ollama-Aliase nicht anfassen. Quadlet nur zurückkopieren, wenn die Container-Datei mitgesichert wurde.\n"
    )
    return dest


def attach_models(token: str) -> list[dict[str, str]]:
    results = []
    for model_id in ATTACH_MODELS:
        form = {
            "id": model_id,
            "base_model_id": model_id,
            "name": model_id.replace(":latest", ""),
            "meta": {
                "description": "Lokales Chatmodell mit Bild-Tools generate_image und edit_image über den KI-Arbeitsplatz.",
                "toolIds": [TOOL_ID],
                "capabilities": {
                    "vision": True,
                    "file_upload": True,
                    "file_context": False,
                    "image_generation": False,
                },
            },
            "params": {
                "function_calling": "native",
                "system": (
                    "Lokale Bildwerkzeuge: Neues Bild erzeugen → generate_image. "
                    "Ein vorhandenes Bild ändern, umfärben, zuschneiden oder ein Ergebnis weiterbearbeiten "
                    "→ immer sofort edit_image aufrufen. Du siehst Dateien nicht; rufe trotzdem auf. "
                    "Nie nach einem Upload fragen. Nie behaupten, dass kein Bild da ist. "
                    "Wenn keine Datei existiert, liefert das Tool den Fehler. "
                    "Nur über Bilder sprechen, Theorie oder Danke → keine Tools."
                ),
            },
            "access_grants": [],
            "is_active": True,
        }
        existing = request_allow_404("GET", f"/api/v1/models/model?id={model_id}", token)
        if existing and existing.get("id") == model_id:
            payload = {**form, "id": model_id}
            updated = request("POST", "/api/v1/models/model/update", token, payload)
            results.append({"id": model_id, "action": "updated", "toolIds": (updated.get("meta") or {}).get("toolIds")})
        else:
            created = request("POST", "/api/v1/models/create", token, form)
            results.append({"id": model_id, "action": "created", "toolIds": (created.get("meta") or {}).get("toolIds")})
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="admin@localhost")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()
    if not WEBUI_DATA.joinpath("webui.db").is_file():
        raise SystemExit("Open-WebUI-Datenbank fehlt.")
    dest = backup()
    print(f"Backup: {dest}")
    token = signin(args.email, args.password)
    content = tool_content()
    form = {
        "id": TOOL_ID,
        "name": "Lokale Bilder",
        "content": content,
        "meta": {
            "description": "FLUX erzeugen und Qwen-Image-2.1 bearbeiten über den KI-Arbeitsplatz. Kein ComfyUI-Direktzugriff.",
        },
        "access_grants": [],
    }
    existing = request_allow_404("GET", f"/api/v1/tools/id/{TOOL_ID}", token)
    if existing and existing.get("id") == TOOL_ID:
        result = request("POST", f"/api/v1/tools/id/{TOOL_ID}/update", token, form)
        action = "updated"
    else:
        result = request("POST", "/api/v1/tools/create", token, form)
        action = "created"
    fetched = request("GET", f"/api/v1/tools/id/{TOOL_ID}", token)
    names = [spec.get("name") for spec in (fetched.get("specs") or result.get("specs") or [])]
    models = attach_models(token)
    print(
        json.dumps(
            {
                "ok": True,
                "action": action,
                "id": result.get("id"),
                "specs": names,
                "models": models,
                "backup": str(dest),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if sorted(n for n in names if n in {"generate_image", "edit_image"}) != ["edit_image", "generate_image"]:
        raise SystemExit(f"Unerwartete Tool-Specs: {names}")
    extra = [n for n in names if n not in {"generate_image", "edit_image"}]
    if extra:
        raise SystemExit(f"Zusätzliche öffentliche Tool-Methoden: {extra}")


if __name__ == "__main__":
    sys.exit(main())
