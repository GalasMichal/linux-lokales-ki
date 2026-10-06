#!/usr/bin/env python3
"""Context Boundary Discovery for local-quality (bench aliases only).

Multi-run Serve/Agent suites. Never retargets productive local-quality.
trust/approvalMode unchanged. Votes proceed_once only. No YOLO.

Suites:
  A tool_chain  – memory + pdf create/read/render + vision
  B compact     – large memory_load then continue tool chain (compact pressure)
  C knowledge   – knowledge_search/get + short memory note
  D supervisor  – named subagent researcher then architect (depth 1)
  E coding      – small fixture: edit + pytest

Append-only results under benchmarks/context-boundary-YYYYMMDD/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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

PROJECT = Path("/home/mike/Projects/Linux Lokales KI")
WORKSPACE = "/srv/ai/workspaces"
DATE_TAG = time.strftime("%Y%m%d")
OUT = Path(os.environ.get("CBD_OUT") or (PROJECT / "benchmarks" / f"context-boundary-{DATE_TAG}"))
FIXTURE = PROJECT / ".agent" / "tmp" / "ctx-boundary-coding-fixture"

CTX_MODELS_QUALITY = {
    32768: "bench-qwen38-27b-32k",
    40960: "bench-qwen38-27b-40k",
    49152: "bench-qwen38-27b-48k",
    57344: "bench-qwen38-27b-56k",
    65536: "bench-qwen38-27b-64k",
    73728: "bench-qwen38-27b-72k",
    81920: "bench-qwen38-27b-80k",
    90112: "bench-qwen38-27b-88k",
    98304: "bench-qwen38-27b-96k",
}
CTX_MODELS_FAST = {
    32768: "bench-qwen35-9b-32k",
    49152: "bench-qwen35-9b-48k",
    65536: "bench-qwen35-9b-64k",
    81920: "bench-qwen35-9b-80k",
    98304: "bench-qwen35-9b-96k",
}
_FAMILY = os.environ.get("CBD_FAMILY", "quality").strip().lower()
CTX_MODELS = CTX_MODELS_FAST if _FAMILY == "fast" else CTX_MODELS_QUALITY


def stop_models() -> None:
    text = subprocess.check_output(["ollama", "ps"], text=True)
    for line in text.splitlines()[1:]:
        name = line.split()[0] if line.strip() else ""
        if name:
            subprocess.run(["ollama", "stop", name], check=False)
    time.sleep(2)


def warmup_bench_model(model: str, ctx: int) -> dict:
    """Load the bench alias before the Serve prompt so the 45–50s empty abort cannot fire mid-load."""
    import urllib.error
    import urllib.request

    t0 = time.perf_counter()
    body = json.dumps(
        {
            "model": model,
            "prompt": ".",
            "stream": False,
            "keep_alive": "10m",
            "options": {"num_predict": 1, "num_ctx": ctx, "temperature": 0},
        }
    ).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    err = None
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            resp.read()
    except Exception as exc:  # noqa: BLE001 — warmup must not kill the run
        err = str(exc)
    ps = ""
    deadline = time.time() + 45
    while time.time() < deadline:
        ps = ollama_ps()
        if model in ps:
            break
        time.sleep(1)
    info = {
        "ok": model in ps and err is None,
        "error": err,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "ps": ps.strip().splitlines()[:3],
    }
    print(f"[warmup] {model} ctx={ctx} ok={info['ok']} elapsed={info['elapsed_s']}s err={err}", flush=True)
    return info


def is_empty_start(report: dict) -> bool:
    """Unambiguous empty session: ~40–80s, no tools, no votes, prompt was accepted."""
    tools = report.get("tools") or []
    elapsed = report.get("elapsed_s") or 0
    return (
        len(tools) == 0
        and (report.get("votes") or 0) == 0
        and not report.get("prompt_error")
        and 20 <= float(elapsed) <= 80
    )


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


def tool_blob(item: dict) -> str:
    return str(item.get("name") or item.get("title") or "").lower()


def completed_counts(tools: list[dict], expected: list[str]) -> dict[str, int]:
    counts = {e: 0 for e in expected}
    for item in tools:
        status = str(item.get("status") or "").lower()
        if status not in {"completed", "success", "ok"}:
            continue
        blob = tool_blob(item)
        for expect in expected:
            if expect in blob and "toolsearch" not in blob.replace("_", ""):
                counts[expect] += 1
    return counts


def classify(
    *,
    suite: str,
    expected: list[str],
    counts: dict[str, int],
    prompt_error: str | None,
    health: dict,
    assistant_tail: str,
    artifacts: dict,
) -> dict:
    reasons: list[str] = []
    categories: list[str] = []
    drift = False

    if prompt_error:
        pe = prompt_error.lower()
        if "too large" in pe or "compression_failed" in pe or "context" in pe:
            categories.append("context_failure")
            reasons.append(f"prompt_error:{prompt_error[:180]}")
        elif "429" in pe or "rate" in pe:
            categories.append("runtime_failure")
            reasons.append(f"prompt_error:{prompt_error[:180]}")
        else:
            categories.append("runtime_failure")
            reasons.append(f"prompt_error:{prompt_error[:180]}")

    missing = [e for e in expected if counts.get(e, 0) < 1]
    dups = {k: v for k, v in counts.items() if v > 1}
    if missing:
        reasons.append(f"missing:{missing}")
        categories.append("agent_drift")
        drift = True
    if dups:
        reasons.append(f"duplicate_tools:{dups}")
        categories.append("agent_drift")
        drift = True

    tail = (assistant_tail or "").lower()
    if "compressed context" in tail and missing:
        categories.append("compact_issue")
        reasons.append("compact_mentioned_with_incomplete_chain")
    if re.search(r"\b(done|fertig|success|completed)\b", tail) and missing:
        categories.append("agent_drift")
        reasons.append("success_claim_without_tools")
        drift = True

    for key, ok in artifacts.items():
        if key.endswith("_exact") or key.endswith("_alt") or key.endswith("_out"):
            continue
        if isinstance(ok, bool) and not ok:
            reasons.append(f"artifact_missing:{key}")
            categories.append("tool_runtime" if "pdf" in key or "png" in key or "test" in key or "pytest" in key else "agent_drift")

    if not categories and reasons:
        categories.append("unclassified")
    if not reasons:
        categories = ["pass"]

    # Distinct category labels
    cats = sorted(set(categories))
    state = "C_stable_candidate" if cats == ["pass"] else ("B_agent_unstable" if "agent_drift" in cats or "compact_issue" in cats else "A_technical")
    if "runtime_failure" in cats and "agent_drift" not in cats:
        state = "A_technical"

    return {
        "pass": cats == ["pass"],
        "fail_reasons": reasons,
        "categories": cats,
        "drift": drift,
        "state_class": state,
        "missing": missing,
        "duplicates": dups,
    }


def ensure_coding_fixture() -> Path:
    """SWE-bench-lite style mini repo: multi-file bug + failing tests."""
    if FIXTURE.exists():
        shutil.rmtree(FIXTURE)
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "ops.py").write_text(
        "def mul(a, b):\n    # BUG: adds instead of multiplies\n    return a + b\n",
        encoding="utf-8",
    )
    (FIXTURE / "calc.py").write_text(
        "from ops import mul\n\n"
        "def add(a, b):\n    # BUG: subtracts instead of adds\n    return a - b\n\n"
        "def area(w, h):\n    return mul(w, h)\n",
        encoding="utf-8",
    )
    (FIXTURE / "test_calc.py").write_text(
        "from calc import add, area\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n"
        "def test_area():\n    assert area(4, 5) == 20\n",
        encoding="utf-8",
    )
    (FIXTURE / "README.md").write_text(
        "Mini coding fixture (multi-file). Fix add() and mul() so pytest passes.\n",
        encoding="utf-8",
    )
    return FIXTURE


def prompt_for(suite: str, ctx: int, run_id: int, paths: dict) -> tuple[str, list[str]]:
    if suite == "tool_chain":
        expected = ["memory_load", "pdf_create", "pdf_read", "pdf_render", "pdf_vision_qa"]
        prompt = f"""Boundary discovery suite=tool_chain ctx={ctx} run={run_id}.
