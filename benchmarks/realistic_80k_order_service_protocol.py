#!/usr/bin/env python3
"""order_service 80K protocol validation — 3 valid runs, separate from original bench."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

REPO = Path("/home/mike/Projects/Linux Lokales KI")
OUT = REPO / "benchmarks" / "realistic-80k-order-service-protocol-20261004"
RUN_ROOT = Path("/srv/ai/workspaces/realistic-80k-order-service-protocol-20261004/runs")
PROTOCOL = REPO / "benchmarks" / "realistic_80k_tasks" / "order_service" / "PROTOCOL_WORKFLOW_v1.md"
TASK_DIR = REPO / "benchmarks" / "realistic_80k_tasks" / "order_service"
MODEL = "bench-qwen38-27b-80k"
VALID_TARGET = 3
MAX_ATTEMPTS = 6

os.environ["CBD_OUT"] = str(OUT)
os.environ["R80_RUN_ROOT"] = str(RUN_ROOT)
os.environ["R80_TASK"] = "order_service"
os.environ["R80_PROTOCOL_FILE"] = str(PROTOCOL)
os.environ["R80_BENCH_VARIANT"] = "order_service_protocol_v1_20261004"

import realistic_80k_coding as r80  # noqa: E402


def ollama_digest(model: str) -> str | None:
    try:
        proc = subprocess.run(
            ["ollama", "show", model],
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in (proc.stdout + proc.stderr).splitlines():
            if "digest" in line.lower() or len(line.strip()) == 12:
                pass
        proc2 = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in proc2.stdout.splitlines():
            if model.split(":")[0] in line:
                parts = line.split()
                for p in parts:
                    if len(p) == 12 and p.isalnum():
                        return p
    except Exception:
        return None
    return None


def classify_run_validity(report: dict) -> tuple[str, str | None]:
    """valid = graded attempt; invalid = harness/infra/tool protocol failure."""
    if report.get("prompt_error"):
        return "invalid", f"prompt_error:{report['prompt_error'][:120]}"
    if report.get("empty_start"):
        return "invalid", "harness_session_empty_start"
    if report.get("perm_blocked"):
        return "invalid", "permission_blocked"
    ec = r80.recalc_error_class(report)
    if ec in ("tool_runtime", "harness", "harness_session", "permission"):
        return "invalid", ec
    return "valid", None


def write_manifest(digest: str | None) -> None:
    manifest = {
        "bench_variant": os.environ["R80_BENCH_VARIANT"],
        "task": "order_service",
        "num_ctx": r80.CTX,
        "model": MODEL,
        "model_digest": digest,
        "protocol_file": str(PROTOCOL),
        "run_root": str(RUN_ROOT),
        "session_cwd": r80.SESSION_CWD,
        "serve": os.environ.get("CBD_SERVE", "http://127.0.0.1:4171"),
        "qwen": "stable /srv/ai/apps/qwen-code (not nightly)",
        "prod_local_quality_num_ctx": 65536,
        "distinct_from": "benchmarks/realistic-80k-20261004 (original prompt, no protocol block)",
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_scoreboard(valid_runs: list[dict], invalid_runs: list[dict]) -> dict:
    resolved = sum(1 for r in valid_runs if r.get("resolved"))
    must_loss = sum(1 for r in valid_runs if r80.recalc_error_class(r) == "must_loss")
    tool_proto = sum(1 for r in valid_runs if r80.recalc_error_class(r) == "tool_runtime")
    agent = sum(1 for r in valid_runs if r80.recalc_error_class(r) == "agent")
    board = {
        "valid_runs": len(valid_runs),
        "invalid_runs": len(invalid_runs),
        "resolved": resolved,
        "must_loss": must_loss,
        "tool_runtime_on_valid": tool_proto,
        "agent_fail": agent,
        "recommend_80k_supervised": len(valid_runs) == VALID_TARGET
        and resolved == VALID_TARGET
        and must_loss == 0
        and tool_proto == 0,
        "recommendation": None,
    }
    if board["recommend_80k_supervised"]:
        board["recommendation"] = "80K as supervised prod candidate (all 3 valid runs resolved + MUST)"
    else:
        board["recommendation"] = "Stay 64K prod; 80K remains candidate (protocol validation did not clear MUST)"
    (OUT / "SCOREBOARD.json").write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")
    return board


def write_validation_md(valid_runs: list[dict], invalid_runs: list[dict], board: dict) -> None:
    lines = [
        "# order_service 80K protocol validation (2026-10-04)",
        "",
        "Not comparable to `realistic-80k-20261004` without reading `MANIFEST.json`.",
        "",
        "## Prompt delta",
        "",
        "- Base: same `issue.md` fixture and hidden MUST tests.",
        "- Added: `PROTOCOL_WORKFLOW_v1.md` (tool_search, checklist, self-check, MUST reminder).",
        "",
        "## Results",
        "",
        f"- Valid runs: {len(valid_runs)} (target {VALID_TARGET})",
        f"- Invalid runs: {len(invalid_runs)}",
        f"- Full task success (resolved): {board['resolved']}/{len(valid_runs)}",
        f"- MUST violations (valid runs): {board['must_loss']}",
        f"- Tool/protocol on valid runs: {board['tool_runtime_on_valid']}",
        "",
        "### Valid runs",
        "",
    ]
    for r in valid_runs:
        lines.append(
            f"- slot {r.get('validation_slot')} run_id={r.get('run_id')} "
            f"class={r80.recalc_error_class(r)} resolved={r.get('resolved')} "
            f"visible={r.get('fail_to_pass')} musts={r.get('musts_ok')} "
            f"tools_failed={r.get('tools_failed')}"
        )
    if invalid_runs:
        lines.append("")
        lines.append("### Invalid runs (not counted toward success)")
        lines.append("")
        for r in invalid_runs:
            lines.append(
                f"- attempt {r.get('validation_attempt')} reason={r.get('invalid_reason')} "
                f"class={r.get('error_class')} elapsed={r.get('elapsed_s')}s"
            )
    lines.append("")
    lines.append(f"**Recommendation:** {board['recommendation']}")
    (OUT / "VALIDATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    digest = ollama_digest(MODEL)
    write_manifest(digest)

    valid_runs: list[dict] = []
    invalid_runs: list[dict] = []
    attempt = 0
    slot = 0

    while len(valid_runs) < VALID_TARGET and attempt < MAX_ATTEMPTS:
        attempt += 1
        slot += 1
        run_id = slot
        print(f"\n[protocol] attempt={attempt} slot={slot} valid_so_far={len(valid_runs)}", flush=True)
        report = r80.run_once(TASK_DIR, run_id, attempt=1)
        report["validation_attempt"] = attempt
        report["validation_slot"] = slot
        validity, reason = classify_run_validity(report)
        report["run_validity"] = validity
        report["invalid_reason"] = reason
        r80.append_result(report)

        if validity == "invalid":
            invalid_runs.append(report)
            print(f"[protocol] INVALID {reason}", flush=True)
        else:
            valid_runs.append(report)
            print(
                f"[protocol] VALID class={report['error_class']} resolved={report['resolved']}",
                flush=True,
            )
        r80.write_status()
        time.sleep(2)

    board = write_scoreboard(valid_runs, invalid_runs)
    write_validation_md(valid_runs, invalid_runs, board)
    (OUT / "DECISION.json").write_text(
        json.dumps(
            {
                "cutover": False,
                "protocol_validation": True,
                "scoreboard": board,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(board, ensure_ascii=False), flush=True)
    return 0 if len(valid_runs) == VALID_TARGET else 2


if __name__ == "__main__":
    raise SystemExit(main())
