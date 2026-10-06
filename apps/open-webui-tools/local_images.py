"""Open WebUI Tools adapter: generate_image / edit_image via KI-Arbeitsplatz.

Does not talk to ComfyUI. Does not change local-tools MCP schemas.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from local_image_policy import (
        choose_source_file,
        is_non_edit_ack,
        resolve_named_size,
        snap_edit_size,
    )
except ImportError:  # concatenated into Open WebUI tool content
    pass


WORKPLACE_DEFAULT = "http://host.containers.internal:8790"
STATE_DIR = Path("/app/backend/data/cache/local_images_jobs")
GENERATE_TIMEOUT = 300
EDIT_TIMEOUT = 480
STAGE_TIMEOUT = 60


def _workplace_url() -> str:
    return WORKPLACE_DEFAULT.rstrip("/")


def _json_request(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw)
            message = detail.get("error") or f"HTTP {exc.code}"
        except Exception:
            message = f"HTTP {exc.code}"
        raise RuntimeError(message) from exc
    except Exception as exc:
        raise RuntimeError(f"KI-Arbeitsplatz nicht erreichbar: {exc}") from exc
    data = json.loads(raw)
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "Bildauftrag fehlgeschlagen.")
    return data


def _stage_bytes(name: str, blob: bytes, timeout: int = STAGE_TIMEOUT) -> dict[str, Any]:
    boundary = f"----ki{int(time.time() * 1000)}"
    filename = Path(name or "upload.png").name
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        blob,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    request = urllib.request.Request(
        f"{_workplace_url()}/api/images/stage",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            message = json.loads(raw).get("error") or f"HTTP {exc.code}"
        except Exception:
            message = f"HTTP {exc.code}"
        raise RuntimeError(message) from exc
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "Datei konnte nicht übernommen werden.")
    return data


def _read_state(chat_id: str | None) -> dict[str, Any]:
    if not chat_id:
        return {}
    path = STATE_DIR / f"{chat_id}.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _write_state(chat_id: str | None, payload: dict[str, Any]) -> None:
    if not chat_id:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{chat_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _file_bytes(item: dict[str, Any]) -> tuple[str, bytes]:
    path = item.get("path") or ""
    if path:
        host = Path(path)
        if host.is_file():
            return host.name, host.read_bytes()
    file_id = item.get("id")
    if file_id:
        uploads = Path("/app/backend/data/uploads")
        if uploads.is_dir():
            matches = sorted(uploads.glob(f"{file_id}_*"))
            if matches:
                return matches[0].name, matches[0].read_bytes()
    url = str(item.get("url") or "")
    if url.startswith("data:image/") and "," in url:
        import base64

        header, b64 = url.split(",", 1)
        return "upload.png", base64.b64decode(b64)
    raise RuntimeError("Hochgeladene Bilddatei ist im Chat nicht lesbar.")


def _output_data_url(job_id: str) -> str:
    import base64

    url = f"{_workplace_url()}/api/images/jobs/{job_id}/output"
    with urllib.request.urlopen(url, timeout=30) as response:
        blob = response.read()
    if not blob.startswith(b"\x89PNG"):
        raise RuntimeError("Das Ergebnis ist kein gültiges PNG.")
    return "data:image/png;base64," + base64.b64encode(blob).decode("ascii")


def _error(message: str) -> str:
    return json.dumps({"status": "error", "error": message}, ensure_ascii=False)


def _latest_user_text(messages: list | None) -> str:
    if not isinstance(messages, list):
        return ""
    for item in reversed(messages):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        raw = item.get("content")
        if isinstance(raw, list):
            raw = "\n".join(
                str(part.get("text") or "")
                for part in raw
                if isinstance(part, dict)
            )
        text = str(raw or "").strip()
        if text:
            return text
    return ""


async def _user_text_from_chat(chat_id: str | None) -> str:
    if not chat_id:
        return ""
    try:
        from open_webui.models.chats import Chats

        chat = await Chats.get_chat_by_id(chat_id)
        data = (getattr(chat, "chat", None) or {}) if chat else {}
        if not isinstance(data, dict):
            return ""
        history = data.get("history") or {}
        messages = history.get("messages") or {}
        node = history.get("currentId")
        seen: set[str] = set()
        while node and str(node) not in seen:
            seen.add(str(node))
            item = messages.get(node) if isinstance(messages, dict) else None
            if not isinstance(item, dict):
                break
            if item.get("role") == "user":
                return _latest_user_text([item])
            node = item.get("parentId")
    except Exception:
        return ""
    return ""


async def _collect_files(extra: list | None, chat_id: str | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: Any) -> None:
        if not isinstance(item, dict):
            return
        nested = item.get("file") if isinstance(item.get("file"), dict) else {}
        fid = str(item.get("id") or nested.get("id") or "")
        key = fid or f"anon:{len(items)}"
        if key in seen:
            return
        seen.add(key)
        items.append(item)

    for item in extra or []:
        add(item)
    if not chat_id:
        return items
    try:
        from open_webui.models.chats import Chats

        chat = await Chats.get_chat_by_id(chat_id)
        data = (getattr(chat, "chat", None) or {}) if chat else {}
        if not isinstance(data, dict):
            return items
        for item in data.get("files") or []:
            add(item)
        history = (data.get("history") or {}).get("messages") or {}
        if isinstance(history, dict):
            for message in history.values():
                if isinstance(message, dict):
                    for item in message.get("files") or []:
                        add(item)
    except Exception:
        return items
    return items


async def _emit_image(event_emitter, chat_id, message_id, data_url: str) -> None:
    files = [{"type": "image", "url": data_url, "local_ki_output": True}]
    if chat_id and message_id:
        try:
            from open_webui.models.chats import Chats
            from open_webui.utils.misc import is_saved_chat_id

            if is_saved_chat_id(chat_id):
                stored = await Chats.add_message_files_by_id_and_message_id(chat_id, message_id, files)
                if stored:
                    files = stored
        except Exception:
            pass
    if not event_emitter:
        return
    payload = {"type": "files", "data": {"files": files}}
    await event_emitter(payload)
    await event_emitter({"type": "chat:message:files", "data": {"files": files}})


try:
    from pydantic import BaseModel
except ImportError:
    BaseModel = object  # type: ignore


class Tools:
    class Valves(BaseModel):
        WORKPLACE_URL: str = WORKPLACE_DEFAULT

    def __init__(self):
        self.valves = self.Valves()

    def _apply_valves(self) -> None:
        global WORKPLACE_DEFAULT
        WORKPLACE_DEFAULT = getattr(self.valves, "WORKPLACE_URL", WORKPLACE_DEFAULT) or WORKPLACE_DEFAULT

    async def generate_image(
        self,
        prompt: str,
        width: int | None = None,
        height: int | None = None,
        seed: int = 42,
        __event_emitter__: Any = None,
        __chat_id__: str = None,
        __message_id__: str = None,
    ) -> str:
        """Create a new local picture with FLUX.2 [klein]. Call only when the user asks to create, draw, generate, or make a NEW picture. Do not call this to change an existing picture. Do not call this when the user is only talking about images, quality, theory, or saying thanks.

        Omit width/height unless the user named 512, 768, or 1024. Default is 1024.
        """
        self._apply_valves()
        try:
            if not (prompt or "").strip():
                return _error("Bitte einen Bildtext eingeben.")
            size = resolve_named_size(prompt, width, height) or (1024, 1024)
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Erzeuge lokales Bild…", "done": False}}
                )
            result = _json_request(
                f"{_workplace_url()}/api/images/generate",
                {"prompt": prompt, "width": size[0], "height": size[1], "seed": int(seed or 42)},
                GENERATE_TIMEOUT,
            )
            job_id = result["job_id"]
            data_url = _output_data_url(job_id)
            _write_state(
                __chat_id__,
                {
                    "last_job_id": job_id,
                    "last_kind": "generate",
                    "original_file_ids": [],
                    "width": size[0],
                    "height": size[1],
                },
            )
            await _emit_image(__event_emitter__, __chat_id__, __message_id__, data_url)
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": "Bild erstellt", "done": True}})
            return json.dumps(
                {
                    "status": "success",
                    "message": "Bild ist im Chat sichtbar. Keinen Pfad vorlesen.",
                    "job_id": job_id,
                    "runtime_seconds": result.get("runtime_seconds"),
                    "width": size[0],
                    "height": size[1],
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            return _error(str(exc))

    async def edit_image(
        self,
        instruction: str,
        width: int | None = None,
        height: int | None = None,
        seed: int = 42,
        __files__: list | None = None,
        __messages__: list | None = None,
        __event_emitter__: Any = None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __request__: Any = None,
    ) -> str:
        """Edit an existing picture with local Qwen-Image-2.1. ALWAYS call this when the user wants to change, recolor, crop, restyle, or further edit a picture — including 'dieses Ergebnis', 'zuletzt erzeugte', or a named size such as 1024. You cannot see files; call anyway. Do not ask to upload. Do not claim that no image is present. If no file exists the tool returns the error. Do not call after thanks or small talk. Do not call generate_image for edits.

        Always prefer the original user upload. Use a previous KI result only if the user clearly said to edit that result. Omit width/height unless the user named 512, 768, or 1024.
        Never invent a host path. Never pass a URL.
        """
        self._apply_valves()
        try:
            if not (instruction or "").strip():
                return _error("Bitte eine Bearbeitungsanweisung eingeben.")
            user_text = _latest_user_text(__messages__)
            if not user_text:
                user_text = await _user_text_from_chat(__chat_id__)
            policy_text = "\n".join(part for part in (instruction, user_text) if part)
            if is_non_edit_ack(user_text or instruction):
                return _error("Kein weiterer Bildauftrag. Das letzte Ergebnis bleibt unverändert.")

            files = await _collect_files(__files__, __chat_id__)
            state = _read_state(__chat_id__)
            chosen = choose_source_file(files, policy_text, last_job_id=state.get("last_job_id"))

            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Bereite Bildbearbeitung vor…", "done": False}}
                )

            if chosen["source"] == "last_job":
                with urllib.request.urlopen(
                    f"{_workplace_url()}/api/images/jobs/{chosen['job_id']}/output", timeout=30
                ) as response:
                    blob = response.read()
                staged = _stage_bytes("previous-result.png", blob)
            else:
                item = chosen["file"]
                if __request__ is not None and item.get("id") and not item.get("path"):
                    try:
                        from open_webui.models.files import Files

                        record = await Files.get_file_by_id(item["id"])
                        if record and getattr(record, "path", None):
                            item = {**item, "path": record.path, "filename": getattr(record, "filename", item.get("name"))}
                    except Exception:
                        pass
                name, blob = _file_bytes(item)
                staged = _stage_bytes(name, blob)

            size = resolve_named_size(policy_text, width, height)
            if size is None:
                size = snap_edit_size(int(staged.get("width") or 512), int(staged.get("height") or 512))

            result = _json_request(
                f"{_workplace_url()}/api/images/edit",
                {
                    "instruction": instruction.strip(),
                    "input_path": staged["path"],
                    "width": size[0],
                    "height": size[1],
                    "seed": int(seed or 42),
                    "preserve_alpha": False,
                },
                EDIT_TIMEOUT,
            )
            job_id = result["job_id"]
            data_url = _output_data_url(job_id)
            originals = list(state.get("original_file_ids") or [])
            if chosen["source"] == "original":
                fid = str((chosen.get("file") or {}).get("id") or "")
                if fid and fid not in originals:
                    originals.append(fid)
            _write_state(
                __chat_id__,
                {
                    "last_job_id": job_id,
                    "last_kind": "edit",
                    "original_file_ids": originals,
                    "used_second_edit": chosen["source"] != "original",
                    "width": size[0],
                    "height": size[1],
                },
            )
            await _emit_image(__event_emitter__, __chat_id__, __message_id__, data_url)
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Bild bearbeitet", "done": True}}
                )
            return json.dumps(
                {
                    "status": "success",
                    "message": "Bearbeitetes Bild ist im Chat sichtbar. Keinen internen Pfad vorlesen.",
                    "job_id": job_id,
                    "runtime_seconds": result.get("runtime_seconds"),
                    "width": size[0],
                    "height": size[1],
                    "source": chosen["source"],
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            return _error(str(exc))