Use real MCP tools. Wait for permission. No YOLO. No /tmp. No essays between tools.

Order only:
1. mcp__local-tools__memory_load workspace="{PROJECT}"
2. mcp__local-tools__pdf_create output="{paths['pdf']}" title="BOUND {ctx} R{run_id}" text="Boundary probe ctx={ctx} run={run_id}."
3. mcp__local-tools__pdf_read path="{paths['pdf']}"
4. mcp__local-tools__pdf_render path="{paths['pdf']}" output="{paths['png']}" page=1
5. mcp__local-tools__pdf_vision_qa path="{paths['pdf']}"

Stop after pdf_vision_qa. Do not repeat completed tools.
"""
        return prompt, expected

    if suite == "compact":
        expected = ["memory_load", "pdf_create", "pdf_read"]
        prompt = f"""Boundary discovery suite=compact ctx={ctx} run={run_id}.
Wait for permission. No YOLO.

1. Call mcp__local-tools__memory_load with workspace="{PROJECT}" (full project memory).
2. After it returns, write ONE short sentence restating the active TASKS from memory (max 40 words).
3. Then mcp__local-tools__pdf_create output="{paths['pdf']}" title="COMPACT {ctx} R{run_id}" text="Compact continuity check ctx={ctx}."
4. Then mcp__local-tools__pdf_read path="{paths['pdf']}".
5. Stop. Do not re-call memory_load. Do not invent extra tools.
"""
        return prompt, expected

    if suite == "knowledge":
        expected = ["knowledge_search", "knowledge_get"]
        prompt = f"""Boundary discovery suite=knowledge ctx={ctx} run={run_id}.
