#!/usr/bin/env python3
"""Live Open WebUI chat tests for generate_image / edit_image. Localhost only."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path("/home/mike/Projects/Linux Lokales KI")
OUT = PROJECT / "benchmarks" / "open-webui-image-tools-20260921"
SOURCE = PROJECT / "benchmarks" / "qwen-image-21-smoke-20260921" / "input" / "source.png"
FLUX_WF = PROJECT / "apps" / "ki-workplace" / "workflows" / "flux2-klein-t2i-api-v1.json"
EDIT_WF = PROJECT / "apps" / "ki-workplace" / "workflows" / "qwen-image-21-edit-v1.json"
FLUX_SHA = "d9d752d52b1430bd3756908885146daea41279e29a7b6e3a9e05705572f39953"
EDIT_SHA = "78a0d0f445b08557d5e69139ce7f2d2ad547658bcaf90a10cfe154121b65bbe8"
BASE = "http://127.0.0.1:3000"
WORK = "http://127.0.0.1:8790"
MCP_HEALTH = "http://127.0.0.1:8765/health"
ARCHIVE = Path("/mnt/ai-archive/images/inbox")
STAGE = Path("/srv/ai/workspaces/ki-workplace-stage")
TOOL_ID = "local_images"
MODEL = "local-fast:latest"


def sh(*args: str) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    return (proc.stdout or proc.stderr or "").strip()


def gpu() -> dict:
    line = sh("nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits")
    parts = [p.strip() for p in line.split(",")]
    return {"used_mib": int(parts[0]), "free_mib": int(parts[1])}


def unit(name: str) -> str:
    return sh("systemctl", "--user", "is-active", name) or "unknown"


def canonical_sha(path: Path) -> str:
    data = json.loads(path.read_text())
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def signin() -> str:
    req = urllib.request.Request(
        f"{BASE}/api/v1/auths/signin",
        data=json.dumps({"email": "admin@localhost", "password": "admin"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())["token"]


def api(method: str, path: str, token: str, payload: dict | None = None, timeout: int = 30) -> tuple[int, dict | list | str]:
    data = None if payload is None else json.dumps(payload).encode()
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
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            if not raw:
                return response.status, {}
            try:
                return response.status, json.loads(raw)
            except json.JSONDecodeError:
                return response.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            body = {"error": raw.decode("utf-8", "replace")[:1200]}
        return exc.code, body


def upload_file(token: str, path: Path, content_type: str) -> dict:
    boundary = "----owui" + str(int(time.time() * 1000))
    filename = path.name
    blob = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + blob + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/files/?process=false",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())


def walk(obj, found: list[dict]) -> None:
    if isinstance(obj, dict):
        if "job_id" in obj or obj.get("name") in {"generate_image", "edit_image"}:
            found.append(obj)
        for value in obj.values():
            walk(value, found)
    elif isinstance(obj, list):
        for item in obj:
            walk(item, found)
    elif isinstance(obj, str) and ("job_id" in obj or "generate_image" in obj or "edit_image" in obj):
        try:
            walk(json.loads(obj), found)
        except Exception:
            if '"job_id"' in obj:
                found.append({"raw": obj[:400]})


def extract_jobs(payload) -> list[str]:
    found: list[dict] = []
    walk(payload, found)
    ids = []
    for item in found:
        job = item.get("job_id")
        if isinstance(job, str) and job not in ids:
            ids.append(job)
    return ids


def extract_tools(payload) -> list[str]:
    found: list[dict] = []
    walk(payload, found)
    names = []
    text = json.dumps(payload, ensure_ascii=False)
    for name in ("generate_image", "edit_image"):
        if name in text and name not in names:
            names.append(name)
    return names


def new_chat(token: str, title: str) -> str:
    status, body = api(
        "POST",
        "/api/v1/chats/new",
        token,
        {"chat": {"title": title, "models": [MODEL]}},
    )
    if status >= 300 or not isinstance(body, dict) or not body.get("id"):
        raise SystemExit(f"Chat anlegen fehlgeschlagen: {status} {body}")
    return str(body["id"])


def message_content(token: str, prompt: str, files: list[dict] | None) -> str | list[dict]:
    images: list[dict] = []
    for item in files or []:
        file_id = item.get("id")
        content_type = str(item.get("content_type") or "")
        if not file_id or not content_type.startswith("image/"):
            continue
        req = urllib.request.Request(
            f"{BASE}/api/v1/files/{file_id}/content",
            headers={"Authorization": f"Bearer {token}"},
        )
        blob = urllib.request.urlopen(req, timeout=30).read()
        import base64

        images.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{content_type};base64,{base64.b64encode(blob).decode('ascii')}"},
            }
        )
    if not images:
        return prompt
    return [{"type": "text", "text": prompt}, *images]


def current_leaf(chat: dict | list | str | None) -> str | None:
    if not isinstance(chat, dict):
        return None
    inner = chat.get("chat") if isinstance(chat.get("chat"), dict) else chat
    history = inner.get("history") if isinstance(inner, dict) else None
    if not isinstance(history, dict):
        return None
    current = history.get("currentId")
    return str(current) if current else None


def history_messages(chat: dict | list | str | None) -> list[dict]:
    if not isinstance(chat, dict):
        return []
    inner = chat.get("chat") if isinstance(chat.get("chat"), dict) else chat
    history = inner.get("history") if isinstance(inner, dict) else None
    if not isinstance(history, dict):
        return []
    messages = history.get("messages") or {}
    if not isinstance(messages, dict):
        return []
    node = history.get("currentId")
    chain: list[dict] = []
    seen: set[str] = set()
    while node and node not in seen:
        seen.add(str(node))
        item = messages.get(node)
        if not isinstance(item, dict):
            break
        chain.append(item)
        node = item.get("parentId")
    chain.reverse()
    out: list[dict] = []
    for item in chain:
        role = item.get("role")
        raw = item.get("content")
        if isinstance(raw, list):
            texts = [
                part.get("text")
                for part in raw
                if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
            ]
            raw = "\n".join(texts)
        if role in {"user", "assistant"} and isinstance(raw, str) and raw.strip():
            out.append({"role": role, "content": raw})
    return out


def complete(token: str, chat_id: str, prompt: str, files: list[dict] | None = None, timeout: int = 600) -> dict:
    import uuid

    user_message_id = str(uuid.uuid4())
    assistant_message_id = str(uuid.uuid4())
    now = int(time.time())
    content = message_content(token, prompt, files)
    _, existing = api("GET", f"/api/v1/chats/{chat_id}", token)
    parent = current_leaf(existing)
    prior = history_messages(existing)
    payload = {
        "model": MODEL,
        "chat_id": chat_id,
        "id": assistant_message_id,
        "tool_ids": [TOOL_ID],
        "stream": True,
        "features": {"image_generation": False, "web_search": False, "code_interpreter": False},
        "params": {"function_calling": "native"},
        "messages": [*prior, {"role": "user", "content": content}],
        "files": files or [],
        "user_message": {
            "id": user_message_id,
            "parentId": parent,
            "childrenIds": [assistant_message_id],
            "role": "user",
            "content": prompt,
            "files": files or [],
            "timestamp": now,
            "models": [MODEL],
        },
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE}/api/chat/completions",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    events: list[dict] = []
    text_parts: list[str] = []
    status = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            ctype = (response.headers.get("Content-Type") or "").lower()
            if "text/event-stream" in ctype:
                buf = b""
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        raw = line.decode("utf-8", "replace").strip()
                        if not raw.startswith("data:"):
                            continue
                        payload_text = raw[5:].strip()
                        if not payload_text or payload_text == "[DONE]":
                            continue
                        try:
                            event = json.loads(payload_text)
                        except json.JSONDecodeError:
                            continue
                        events.append(event)
                        choices = event.get("choices") if isinstance(event, dict) else None
                        if isinstance(choices, list) and choices:
                            delta = (choices[0] or {}).get("delta") or {}
                            content = delta.get("content")
                            if isinstance(content, str):
                                text_parts.append(content)
                        if isinstance(event, dict) and isinstance(event.get("content"), str):
                            text_parts.append(event["content"])
            else:
                raw = response.read()
                try:
                    body = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    body = {"raw": raw.decode("utf-8", "replace")[:1200]}
                events.append(body if isinstance(body, dict) else {"body": body})
                if isinstance(body, dict):
                    choices = body.get("choices") or []
                    if choices:
                        msg = (choices[0] or {}).get("message") or {}
                        if isinstance(msg.get("content"), str):
                            text_parts.append(msg["content"])
    except urllib.error.HTTPError as exc:
        status = exc.code
        events.append({"error": exc.read().decode("utf-8", "replace")[:1200]})
    chat_status, chat = api("GET", f"/api/v1/chats/{chat_id}", token)
    state_path = Path("/srv/ai/apps/open-webui/data/cache/local_images_jobs") / f"{chat_id}.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    combined = {"events": events[-20:], "chat": chat, "state": state, "text": "".join(text_parts)[-4000:]}
    job_ids = extract_jobs(combined)
    if state.get("last_job_id") and state["last_job_id"] not in job_ids:
        job_ids.append(state["last_job_id"])
    return {
        "http_status": status,
        "completion": {"event_count": len(events), "text": "".join(text_parts)[-2000:]},
        "chat_status": chat_status,
        "chat": chat,
        "state": state,
        "job_ids": job_ids,
        "tools": extract_tools(combined),
        "files": collect_files(chat if isinstance(chat, dict) else {}),
    }


def collect_files(chat: dict) -> list[dict]:
    files = []

    def inner(obj):
        if isinstance(obj, dict):
            if obj.get("type") == "image" and obj.get("url"):
                files.append({"type": "image", "url_prefix": str(obj.get("url"))[:32], "local_ki_output": obj.get("local_ki_output")})
            for value in obj.values():
                inner(value)
        elif isinstance(obj, list):
            for item in obj:
                inner(item)

    inner(chat)
    return files


def job_manifest(job_id: str) -> dict | None:
    if not ARCHIVE.is_dir():
        return None
    matches = list(ARCHIVE.glob(f"*/{job_id}/manifest.json"))
    if not matches:
        return None
    return json.loads(matches[0].read_text())


def record(name: str, payload: dict, ok: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {**payload, "ok": ok, "name": name, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (OUT / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"{'PASS' if ok else 'FAIL'} {name}", flush=True)


def gpu_cleanup() -> None:
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"{WORK}/api/gpu/cleanup",
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            ),
            timeout=180,
        ).read()
    except Exception:
        pass
    time.sleep(2)
    staged = list(STAGE.glob("ui_stage_*")) if STAGE.is_dir() else []
    for path in staged:
        if time.time() - path.stat().st_mtime > 3600:
            path.unlink(missing_ok=True)
    return {
        "comfy": unit("comfyui.service"),
        "ollama": unit("ollama.service"),
        "gpu": gpu(),
        "staged": [p.name for p in (list(STAGE.glob('ui_stage_*')) if STAGE.is_dir() else [])],
        "ki_edit": sh("bash", "-lc", "ls /tmp/ki_edit_* 2>/dev/null | wc -l") or "0",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    flux_sha = canonical_sha(FLUX_WF)
    edit_sha = canonical_sha(EDIT_WF)
    results["sha"] = {"flux": flux_sha, "edit": edit_sha}
    record("SHA", results["sha"], flux_sha == FLUX_SHA and edit_sha == EDIT_SHA)

    mcp = json.loads(urllib.request.urlopen(MCP_HEALTH, timeout=5).read())
    record(
        "MCP-HEALTH",
        mcp,
        mcp.get("status") == "ok"
        and mcp.get("version") == "1.3.0"
        and mcp.get("tools") == [
            "generate_image",
            "edit_image",
            "memory_load",
            "memory_update",
            "pdf_read",
            "pdf_inspect",
            "pdf_create",
            "pdf_edit",
            "pdf_merge",
            "pdf_split",
            "pdf_ocr",
            "pdf_render",
            "pdf_vision_qa",
        ],
    )

    token = signin()
    tool_status, tool = api("GET", f"/api/v1/tools/id/{TOOL_ID}", token)
    specs = [item.get("name") for item in (tool.get("specs") or [])] if isinstance(tool, dict) else []
    record("TOOL", {"status": tool_status, "specs": specs}, specs == ["generate_image", "edit_image"] or set(specs) == {"generate_image", "edit_image"})

    # CHAT-IMAGE-TALK
    talk_chat = new_chat(token, "CHAT-IMAGE-TALK")
    before_talk = {p.parent.name for p in ARCHIVE.glob("*/*/manifest.json")} if ARCHIVE.is_dir() else set()
    talk = complete(token, talk_chat, "Warum wirken KI-Bilder manchmal gemalt?", timeout=180)
    after_talk = {p.parent.name for p in ARCHIVE.glob("*/*/manifest.json")} if ARCHIVE.is_dir() else set()
    talk_ok = not talk["job_ids"] and not (talk.get("state") or {}).get("last_job_id")
    record("CHAT-IMAGE-TALK", talk, talk_ok)

    # CHAT-BAD-FILE
    bad_path = OUT / "bad.txt"
    bad_path.write_text("das ist kein bild\n")
    bad_upload = upload_file(token, bad_path, "text/plain")
    bad_chat = new_chat(token, "CHAT-BAD-FILE")
    bad_files = [
        {
            "type": "file",
            "id": bad_upload.get("id"),
            "name": "bad.txt",
            "content_type": "text/plain",
            "file": bad_upload,
        }
    ]
    before_jobs = {p.parent.name for p in ARCHIVE.glob("*/*/manifest.json")} if ARCHIVE.is_dir() else set()
    bad = complete(
        token,
        bad_chat,
        "Bearbeite dieses Bild und mache den Himmel blau.",
        files=bad_files,
        timeout=180,
    )
    after_jobs = {p.parent.name for p in ARCHIVE.glob("*/*/manifest.json")} if ARCHIVE.is_dir() else set()
    new_jobs = after_jobs - before_jobs
    bad_ok = not new_jobs
    record("CHAT-BAD-FILE", {**bad, "upload": bad_upload, "new_jobs": sorted(new_jobs)}, bad_ok)

    # CHAT-GENERATE
    gen_chat = new_chat(token, "CHAT-GENERATE")
    gen = complete(token, gen_chat, "Erstelle ein Bild von einem roten Apfel auf einem weißen Tisch.", timeout=420)
    gen_jobs = gen["job_ids"]
    gen_man = job_manifest(gen_jobs[0]) if gen_jobs else None
    gen_ok = (
        len(gen_jobs) == 1
        and (gen_man or {}).get("workflow_id") == "flux2-klein-t2i-v1"
    )
    record("CHAT-GENERATE", {**gen, "manifest": gen_man}, gen_ok)
    gpu_cleanup()

    # CHAT-EDIT-ORIGINAL + SIZE-512
    if not SOURCE.is_file():
        raise SystemExit(f"Original fehlt: {SOURCE}")
    orig = upload_file(token, SOURCE, "image/png")
    orig_files = [
        {
            "type": "file",
            "id": orig.get("id"),
            "name": SOURCE.name,
            "content_type": "image/png",
            "file": orig,
        }
    ]
    edit_chat = new_chat(token, "CHAT-EDIT-ORIGINAL")
    edit = complete(
        token,
        edit_chat,
        "Ändere nur den roten Apfel zu grün. Alles andere soll unverändert bleiben.",
        files=orig_files,
        timeout=540,
    )
    edit_jobs = edit["job_ids"]
    edit_man = job_manifest(edit_jobs[0]) if edit_jobs else None
    edit_ok = (
        len(edit_jobs) == 1
        and (edit_man or {}).get("workflow_id") == "qwen-image-21-edit-v1"
        and (edit_man or {}).get("width") == 512
    )
    record("CHAT-EDIT-ORIGINAL", {**edit, "manifest": edit_man, "upload": {"id": orig.get("id"), "filename": orig.get("filename")}}, edit_ok)
    record("CHAT-SIZE-512", {"job_id": edit_jobs[0] if edit_jobs else None, "width": (edit_man or {}).get("width"), "height": (edit_man or {}).get("height")}, bool(edit_ok and (edit_man or {}).get("width") == 512))
    gpu_cleanup()

    # CHAT-NO-DOUBLE-EDIT
    before_thanks = {p.parent.name for p in ARCHIVE.glob("*/*/manifest.json")} if ARCHIVE.is_dir() else set()
    thanks = complete(token, edit_chat, "Danke, das sieht gut aus.", files=None, timeout=180)
    after_thanks = {p.parent.name for p in ARCHIVE.glob("*/*/manifest.json")} if ARCHIVE.is_dir() else set()
    thanks_new = sorted(after_thanks - before_thanks)
    thanks_ok = not thanks_new
    record("CHAT-NO-DOUBLE-EDIT", {**thanks, "new_jobs": thanks_new}, thanks_ok)

    # CHAT-EXPLICIT-SECOND-EDIT
    second = complete(
        token,
        edit_chat,
        "Nimm dieses Ergebnis und ändere zusätzlich den Hintergrund zu blau.",
        files=orig_files,
        timeout=540,
    )
    second_jobs = [j for j in second["job_ids"] if j not in set(edit_jobs)]
    second_man = job_manifest(second_jobs[0]) if second_jobs else None
    second_ok = (
        len(second_jobs) == 1
        and (second_man or {}).get("workflow_id") == "qwen-image-21-edit-v1"
        and (second_man or {}).get("input_sha256") == (edit_man or {}).get("output_sha256")
        and (second.get("state") or {}).get("used_second_edit") is True
    )
    record("CHAT-EXPLICIT-SECOND-EDIT", {**second, "new_job": second_jobs, "manifest": second_man}, second_ok)
    gpu_cleanup()

    # CHAT-SIZE-EXPLICIT
    size_chat = new_chat(token, "CHAT-SIZE-EXPLICIT")
    size = complete(
        token,
        size_chat,
        "Ändere nur den roten Apfel zu grün. Alles andere soll unverändert bleiben. Bitte in 1024 Pixeln.",
        files=orig_files,
        timeout=540,
    )
    size_jobs = size["job_ids"]
    size_man = job_manifest(size_jobs[0]) if size_jobs else None
    size_ok = bool(size_jobs) and (size_man or {}).get("width") == 1024
    record("CHAT-SIZE-EXPLICIT", {**size, "manifest": size_man}, size_ok)
    gpu_cleanup()

    # workplace generate regression (same endpoint as MCP/UI)
    t0 = time.monotonic()
    req = urllib.request.Request(
        f"{WORK}/api/images/generate",
        data=json.dumps(
            {
                "prompt": "Ein kleiner roter Wuerfel auf einem neutralen grauen Hintergrund, Studiofotografie",
                "width": 512,
                "height": 512,
                "seed": 42,
            }
        ).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            flux_body = json.loads(response.read())
            flux_status = 200
    except urllib.error.HTTPError as exc:
        flux_status = exc.code
        flux_body = json.loads(exc.read() or b"{}")
    flux_runtime = round(time.monotonic() - t0, 3)
    flux_man = {}
    if flux_body.get("manifest") and Path(flux_body["manifest"]).is_file():
        flux_man = json.loads(Path(flux_body["manifest"]).read_text())
    flux_ok = flux_status == 200 and flux_body.get("ok") is True and flux_man.get("workflow_sha256") == FLUX_SHA
    record("WORKPLACE-GENERATE", {"status": flux_status, "body": flux_body, "runtime": flux_runtime, "manifest": flux_man}, flux_ok)

    # GPU cleanup via existing workplace endpoint
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"{WORK}/api/gpu/cleanup",
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            ),
            timeout=180,
        ).read()
        cleanup_ok = True
    except Exception as exc:
        cleanup_ok = False
        flux_body = {**flux_body, "cleanup_error": str(exc)}
    time.sleep(3)
    cleanup = gpu_cleanup()
    record("CLEANUP", cleanup, cleanup.get("gpu", {}).get("used_mib", 99999) < 8000 and not cleanup.get("staged"))

    summary = {
        "tests": {p.stem: json.loads(p.read_text()).get("ok") for p in sorted(OUT.glob("*.json")) if p.name != "summary.json"},
        "cleanup": cleanup,
        "git": sh("git", "-C", str(PROJECT), "rev-parse", "HEAD"),
    }
    summary["pass"] = all(bool(v) for k, v in summary["tests"].items() if k != "summary")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
