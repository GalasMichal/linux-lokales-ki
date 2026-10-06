#!/usr/bin/env python3
"""QUALITY context ladder via qwen serve until it breaks.

Additive bench models only. Does not retarget local-quality or local-fast.
Votes proceed_once only. trust stays false. No YOLO.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from quality_cutover_e2e import (  # noqa: E402
    EventCollector,
    http_json,
    nvidia,
    ollama_ps,
    pick_allow,
    sse_loop,
    wait_for_turn,
)

PROJECT = "/home/mike/Projects/Linux Lokales KI"
WORKSPACE = "/srv/ai/workspaces"
OUT = Path(PROJECT) / "benchmarks" / "quality-context-ladder-20261002"
LEVELS = [
    ("bench-qwen38-27b-16k", 16384),
    ("bench-qwen38-27b-24k", 24576),
    ("bench-qwen38-27b-32k", 32768),
    ("bench-qwen38-27b-40k", 40960),
    ("bench-qwen38-27b-48k", 49152),
]
EXPECTED = ["memory_load", "pdf_create", "pdf_read", "pdf_render", "pdf_vision_qa"]


def stop_models() -> None:
    text = subprocess.check_output(["ollama", "ps"], text=True)
    for line in text.splitlines()[1:]:
        name = line.split()[0] if line.strip() else ""
        if name:
            subprocess.run(["ollama", "stop", name], check=False)
    time.sleep(2)


def meminfo() -> dict:
    vals = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, rest = line.split(":", 1)
        vals[k] = int(rest.strip().split()[0])
    return {
        "mem_available_mib": vals["MemAvailable"] // 1024,
        "swap_used_mib": (vals["SwapTotal"] - vals["SwapFree"]) // 1024,
    }


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


def compact_tools(collector: EventCollector) -> list[dict]:
    seen = []
    out = []
    for item in collector.tools:
        key = (item.get("id"), item.get("status"))
        if key in seen:
            continue
        seen.append(key)
        out.append(
            {
                "id": item.get("id"),
                "name": item.get("name") or item.get("title"),
                "status": item.get("status"),
                "input": item.get("rawInput"),
            }
        )
    return out


def completed_names(tools: list[dict]) -> list[str]:
    names = []
    for item in tools:
        if str(item.get("status") or "").lower() not in {"completed", "success", "ok"}:
            # still count name hits for diagnostics; prefer completed below
            pass
        blob = str(item.get("name") or "").lower()
        for expect in EXPECTED:
            if expect in blob and "toolsearch" not in blob.replace("_", ""):
                names.append(expect)
    return names


def count_completed(tools: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {e: 0 for e in EXPECTED}
    for item in tools:
        status = str(item.get("status") or "").lower()
        if status not in {"completed", "success", "ok"}:
            continue
        blob = str(item.get("name") or "").lower()
        for expect in EXPECTED:
            if expect in blob and "toolsearch" not in blob.replace("_", ""):
                counts[expect] += 1
    return counts


def prompt_for(ctx: int, pdf: str, png: str) -> str:
    return f"""You are in one continuous session at context {ctx}. Use real MCP tools. Wait for permission. No YOLO. No /tmp.

Do these steps in order:
1. mcp__local-tools__memory_load workspace="{PROJECT}"
2. mcp__local-tools__pdf_create output="{pdf}" title="QUALITY CTX {ctx}" text="Context ladder probe at {ctx} tokens. FAST stays local-fast. No productive cutover."
3. mcp__local-tools__pdf_read path="{pdf}"
4. mcp__local-tools__pdf_render path="{pdf}" output="{png}" page=1
5. mcp__local-tools__pdf_vision_qa path="{pdf}"