Wait for permission. No YOLO. Short answers.

1. mcp__local-tools__knowledge_search query="compact state ledger lazy tools"
2. Take the top id from the result and call mcp__local-tools__knowledge_get with that id
3. Reply with one sentence: the entry id and whether status is validated/active.
Stop. Do not call unrelated tools.
"""
        return prompt, expected

    if suite == "supervisor":
        expected = ["agent"]
        prompt = f"""Boundary discovery suite=supervisor ctx={ctx} run={run_id}.
Wait for permission. No YOLO. maxSubagentDepth=1.

Task: Ask the researcher subagent (via agent tool, subagent_type=researcher) one short question:
"In one sentence: what is Compact State Ledger used for in this project?"
After the researcher returns, summarize in <=2 sentences. Do not spawn architect or reviewer. Do not recurse.
"""
        return prompt, expected

    if suite == "coding":
        expected = []  # judged by pytest artifact
        prompt = f"""Boundary discovery suite=coding ctx={ctx} run={run_id}.
Wait for permission. No YOLO. This is a small multi-file bugfix (SWE-bench style).

Work only in directory: {paths['fixture']}
1. Read README.md, calc.py, ops.py, test_calc.py
2. Run: python3 -m pytest -q {paths['fixture']}/test_calc.py  (expect FAIL)
3. Fix ALL bugs so both tests pass (add and area/mul)
4. Re-run pytest until green
5. Stop when tests pass. Do not touch files outside the fixture directory.
"""
        return prompt, expected

    if suite == "multi_hop":
        # Harder agentic: memory → knowledge → write note into pdf → read back
        expected = ["memory_load", "knowledge_search", "pdf_create", "pdf_read"]
        prompt = f"""Boundary discovery suite=multi_hop ctx={ctx} run={run_id}.
Wait for permission. No YOLO. No essays between tools.

Goal: prove multi-hop tool use with state continuity.
1. mcp__local-tools__memory_load workspace="{PROJECT}"
2. mcp__local-tools__knowledge_search query="compact state ledger"
3. From knowledge result, pick one id. Create pdf with mcp__local-tools__pdf_create
   output="{paths['pdf']}" title="MHOP {ctx} R{run_id}"
   text="multi_hop ctx={ctx} knowledge_id=<THE_ID> ledger_ok=yes"
