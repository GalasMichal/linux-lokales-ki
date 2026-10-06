#!/usr/bin/env python3
"""PDF Agent E2E via qwen serve HTTP bridge. approvalMode default, proceed_once votes, no YOLO.

Natural-language user prompt → local-fast → ToolSearch → MCP pdf_* → QA.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

PROJECT = Path("/home/mike/Projects/Linux Lokales KI")
sys.path.insert(0, str(PROJECT / "benchmarks"))
from quality_cutover_e2e import (  # noqa: E402
    EventCollector,
    http_json,
    nvidia,
    ollama_ps,
    pick_allow,
    sse_loop,
    wait_for_turn,
)

OUT = PROJECT / "benchmarks" / "pdf_agent_e2e_2026-09-28"
SRC = OUT / "input" / "agent_e2e_source.pdf"
EDITED = OUT / "output" / "agent_e2e_edited.pdf"
MODEL_ID = "local-fast(openai)"
WORKSPACE = str(PROJECT)

USER_PROMPT = f"""Bearbeite diese PDF mit den MCP-Tools pdf_inspect, pdf_edit, pdf_read (ToolSearch ok):
{SRC}

Pflicht-Ersetzungen in EINEM pdf_edit call, mode=replace, output={EDITED}:
replacements="Project Status: Draft=>Project Status: Final;Amount: 1250 EUR=>Amount: 1490 EUR;Pending=>Done   "
(Hinweis: Done + 3 Leerzeichen = 7 Zeichen wie Pending, Layout bleibt sauber.)