After each tool returns, call the next tool. Do not write long essays between tools. Stop after pdf_vision_qa returns.
"""


def run_level(model: str, ctx: int) -> dict:
    model_id = f"{model}(openai)"
    pdf = f"{PROJECT}/.agent/tmp/quality-ctx-ladder-{ctx}.pdf"
    png = f"{PROJECT}/.agent/tmp/quality-ctx-ladder-{ctx}.png"
    for stale in (pdf, png):
        path = Path(stale)
        if path.is_file():
            path.unlink()
    Path(pdf).parent.mkdir(parents=True, exist_ok=True)

    stop_models()
    before = {"nvidia": nvidia(), "mem": meminfo(), "ps": ollama_ps()}
    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    mcp = http_json("GET", "/workspace/mcp")
    created = http_json("POST", "/session", {"cwd": WORKSPACE})
    sid = created["sessionId"]
    if created.get("attached"):
        try:
            http_json("DELETE", f"/session/{sid}")
            created = http_json("POST", "/session", {"cwd": WORKSPACE})
            sid = created["sessionId"]
        except Exception as exc:
            print(f"[session-fresh] skip {exc}", flush=True)
    print(f"\n=== LEVEL {ctx} model={model_id} session={sid} ===", flush=True)
    model_switch = http_json("POST", f"/session/{sid}/model", {"modelId": model_id})
    print(f"[model] {model_switch}", flush=True)
    try:
        http_json(
            "POST",
            f"/session/{sid}/config-option",
            {"configId": "reasoning_effort", "value": "none", "persist": False},
        )
    except Exception as exc:
        print(f"[effort] skip {exc}", flush=True)

    stop = threading.Event()
    collector = EventCollector(sid)
    threading.Thread(target=sse_loop, args=(sid, collector, stop), daemon=True).start()
    time.sleep(0.8)

    def poll_votes() -> None:
        while not stop.is_set():
            vote_pending(sid, collector)
            time.sleep(0.6)

    threading.Thread(target=poll_votes, daemon=True).start()
    prompt_error = None
    try:
        http_json(
            "POST",
            f"/session/{sid}/prompt",
            {"prompt": [{"type": "text", "text": prompt_for(ctx, pdf, png)}]},
            timeout=30,
        )
    except Exception as exc:
        prompt_error = str(exc)
        print(f"[prompt] FAIL {exc}", flush=True)

    final_health = wait_for_turn(sid, collector, t0, since)
    stop.set()
    try:
        http_json("DELETE", f"/session/{sid}")
    except Exception:
        pass

    tools = compact_tools(collector)
    counts = count_completed(tools)
    hit = {k for k, v in counts.items() if v >= 1}
    dups = {k: v for k, v in counts.items() if v > 1}
    yolo = any("yolo" in str(v.get("optionId") or "").lower() for v in collector.votes)
    always = any("always" in str(v.get("optionId") or "").lower() for v in collector.votes)
    ok_votes = [v for v in collector.votes if v.get("ok")]
    after = {"nvidia": nvidia(), "mem": meminfo(), "ps": ollama_ps()}
    reasons: list[str] = []
    if prompt_error:
        reasons.append(f"prompt_error:{prompt_error[:120]}")
    for expect in EXPECTED:
        if expect not in hit:
            reasons.append(f"missing:{expect}")
    if dups:
        reasons.append(f"duplicate_tools:{dups}")
    if not Path(pdf).is_file():
        reasons.append("pdf_missing")
    if not Path(png).is_file():
        reasons.append("png_missing")
    if yolo:
        reasons.append("yolo_vote")
    if always:
        reasons.append("always_vote")
    if not ok_votes:
        reasons.append("no_votes")
    elif any(v.get("optionId") != "proceed_once" for v in ok_votes):
        reasons.append("non_proceed_once")
    if after["mem"]["mem_available_mib"] < 1024:
        reasons.append("ram_low")
    if after["mem"]["swap_used_mib"] >= 16000 and after["mem"]["mem_available_mib"] < 2048:
        reasons.append("swap_pressure")

    report = {
        "model": model,
        "model_id": model_id,
        "num_ctx": ctx,
        "sessionId": sid,
        "model_switch": model_switch,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "prompt_error": prompt_error,
        "votes": collector.votes,
        "tools": tools,
        "completed_counts": counts,
        "expected_hit": sorted(hit),
        "missing": [x for x in EXPECTED if x not in hit],
        "duplicates": dups,
        "thoughts": collector.thoughts,
        "assistant_text_tail": "".join(collector.texts)[-1000:],
        "pdf_exists": Path(pdf).is_file(),
        "png_exists": Path(png).is_file(),
        "yolo": yolo,
        "always_allow": always,
        "mcp_status": {
            "initialized": mcp.get("initialized"),
            "servers": [
                {"name": s.get("name"), "status": s.get("status"), "trust": s.get("trust")}
                for s in (mcp.get("servers") or mcp.get("mcpServers") or [])
                if isinstance(s, dict)
            ],
        },
        "health": final_health,
        "before": before,
        "after": after,
        "fail_reasons": reasons,
        "pass": not reasons,
    }
    (OUT / f"level-{ctx}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)[:2_000_000] + "\n")
    print(
        json.dumps(
            {
                "ctx": ctx,
                "pass": report["pass"],
                "elapsed_s": report["elapsed_s"],
                "hit": report["expected_hit"],
                "missing": report["missing"],
                "duplicates": dups,
                "fail_reasons": reasons,
                "vram_after": after["nvidia"],
                "mem_after": after["mem"],
                "ps": after["ps"].splitlines()[:3],
            },
            indent=2,
            ensure_ascii=False,
        ),
        flush=True,
    )
    return report


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    from_ctx = 0
    if len(sys.argv) > 1 and sys.argv[1].startswith("--from-ctx="):
        from_ctx = int(sys.argv[1].split("=", 1)[1])
    # health gate
    health = http_json("GET", "/health")
    if health.get("status") != "ok":
        raise SystemExit(f"ABBRUCH: qwen serve health={health}")
    # productive alias must stay 16k
    show = subprocess.check_output(["ollama", "show", "local-quality", "--modelfile"], text=True)
    if "num_ctx 16384" not in show:
        raise SystemExit("ABBRUCH: local-quality ist nicht mehr 16384")

    summary: dict = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "levels": [],
        "highest_pass_ctx": None,
        "first_fail_ctx": None,
        "productive_local_quality_ctx": 16384,
        "recommendation": None,
        "from_ctx": from_ctx or None,
    }
    # Seed from prior level JSON when resuming mid-ladder.
    for model, ctx in LEVELS:
        if from_ctx and ctx >= from_ctx:
            break
        prev = OUT / f"level-{ctx}.json"
        if not prev.is_file():
            continue
        prev_data = json.loads(prev.read_text())
        seed = {
            "model": model,
            "num_ctx": ctx,
            "pass": bool(prev_data.get("pass")),
            "elapsed_s": prev_data.get("elapsed_s"),
            "fail_reasons": prev_data.get("fail_reasons") or [],
            "completed_counts": prev_data.get("completed_counts"),
            "vram_after_mib": (prev_data.get("after") or {}).get("nvidia", {}).get("vram_used_mib")
            if isinstance(prev_data.get("after"), dict)
            else (prev_data.get("vram_after") or {}).get("vram_used_mib"),
            "swap_after_mib": (prev_data.get("after") or {}).get("mem", {}).get("swap_used_mib")
            if isinstance(prev_data.get("after"), dict)
            else (prev_data.get("mem_after") or {}).get("swap_used_mib"),
            "seeded": True,
        }
        summary["levels"].append(seed)
        if seed["pass"]:
            summary["highest_pass_ctx"] = ctx
        elif summary["first_fail_ctx"] is None:
            summary["first_fail_ctx"] = ctx
        print(f"SEED level {ctx} pass={seed['pass']}", flush=True)

    try:
        for model, ctx in LEVELS:
            if from_ctx and ctx < from_ctx:
                continue
            level = run_level(model, ctx)
            summary["levels"].append(
                {
                    "model": model,
                    "num_ctx": ctx,
                    "pass": level["pass"],
                    "elapsed_s": level["elapsed_s"],
                    "fail_reasons": level["fail_reasons"],
                    "completed_counts": level["completed_counts"],
                    "vram_after_mib": level["after"]["nvidia"].get("vram_used_mib"),
                    "swap_after_mib": level["after"]["mem"]["swap_used_mib"],
                }
            )
            if level["pass"]:
                summary["highest_pass_ctx"] = ctx
            else:
                if summary["first_fail_ctx"] is None:
                    summary["first_fail_ctx"] = ctx
                # Continue ascending: lower fails (e.g. 16k overflow) do not prove
                # higher contexts are also too high. Stop only on hard resource abort.
                hard = any(
                    r.startswith(p)
                    for r in level["fail_reasons"]
                    for p in ("ram_low", "swap_pressure", "prompt_error:ABBRUCH")
                )
                print(
                    f"LEVEL FAIL at {ctx}; continue={'no' if hard else 'yes'} reasons={level['fail_reasons']}",
                    flush=True,
                )
                if hard:
                    print(f"STOP ascending: hard resource fail at {ctx}", flush=True)
                    break
    finally:
        stop_models()
        # leave qwen serve running; caller may stop

    high = summary["highest_pass_ctx"]
    fail = summary["first_fail_ctx"]
    if high is None and fail is not None:
        summary["recommendation"] = (
            f"Keine Serve-E2E-Stufe PASS. Erster Fail {fail}. Kein Cutover. "
            "local-quality bleibt 16384."
        )
    elif high is not None and fail is None:
        summary["recommendation"] = (
            f"Alle getesteten Stufen bis {high} PASS. Obere Grenze in dieser Leiter nicht gefunden. "
            "Produktives local-quality bleibt 16384."
        )
    elif high is not None and fail is not None and fail < high:
        summary["recommendation"] = (
            f"Serve-E2E: {fail} zu eng (Fail), höhere Stufe bis {high} PASS. "
            f"Für Cutover höchstens {high} erwägen — nur mit Freigabe. local-quality bleibt 16384."
        )
    else:
        summary["recommendation"] = (
            f"Serve-E2E PASS bis {high}; Fail bei/nach {fail}. "
            f"Cutover höchstens {high} — nur mit Freigabe. local-quality bleibt 16384."
        )
    show_after = subprocess.check_output(["ollama", "show", "local-quality", "--modelfile"], text=True)
    summary["local_quality_still_16384"] = "num_ctx 16384" in show_after
    summary["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print("SUMMARY", json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