4. mcp__local-tools__pdf_read path="{paths['pdf']}"
5. Final reply one line: knowledge_id=<id>
Do not repeat completed tools. Do not call vision.
"""
        return prompt, expected

    raise SystemExit(f"unknown suite {suite}")


def run_once(suite: str, ctx: int, run_id: int) -> dict:
    model = CTX_MODELS[ctx]
    model_id = f"{model}(openai)"
    stamp = time.strftime("%H%M%S")
    paths = {
        "pdf": str(PROJECT / ".agent" / "tmp" / f"bound-{suite}-{ctx}-r{run_id}-{stamp}.pdf"),
        "png": str(PROJECT / ".agent" / "tmp" / f"bound-{suite}-{ctx}-r{run_id}-{stamp}.png"),
        "fixture": str(FIXTURE),
    }
    if suite == "coding":
        ensure_coding_fixture()
    for key in ("pdf", "png"):
        p = Path(paths[key])
        if p.is_file():
            p.unlink()
        p.parent.mkdir(parents=True, exist_ok=True)

    prompt, expected = prompt_for(suite, ctx, run_id, paths)
    stop_models()
    warmup = warmup_bench_model(model, ctx)
    before = {"nvidia": nvidia(), "mem": meminfo(), "ps": ollama_ps(), "warmup": warmup}
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
            print(f"[session-fresh] {exc}", flush=True)

    print(f"\n=== {suite} ctx={ctx} run={run_id} model={model_id} session={sid} ===", flush=True)
    model_switch = http_json("POST", f"/session/{sid}/model", {"modelId": model_id})
    print(f"[model] {model_switch}", flush=True)
    try:
        http_json(
            "POST",
            f"/session/{sid}/config-option",
            {"configId": "reasoning_effort", "value": "none", "persist": False},
        )
    except Exception:
        pass

    stop = threading.Event()
    collector = EventCollector(sid)
    thread = threading.Thread(target=sse_loop, args=(sid, collector, stop), daemon=True)
    thread.start()
    time.sleep(0.8)

    prompt_error = None
    try:
        http_json(
            "POST",
            f"/session/{sid}/prompt",
            {"prompt": [{"type": "text", "text": prompt}]},
            timeout=30,
        )
    except Exception as exc:
        prompt_error = str(exc)
        print(f"[prompt] FAIL {exc}", flush=True)

    final_health = wait_for_turn(sid, collector, t0, since)
    stop.set()
    time.sleep(0.5)

    tools = []
    for item in collector.tools:
        tools.append(
            {
                "id": item.get("id"),
                "name": item.get("name") or item.get("title"),
                "status": item.get("status"),
            }
        )
    counts = completed_counts(tools, expected) if expected else {}
    assistant_tail = "".join(getattr(collector, "texts", []) or [])[-1500:]

    artifacts = {}
    if suite in {"tool_chain", "compact", "multi_hop"}:
        pdf_p = Path(paths["pdf"])
        artifacts["pdf"] = pdf_p.is_file()
        if suite == "tool_chain":
            png_p = Path(paths["png"])
            # Agent sometimes writes stem-p1.png / stem.p1.png — still a successful render.
            alt = list(pdf_p.parent.glob(pdf_p.stem + "*.png")) if pdf_p.parent.is_dir() else []
            artifacts["png"] = png_p.is_file() or any(p.is_file() for p in alt)
            artifacts["png_exact"] = png_p.is_file()
            artifacts["png_alt"] = [str(p) for p in alt[:5]]
    if suite == "coding":
        # validate with pytest ourselves
        proc = subprocess.run(
            ["python3", "-m", "pytest", "-q", str(FIXTURE / "test_calc.py")],
            cwd=str(FIXTURE),
            capture_output=True,
            text=True,
            timeout=60,
        )
        artifacts["pytest_pass"] = proc.returncode == 0
        artifacts["pytest_out"] = (proc.stdout + proc.stderr)[-500:]
        calc_src = (FIXTURE / "calc.py").read_text(encoding="utf-8")
        ops_src = (FIXTURE / "ops.py").read_text(encoding="utf-8") if (FIXTURE / "ops.py").is_file() else ""
        artifacts["add_fixed"] = "a - b" not in calc_src and ("a + b" in calc_src or "a+b" in calc_src)
        artifacts["mul_fixed"] = (
            ("a * b" in ops_src or "a*b" in ops_src) and "a + b" not in ops_src and "a+b" not in ops_src
            if ops_src
            else True
        )

    after = {"nvidia": nvidia(), "mem": meminfo(), "ps": ollama_ps()}
    verdict = classify(
        suite=suite,
        expected=expected,
        counts=counts,
        prompt_error=prompt_error,
        health=final_health or {},
        assistant_tail=assistant_tail,
        artifacts={k: v for k, v in artifacts.items() if not isinstance(v, str)},
    )
    # coding: pass if pytest + fixes even without expected tool names
    if suite == "coding":
        if artifacts.get("pytest_pass") and artifacts.get("add_fixed") and artifacts.get("mul_fixed"):
            verdict = {
                "pass": True,
                "fail_reasons": [],
                "categories": ["pass"],
                "drift": False,
                "state_class": "C_stable_candidate",
                "missing": [],
                "duplicates": {},
            }
        else:
            verdict["pass"] = False
            if "agent_drift" not in verdict["categories"]:
                verdict["categories"] = sorted(set(verdict["categories"] + ["agent_drift"]))
            verdict["state_class"] = "B_agent_unstable"
            verdict["drift"] = True
            if not artifacts.get("pytest_pass"):
                verdict["fail_reasons"].append("pytest_failed")
            if not artifacts.get("add_fixed"):
                verdict["fail_reasons"].append("calc_not_fixed")
            if not artifacts.get("mul_fixed"):
                verdict["fail_reasons"].append("mul_not_fixed")

    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "suite": suite,
        "num_ctx": ctx,
        "model": model,
        "run_id": run_id,
        "sessionId": sid,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "pass": verdict["pass"],
        "drift": verdict["drift"],
        "state_class": verdict["state_class"],
        "categories": verdict["categories"],
        "fail_reasons": verdict["fail_reasons"],
        "completed_counts": counts,
        "tools": tools,
        "votes": len(collector.votes),
        "artifacts": artifacts,
        "before": before,
        "after": after,
        "prompt_error": prompt_error,
        "mcp_status": mcp.get("status") if isinstance(mcp, dict) else None,
        "runtime": {
            "ollama": subprocess.check_output(["ollama", "--version"], text=True).strip(),
        },
        "productive_local_quality_untouched": True,
        "warmup": warmup,
        "attempt": 1,
        "retry_of": None,
        "empty_start": False,
        "error_class": None,
    }
    try:
        http_json("DELETE", f"/session/{sid}")
    except Exception:
        pass
    stop_models()
    return report


def append_result(report: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "results.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False) + "\n")
    suite = report["suite"]
    ctx = report["num_ctx"]
    rid = report["run_id"]
    attempt = int(report.get("attempt") or 1)
    blob = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    (OUT / f"{suite}-ctx{ctx}-r{rid}-a{attempt}.json").write_text(blob)
    # Latest attempt is the canonical name; attempt-1 stays in *-a1.json.
    (OUT / f"{suite}-ctx{ctx}-r{rid}.json").write_text(blob)
    return path


def tag_error_class(report: dict) -> dict:
    if is_empty_start(report):
        report["empty_start"] = True
        report["error_class"] = "harness_session"
        cats = sorted(set((report.get("categories") or []) + ["session_empty_start"]))
        report["categories"] = cats
        report["state_class"] = "A_technical"
        report["drift"] = False
        reasons = list(report.get("fail_reasons") or [])
        if "empty_session_start" not in reasons:
            reasons.append("empty_session_start")
        report["fail_reasons"] = reasons
        report["pass"] = False
        return report
    report["empty_start"] = False
    if report.get("pass"):
        report["error_class"] = "pass"
    elif "runtime_failure" in (report.get("categories") or []):
        report["error_class"] = "infrastructure"
    else:
        report["error_class"] = "agent"
    return report


def summarize() -> dict:
    path = OUT / "results.jsonl"
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    by: dict[str, dict] = {}
    for r in rows:
        key = f"{r['suite']}:{r['num_ctx']}"
        slot = by.setdefault(
            key,
            {
                "suite": r["suite"],
                "num_ctx": r["num_ctx"],
                "runs": 0,
                "pass": 0,
                "fail": 0,
                "drift": 0,
                "categories": {},
                "fail_reasons": [],
            },
        )
        slot["runs"] += 1
        if r.get("pass"):
            slot["pass"] += 1
        else:
            slot["fail"] += 1
        if r.get("drift"):
            slot["drift"] += 1
        for c in r.get("categories") or []:
            slot["categories"][c] = slot["categories"].get(c, 0) + 1
        if r.get("fail_reasons"):
            slot["fail_reasons"].append(r["fail_reasons"])
    summary = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "out": str(OUT),
        "total_runs": len(rows),
        "by_suite_ctx": list(by.values()),
        "note": "Benchmark-only. Productive local-quality may be 16384 or 65536; check ollama show.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return summary


def gate_productive() -> None:
    show = subprocess.check_output(["ollama", "show", "local-quality", "--modelfile"], text=True)
    # After 64K cutover productive is 65536; allow historical 16384 for older harness use.
    if "num_ctx 65536" not in show and "num_ctx 16384" not in show:
        raise SystemExit("ABBRUCH: local-quality num_ctx ist weder 65536 noch 16384")
    health = http_json("GET", "/health")
    if health.get("status") != "ok":
        raise SystemExit(f"ABBRUCH: qwen serve health={health}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--suite",
        required=True,
        choices=["tool_chain", "compact", "knowledge", "supervisor", "coding", "multi_hop"],
    )
    ap.add_argument("--ctx", required=True, help="comma list e.g. 32768,40960,49152")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--start-run", type=int, default=1)
    args = ap.parse_args()
    ctxs = [int(x.strip()) for x in args.ctx.split(",") if x.strip()]
    for c in ctxs:
        if c not in CTX_MODELS:
            raise SystemExit(f"unknown ctx {c}; known={sorted(CTX_MODELS)}")

    gate_productive()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"OUT={OUT} suite={args.suite} ctxs={ctxs} runs={args.runs}", flush=True)

    for ctx in ctxs:
        for run_id in range(args.start_run, args.start_run + args.runs):
            try:
                report = run_once(args.suite, ctx, run_id)
            except Exception as exc:
                report = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "suite": args.suite,
                    "num_ctx": ctx,
                    "model": CTX_MODELS[ctx],
                    "run_id": run_id,
                    "pass": False,
                    "drift": False,
                    "state_class": "A_technical",
                    "categories": ["runtime_failure"],
                    "fail_reasons": [f"exception:{exc}"],
                    "productive_local_quality_untouched": True,
                    "tools": [],
                    "votes": 0,
                    "elapsed_s": 0,
                    "prompt_error": None,
                }
                print(f"[exception] {exc}", flush=True)
            report["attempt"] = 1
            report["retry_of"] = None
            tag_error_class(report)
            append_result(report)
            print(
                json.dumps(
                    {
                        "suite": report["suite"],
                        "ctx": report["num_ctx"],
                        "run": report["run_id"],
                        "attempt": 1,
                        "empty_start": report.get("empty_start"),
                        "error_class": report.get("error_class"),
                        "pass": report["pass"],
                        "drift": report.get("drift"),
                        "state": report.get("state_class"),
                        "reasons": report.get("fail_reasons"),
                        "elapsed_s": report.get("elapsed_s"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if report.get("empty_start"):
                print(f"[retry] empty start {args.suite} ctx={ctx} r={run_id} — one retry", flush=True)
                try:
                    retry = run_once(args.suite, ctx, run_id)
                except Exception as exc:
                    retry = {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        "suite": args.suite,
                        "num_ctx": ctx,
                        "model": CTX_MODELS[ctx],
                        "run_id": run_id,
                        "pass": False,
                        "drift": False,
                        "state_class": "A_technical",
                        "categories": ["runtime_failure"],
                        "fail_reasons": [f"exception:{exc}"],
                        "productive_local_quality_untouched": True,
                        "tools": [],
                        "votes": 0,
                        "elapsed_s": 0,
                        "prompt_error": None,
                    }
                    print(f"[exception-retry] {exc}", flush=True)
                retry["attempt"] = 2
                retry["retry_of"] = f"{args.suite}-ctx{ctx}-r{run_id}-a1"
                tag_error_class(retry)
                append_result(retry)
                print(
                    json.dumps(
                        {
                            "suite": retry["suite"],
                            "ctx": retry["num_ctx"],
                            "run": retry["run_id"],
                            "attempt": 2,
                            "retry_of": retry["retry_of"],
                            "empty_start": retry.get("empty_start"),
                            "error_class": retry.get("error_class"),
                            "pass": retry["pass"],
                            "drift": retry.get("drift"),
                            "state": retry.get("state_class"),
                            "reasons": retry.get("fail_reasons"),
                            "elapsed_s": retry.get("elapsed_s"),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            gate_productive()

    summary = summarize()
    print("SUMMARY", json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
