#!/usr/bin/env python3
"""80K-only realistic coding bench (SWE-lite, no Docker, no 64K rerun).

Official method (https://www.swebench.com/SWE-bench/):
resolved = FAIL_TO_PASS pass AND PASS_TO_PASS still pass.
Aider polyglot (https://aider.chat/docs/leaderboards/): edit + run tests.
No YOLO. Isolated :4171 + fail-closed pytest/unittest voter.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path("/home/mike/Projects/Linux Lokales KI")
sys.path.insert(0, str(REPO / "benchmarks"))

OUT = Path(os.environ.get("CBD_OUT") or (REPO / "benchmarks" / "realistic-80k-20261004"))
TASKS = REPO / "benchmarks" / "realistic_80k_tasks"
# Isolated `qwen serve --workspace /srv/ai/workspaces` rejects other session cwd.
SESSION_CWD = "/srv/ai/workspaces"
RUN_ROOT = Path(
    os.environ.get("R80_RUN_ROOT", "/srv/ai/workspaces/realistic-80k-20261004/runs")
)
CTX = 81920
MODEL = "bench-qwen38-27b-80k"
MODEL_ID = f"{MODEL}(openai)"
RUNS = 3

os.environ.setdefault("CBD_OUT", str(OUT))
os.environ.setdefault("CBD_SERVE", "http://127.0.0.1:4171")

import night_scoped_shell as scoped  # noqa: E402
import quality_cutover_e2e as e2e  # noqa: E402
from context_boundary_discovery import (  # noqa: E402
    is_empty_start,
    meminfo,
    stop_models,
    warmup_bench_model,
)

e2e.BASE = os.environ["CBD_SERVE"]
scoped.install_voter(e2e.BASE)


def vote_pending(session_id: str, collector) -> None:  # type: ignore[no-untyped-def]
    try:
        status = e2e.http_json("GET", f"/session/{session_id}/status")
    except Exception:
        return
    for item in status.get("pendingInteractions") or []:
        request_id = item.get("requestId") or item.get("id")
        if not request_id:
            continue
        vote = scoped.cast_vote(e2e.BASE, session_id, item)
        collector.votes.append(vote)


# Fail-closed shell voter instead of CBD proceed_once.
import context_boundary_discovery as cbd  # noqa: E402

cbd.vote_pending = vote_pending


def list_tasks() -> list[Path]:
    return sorted(p for p in TASKS.iterdir() if (p / "task.json").is_file())


def protocol_prompt_suffix() -> str:
    pf = os.environ.get("R80_PROTOCOL_FILE")
    if not pf:
        return ""
    return "\n\n" + Path(pf).read_text(encoding="utf-8")


def reset_workspace(task_dir: Path, task_id: str, run_id: int) -> Path:
    dest = RUN_ROOT / f"{task_id}-r{run_id}"
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(task_dir / "workspace", dest)
    return dest


def run_pytest(paths: list[Path], cwd: Path) -> dict:
    cmd = ["python3", "-m", "pytest", "-q", *[str(p) for p in paths]]
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=60)
    return {
        "pass": proc.returncode == 0,
        "code": proc.returncode,
        "out": (proc.stdout + proc.stderr)[-800:],
    }


def score_workspace(task_dir: Path, workspace: Path) -> dict:
    hidden = task_dir / "hidden"
    vis = run_pytest([workspace / "test_visible.py"], workspace)
    p2p = run_pytest([hidden / "test_pass_to_pass.py"], workspace)
    musts = run_pytest([hidden / "test_musts.py"], workspace)
    resolved = bool(vis["pass"] and p2p["pass"] and musts["pass"])
    return {
        "fail_to_pass": vis,
        "pass_to_pass": p2p,
        "musts": musts,
        "resolved": resolved,
    }


def _tool_names(tools: list) -> list[str]:
    return [str(t.get("name") or t.get("title") or "") for t in tools]


def turn_aborted(report: dict, tools: list) -> bool:
    """True when the agent turn died before a meaningful code fix (Qwen turn_error / loop guard)."""
    if report.get("turn_error"):
        return True
    names = _tool_names(tools)
    lowered = " ".join(names).lower()
    if report.get("turn_aborted"):
        return True
    edited = any(tok in lowered for tok in ("edit:", "writefile:", "writing to"))
    if edited:
        return False
    failed = sum(1 for t in tools if str(t.get("status")).lower() == "failed")
    failed_reads = sum(
        1
        for t in tools
        if str(t.get("status")).lower() == "failed"
        and any(tok in str(t.get("name") or "").lower() for tok in ("read", "toolcall"))
    )
    if failed >= 2 and failed_reads >= 1 and not score_visible_fixed(report):
        return True
    return False


def score_visible_fixed(report: dict) -> bool:
    return bool(report.get("fail_to_pass"))


def classify_error(report: dict, score: dict) -> str:
    tools = report.get("tools") or []
    if is_empty_start(report):
        return "harness_session"
    if report.get("prompt_error"):
        return "harness"
    if report.get("perm_blocked"):
        return "permission"
    if score["resolved"]:
        return "pass"
    if turn_aborted(report, tools):
        return "tool_runtime"
    if not score["fail_to_pass"]["pass"]:
        return "agent"
    if not score["musts"]["pass"]:
        return "must_loss"
    if not score["pass_to_pass"]["pass"]:
        return "regression"
    return "agent"


def run_once(task_dir: Path, run_id: int, attempt: int = 1, retry_of: int | None = None) -> dict:
    meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    task_id = meta["id"]
    workspace = reset_workspace(task_dir, task_id, run_id)
    issue = (task_dir / "issue.md").read_text(encoding="utf-8").replace("{workspace}", str(workspace))
    prompt = (
        f"Realistic coding bench task={task_id} ctx={CTX} run={run_id}.\n"
        f"You are a coding agent. Solve the issue below.\n"
        f"Run the visible pytest command yourself, fix failures, then re-run pytest.\n"
        f"Do not ask the user questions.\n\n{issue}"
        f"{protocol_prompt_suffix()}"
    )
    scoped.assert_user_settings_untouched()
    stop_models()
    warmup = warmup_bench_model(MODEL, CTX)
    before = {"mem": meminfo(), "warmup": warmup}
    t0 = time.perf_counter()
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    created = e2e.http_json("POST", "/session", {"cwd": SESSION_CWD})
    sid = created["sessionId"]
    if created.get("attached"):
        try:
            e2e.http_json("DELETE", f"/session/{sid}")
            created = e2e.http_json("POST", "/session", {"cwd": SESSION_CWD})
            sid = created["sessionId"]
        except Exception as exc:
            print(f"[session-fresh] {exc}", flush=True)
    print(f"\n=== {task_id} ctx={CTX} run={run_id} a{attempt} session={sid} ===", flush=True)
    e2e.http_json("POST", f"/session/{sid}/model", {"modelId": MODEL_ID})
    try:
        e2e.http_json(
            "POST",
            f"/session/{sid}/config-option",
            {"configId": "reasoning_effort", "value": "none", "persist": False},
        )
    except Exception:
        pass
    stop = threading.Event()
    collector = e2e.EventCollector(sid)
    thread = threading.Thread(target=e2e.sse_loop, args=(sid, collector, stop), daemon=True)
    thread.start()
    time.sleep(0.8)
    prompt_error = None
    try:
        e2e.http_json(
            "POST",
            f"/session/{sid}/prompt",
            {"prompt": [{"type": "text", "text": prompt}]},
            timeout=30,
        )
    except Exception as exc:
        prompt_error = str(exc)
        print(f"[prompt] FAIL {exc}", flush=True)
    final_health = e2e.wait_for_turn(sid, collector, t0, since)
    stop.set()
    time.sleep(0.4)
    tools = [{"name": t.get("name") or t.get("title"), "status": t.get("status")} for t in collector.tools]
    score = score_workspace(task_dir, workspace)
    tools_failed = sum(1 for t in tools if str(t.get("status")).lower() == "failed")
    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "task": task_id,
        "title": meta.get("title"),
        "core": bool(meta.get("core")),
        "num_ctx": CTX,
        "model": MODEL,
        "bench_variant": os.environ.get("R80_BENCH_VARIANT", "realistic_80k_default"),
        "protocol_file": os.environ.get("R80_PROTOCOL_FILE"),
        "run_id": run_id,
        "attempt": attempt,
        "retry_of": retry_of,
        "sessionId": sid,
        "workspace": str(workspace),
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "pass": score["resolved"],
        "resolved": score["resolved"],
        "fail_to_pass": score["fail_to_pass"]["pass"],
        "pass_to_pass": score["pass_to_pass"]["pass"],
        "musts_ok": score["musts"]["pass"],
        "score": score,
        "tools": tools,
        "tools_failed": tools_failed,
        "votes": len(collector.votes),
        "vote_log_tail": [],
        "prompt_error": prompt_error,
        "health": final_health or {},
        "before": before,
        "empty_start": False,
        "error_class": None,
        "perm_blocked": False,
        "productive_local_quality_untouched": True,
    }
    report["empty_start"] = is_empty_start(report)
    report["turn_aborted"] = turn_aborted(report, tools)
    report["error_class"] = classify_error(report, score)
    if report["empty_start"]:
        report["pass"] = False
        report["resolved"] = False
    try:
        e2e.http_json("DELETE", f"/session/{sid}")
    except Exception:
        pass
    stop_models()
    scoped.assert_user_settings_untouched()
    return report


def append_result(report: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "results.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False) + "\n")
    name = f"{report['task']}-r{report['run_id']}-a{report['attempt']}.json"
    (OUT / name).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (OUT / f"{report['task']}-r{report['run_id']}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )


def write_status() -> None:
    rows = []
    p = OUT / "results.jsonl"
    if p.is_file():
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    latest = {}
    for r in rows:
        key = (r["task"], r["run_id"])
        prev = latest.get(key)
        if prev is None or int(r.get("attempt") or 1) >= int(prev.get("attempt") or 1):
            latest[key] = r
    valid = [r for r in latest.values() if not r.get("empty_start")]
    by: dict[str, dict] = {}
    for r in valid:
        slot = by.setdefault(r["task"], {"n": 0, "pass": 0, "must_loss": 0, "agent": 0})
        slot["n"] += 1
        if r.get("resolved"):
            slot["pass"] += 1
        if r.get("error_class") == "must_loss":
            slot["must_loss"] += 1
        if r.get("error_class") == "agent":
            slot["agent"] += 1
    lines = [
        "# Realistic 80K coding — STATUS",
        "",
        f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}. attempts={len(rows)} valid={len(valid)}.",
        "Productive local-quality stays **65536** until a cutover decision.",
        "",
        "| Task | resolved | must_loss | agent |",
        "|---|---|---|---|",
    ]
    for task in ("order_service", "config_merge", "ledger_repair"):
        v = by.get(task)
        if not v:
            lines.append(f"| {task} | — | — | — |")
        else:
            lines.append(f"| {task} | {v['pass']}/{v['n']} | {v['must_loss']} | {v['agent']} |")
    if rows:
        last = rows[-1]
        lines.append("")
        lines.append(
            f"Last: {last.get('task')} r={last.get('run_id')} a={last.get('attempt')} "
            f"class={last.get('error_class')} resolved={last.get('resolved')}"
        )
    (OUT / "STATUS.md").write_text("\n".join(lines) + "\n")


def recalc_error_class(row: dict) -> str:
    """Re-apply classify_error to a stored results.jsonl row (raw fields unchanged)."""
    score = row.get("score") or {}
    stub = {
        "tools": row.get("tools") or [],
        "prompt_error": row.get("prompt_error"),
        "perm_blocked": row.get("perm_blocked"),
        "turn_error": row.get("turn_error"),
        "turn_aborted": row.get("turn_aborted"),
        "fail_to_pass": row.get("fail_to_pass"),
        "empty_start": row.get("empty_start"),
    }
    if row.get("empty_start"):
        return "harness_session"
    return classify_error(stub, score)


def decide() -> dict:
    rows = []
    p = OUT / "results.jsonl"
    if p.is_file():
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    latest = {}
    for r in rows:
        key = (r["task"], r["run_id"])
        prev = latest.get(key)
        if prev is None or int(r.get("attempt") or 1) >= int(prev.get("attempt") or 1):
            latest[key] = r
    valid = [r for r in latest.values() if not r.get("empty_start")]
    per: dict[str, list] = {}
    for r in valid:
        per.setdefault(r["task"], []).append(r)
    task_ok = {}
    must_pattern = {}
    for task, items in per.items():
        n = len(items)
        wins = sum(1 for r in items if r.get("resolved"))
        must_fails = sum(
            1
            for r in items
            if recalc_error_class(r) == "must_loss"
        )
        task_ok[task] = n >= 2 and wins >= 2
        must_pattern[task] = must_fails >= 2
    cores = [t.name for t in list_tasks()]
    ready = all(task_ok.get(t, False) for t in cores) and not any(must_pattern.values())
    return {
        "task_ok": task_ok,
        "must_pattern": must_pattern,
        "cutover": ready,
        "reason": "core tasks repeatedly resolved, no must-loss pattern"
        if ready
        else "stay 64K: missing repeated core success or must-loss pattern",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    scoped.assert_user_settings_untouched()
    start = 1
    only = os.environ.get("R80_TASK")
    tasks = list_tasks()
    if only:
        tasks = [t for t in tasks if t.name == only]
    want_runs = int(os.environ.get("R80_RUNS", str(RUNS)))
    start = int(os.environ.get("R80_START", "1"))
    for task_dir in tasks:
        for run_id in range(start, want_runs + 1):
            report = run_once(task_dir, run_id, attempt=1)
            append_result(report)
            write_status()
            if report.get("empty_start"):
                retry = run_once(task_dir, run_id, attempt=2, retry_of=1)
                append_result(retry)
                write_status()
    decision = decide()
    (OUT / "DECISION.json").write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(decision, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