Danach pdf_read der Output-PDF und kurz bestätigen, dass Final/1490/Done drin sind und Draft/1250/Pending weg.
Optional pdf_render/pdf_vision_qa. Kein Shell, kein WriteFile für die PDF, kein YOLO.
"""


def vote_pending(session_id: str, collector: EventCollector) -> None:
    try:
        status = http_json("GET", f"/session/{session_id}/status")
    except Exception:
        return
    for item in status.get("pendingInteractions") or []:
        request_id = item.get("requestId") or item.get("id")
        if not request_id:
            continue
        oid = pick_allow(item.get("options") or []) or "proceed_once"
        try:
            http_json(
                "POST",
                f"/session/{session_id}/permission/{request_id}",
                {"outcome": {"outcome": "selected", "optionId": oid}},
            )
            collector.votes.append({"requestId": request_id, "optionId": oid, "ok": True})
            print(f"[vote] {request_id} -> {oid}", flush=True)
        except Exception as exc:
            print(f"[vote] fail {exc}", flush=True)


def tool_names(collector: EventCollector) -> list[str]:
    names: list[str] = []
    for item in collector.tools:
        blob = " ".join(str(item.get(k) or "") for k in ("name", "title"))
        names.append(blob)
    return names


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def technical_qa(src: Path, edited: Path) -> dict:
    import pymupdf

    src_meta = json.loads((OUT / "input" / "source_meta.json").read_text())
    raw = edited.read_bytes()
    result: dict = {
        "exists": edited.is_file(),
        "size": len(raw) if edited.is_file() else 0,
        "header_ok": raw[:5] == b"%PDF-" if raw else False,
        "sha256": sha256(edited) if edited.is_file() else "",
        "src_sha256": src_meta["sha256"],
        "hash_changed": False,
        "pages": 0,
        "page_sizes": [],
        "text_checks": {},
        "renders": {},
        "pass": False,
    }
    if not edited.is_file() or result["size"] == 0 or not result["header_ok"]:
        return result
    result["hash_changed"] = result["sha256"] != result["src_sha256"]
    doc = pymupdf.open(edited)
    result["pages"] = doc.page_count
    result["page_sizes"] = [[round(p.rect.width, 2), round(p.rect.height, 2)] for p in doc]
    t1 = doc[0].get_text()
    t2 = doc[1].get_text() if doc.page_count > 1 else ""
    checks = {
        "has_Final": "Final" in t1,
        "no_Draft_status": "Project Status: Draft" not in t1 and "Status: Draft" not in t1,
        "has_1490": "1490" in t1,
        "no_1250": "1250" not in t1,
        "has_Implementation_Done": ("Implementation" in t2 and "Done" in t2),
        "no_Pending_status_cell": "Pending" not in t2.split("Additional notes")[0],
        "customer_preserved": "Example GmbH" in t1,
        "title_preserved": "PDF Agent End-to-End Test" in t1,
        "analysis_still_open": "Analysis" in t2 and "Open" in t2,
        "pages_eq_2": doc.page_count == 2,
        "page_size_stable": result["page_sizes"] == src_meta.get("page_sizes"),
    }
    result["text_checks"] = checks
    result["text_p1"] = t1
    result["text_p2"] = t2
    # render pages
    for i in (0, 1):
        png = OUT / "renders" / f"edited-p{i+1}.png"
        pix = doc[i].get_pixmap(dpi=140)
        png.write_bytes(pix.tobytes("png"))
        result["renders"][f"page_{i+1}"] = {"path": str(png), "bytes": png.stat().st_size}
    doc.close()
    result["pass"] = all(checks.values()) and result["hash_changed"] and all(
        v["bytes"] > 0 for v in result["renders"].values()
    )
    return result


def negative_tests() -> dict:
    sys.path.insert(0, str(PROJECT / "apps" / "local-tools"))
    from pdf_tools import pdf_edit
    from errors import ToolError

    out: dict = {}
    # 1 missing search text
    try:
        r = pdf_edit(
            str(SRC),
            str(OUT / "negatives" / "should_not_exist_missing.pdf"),
            replacements="THIS_TEXT_DOES_NOT_EXIST_XYZ=>Nope",
            mode="replace",
            workspace=str(PROJECT),
        )
        out["missing_text"] = {"ok": r.get("ok"), "error": r.get("error"), "pass": r.get("ok") is False}
    except ToolError as exc:
        out["missing_text"] = {"ok": False, "error": str(exc), "pass": True}
    except Exception as exc:
        out["missing_text"] = {"ok": False, "error": str(exc), "pass": True}

    # 2 invalid pdf (wrong content, .pdf suffix)
    bad = OUT / "negatives" / "not-a-pdf.pdf"
    bad.write_bytes(b"NOT_A_PDF_CONTENT")
    try:
        r = pdf_edit(
            str(bad),
            str(OUT / "negatives" / "from_bad.pdf"),
            replacements="a=>b",
            mode="replace",
            workspace=str(PROJECT),
        )
        out["invalid_pdf"] = {"ok": r.get("ok"), "error": r.get("error"), "pass": r.get("ok") is False}
    except ToolError as exc:
        out["invalid_pdf"] = {"ok": False, "error": str(exc), "pass": True}
    except Exception as exc:
        out["invalid_pdf"] = {"ok": False, "error": str(exc), "pass": True}

    # 3 output outside allowed root
    try:
        r = pdf_edit(
            str(SRC),
            "/etc/agent_e2e_forbidden.pdf",
            replacements="Draft=>Final",
            mode="replace",
            workspace=str(PROJECT),
        )
        out["outside_root"] = {"ok": r.get("ok"), "error": r.get("error"), "pass": r.get("ok") is False}
    except ToolError as exc:
        out["outside_root"] = {"ok": False, "error": str(exc), "pass": True}
    except Exception as exc:
        out["outside_root"] = {"ok": False, "error": str(exc), "pass": True}

    out["all_pass"] = all(bool(v.get("pass")) for v in out.values())
    return out


def call_vision_qa(path: Path) -> dict:
    sys.path.insert(0, "/srv/ai/apps/local-tools")
    # Prefer live deployed module
    import importlib
    import pdf_vision

    importlib.reload(pdf_vision)
    return pdf_vision.pdf_vision_qa(str(path), pages="1-2", strict=False, workspace=str(PROJECT))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "output").mkdir(exist_ok=True)
    (OUT / "renders").mkdir(exist_ok=True)
    (OUT / "negatives").mkdir(exist_ok=True)
    if EDITED.exists():
        EDITED.unlink()

    # Health
    mcp_health = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5).read())
    assert "pdf_edit" in mcp_health["tools"]
    assert SRC.is_file()

    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    before = {"nvidia": nvidia(), "ollama_ps": ollama_ps()}

    # Drop stale attached session so tool/history replay cannot fake PASS.
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    if created.get("attached") and created.get("sessionId"):
        try:
            http_json("DELETE", f"/session/{created['sessionId']}")
        except Exception as exc:
            print(f"[session] delete old failed: {exc}", flush=True)
        created = http_json("POST", "/session", {"cwd": WORKSPACE})
    session_id = created["sessionId"]
    print(f"[session] {session_id} attached={created.get('attached')}", flush=True)
    model = http_json("POST", f"/session/{session_id}/model", {"modelId": MODEL_ID})
    print(f"[model] {model}", flush=True)

    collector = EventCollector(session_id=session_id)
    stop = threading.Event()
    thr = threading.Thread(target=sse_loop, args=(session_id, collector, stop), daemon=True)
    thr.start()
    time.sleep(0.5)

    http_json(
        "POST",
        f"/session/{session_id}/prompt",
        {"prompt": [{"type": "text", "text": USER_PROMPT}]},
        timeout=60,
    )
    print("[prompt] sent", flush=True)

    # Long wait — PDF edit + vision can take several minutes on local-fast
    deadline = time.time() + 900
    while time.time() < deadline:
        vote_pending(session_id, collector)
        status = http_json("GET", f"/session/{session_id}/status")
        elapsed = round(time.perf_counter() - t0, 1)
        print(
            f"[wait {elapsed}s] active={status.get('hasActivePrompt')} wait={status.get('isWaitingForPermission')} "
            f"tools={len(collector.tools)} votes={len(collector.votes)} edited={EDITED.is_file()}",
            flush=True,
        )
        if not status.get("hasActivePrompt") and not status.get("isWaitingForPermission") and elapsed > 15:
            # allow file flush
            time.sleep(2)
            status2 = http_json("GET", f"/session/{session_id}/status")
            if not status2.get("hasActivePrompt"):
                break
        time.sleep(2)

    stop.set()
    thr.join(timeout=5)

    tech = technical_qa(SRC, EDITED) if EDITED.is_file() else {"pass": False, "error": "edited missing"}
    vision = None
    vision_pass = False
    if EDITED.is_file():
        try:
            vision = call_vision_qa(EDITED)
            issues = vision.get("issues") or []
            high = [i for i in issues if str(i.get("severity") or "").lower() == "high"]
            # Medium empty_page on short letter pages is acceptable; fail only on high.
            vision_pass = len(high) == 0 and vision.get("invalid_output") is not True
            vision["high_issues"] = high
            vision["vision_pass"] = vision_pass
        except Exception as exc:
            vision = {"ok": False, "error": str(exc), "vision_pass": False}
            vision_pass = False

    negatives = negative_tests()

    yolo = any("yolo" in str(v.get("optionId") or "").lower() for v in collector.votes)
    names = tool_names(collector)
    used_pdf = any("pdf_" in n.lower() for n in names)
    used_toolsearch = any("toolsearch" in n.lower().replace("_", "") or "tool_search" in n.lower() for n in names)

    agent_pass = bool(
        EDITED.is_file()
        and tech.get("pass")
        and used_pdf
        and not yolo
        and all(str(v.get("optionId") or "").lower() in {"proceed_once", "allow_once", "allow-once", "allow"} or "once" in str(v.get("optionId") or "").lower() for v in collector.votes)
    )

    report = {
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "model": MODEL_ID,
        "session_id": session_id,
        "before": before,
        "after": {"nvidia": nvidia(), "ollama_ps": ollama_ps()},
        "mcp_version": mcp_health.get("version"),
        "user_prompt": USER_PROMPT,
        "source": str(SRC),
        "edited": str(EDITED),
        "tool_names": names,
        "votes": collector.votes,
        "yolo": yolo,
        "used_pdf_tools": used_pdf,
        "used_toolsearch": used_toolsearch,
        "agent_texts_tail": "".join(collector.texts)[-2000:],
        "technical_qa": tech,
        "vision_qa": vision,
        "negatives": negatives,
        "agent_pass": agent_pass,
        "overall_pass": bool(agent_pass and vision_pass and negatives.get("all_pass")),
    }
    (OUT / "agent_e2e_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "agent_tools.json").write_text(json.dumps(collector.tools, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "overall_pass": report["overall_pass"],
        "agent_pass": agent_pass,
        "tech_pass": tech.get("pass"),
        "vision_pass": vision_pass,
        "negatives": negatives.get("all_pass"),
        "tools": names,
        "edited_exists": EDITED.is_file(),
    }, indent=2), flush=True)
    if not report["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
