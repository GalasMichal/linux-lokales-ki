#!/usr/bin/env bash
# Wait for Context Boundary Discovery to finish, write final report, then power off.
# Keeps sleep inhibited until shutdown. Explicitly requested by user 2026-10-02.
set -euo pipefail
OUT='/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-20261002'
REPO='/home/mike/Projects/Linux Lokales KI'
LOG="$OUT/shutdown-watcher.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== SHUTDOWN WATCHER START $(date -Iseconds) ==="
echo "Will power off after phase2 + discovery procs end."

still_running() {
  pgrep -f 'run_context_boundary_phase2\.sh|run_context_boundary_orchestrator\.sh|context_boundary_discovery\.py' >/dev/null
}

# Wait until benches idle
while still_running; do
  echo "busy $(date '+%H:%M:%S') procs=$(pgrep -f 'run_context_boundary|context_boundary_discovery' | wc -l)"
  sleep 60
done

echo "benches idle $(date -Iseconds) — writing final artifacts"

# Restore default model + gate productive alias
python3 - <<'PY'
import json, subprocess
from pathlib import Path
p = Path.home() / ".qwen" / "settings.json"
d = json.loads(p.read_text())
d.setdefault("model", {})["name"] = "local-fast"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
show = subprocess.check_output(["ollama", "show", "local-quality", "--modelfile"], text=True)
ok = "num_ctx 16384" in show
print("restored model.name=local-fast; local-quality_16384=", ok)
if not ok:
    Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-20261002/ABORT-NO-POWEROFF.txt").write_text(
        "local-quality not 16384 — refusing poweroff\n"
    )
    raise SystemExit(2)
PY

# Summarize + REPORT
python3 - <<'PY'
import json, importlib.util
from collections import defaultdict
from pathlib import Path
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-20261002")
spec = importlib.util.spec_from_file_location(
    "cbd",
    "/home/mike/Projects/Linux Lokales KI/benchmarks/context_boundary_discovery.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
summary = mod.summarize()
rows = []
for line in (base / "results.jsonl").read_text().splitlines():
    if line.strip():
        rows.append(json.loads(line))
by = defaultdict(lambda: {"n": 0, "pass": 0, "fail": 0, "drift": 0})
for r in rows:
    k = (r["suite"], r["num_ctx"])
    by[k]["n"] += 1
    by[k]["pass" if r.get("pass") else "fail"] += 1
    if r.get("drift"):
        by[k]["drift"] += 1

# Heuristic classification
ctxs = sorted({c for _, c in by})
lines = [
    "# Context Boundary Discovery — FINAL REPORT",
    "",
    f"Ended: {summary.get('updated')}",
    f"Total runs: {len(rows)}",
    "",
    "**Kein Cutover.** `local-quality` bleibt 16384.",
    "",
    "| Suite | Ctx | Pass | Fail | Drift | N |",
    "|---|---:|---:|---:|---:|---:|",
]
for (suite, ctx), s in sorted(by.items(), key=lambda x: (x[0][1], x[0][0])):
    lines.append(f"| {suite} | {ctx} | {s['pass']} | {s['fail']} | {s['drift']} | {s['n']} |")

# crude productive hints
tool = {c: by[("tool_chain", c)] for c in ctxs if ("tool_chain", c) in by}
tech = max([c for c, s in tool.items() if s["pass"] > 0] or [0])
# stable: pass rate >= 0.8 and drift==0 for tool_chain with n>=5, or suites strong
stable_candidates = []
for c in ctxs:
    t = by.get(("tool_chain", c))
    if not t or t["n"] < 3:
        continue
    rate = t["pass"] / t["n"]
    if rate >= 0.8 and t["drift"] == 0:
        stable_candidates.append(c)
highest_stable_tool = max(stable_candidates) if stable_candidates else None
# coding pass all
coding_ok = []
for c in ctxs:
    s = by.get(("coding", c))
    if s and s["n"] >= 3 and s["fail"] == 0:
        coding_ok.append(c)
highest_coding = max(coding_ok) if coding_ok else None

lines += [
    "",
    "## Boundary (vorläufig, aus Matrix)",
    f"- Highest Technically Working (tool pass>0): **{tech}**",
    f"- Highest Stable Tool-Chain (≥80% pass, drift0, n≥3): **{highest_stable_tool}**",
    f"- Highest Coding all-pass (≥3 runs): **{highest_coding}**",
    "- Highest Productive: siehe Suites — Cutover nur mit Freigabe",
    "",
    "40K bleibt tote Zone (Agent-Drift). Fokus 56K/64K+.",
    "",
    "PC fährt nach diesem Report herunter (explizite User-Anweisung).",
]
(base / "REPORT.md").write_text("\n".join(lines) + "\n")
(base / "STATUS.md").write_text("\n".join(lines) + "\n")
(base / "READY-FOR-POWEROFF").write_text(f"ok {summary.get('updated')}\n")
print("\n".join(lines))
PY

# Stop leftover models
for m in $(ollama ps | awk 'NR>1{print $1}'); do ollama stop "$m" || true; done

echo "POWEROFF in 30s $(date -Iseconds)" | tee "$OUT/POWEROFF-SCHEDULED.txt"
sleep 30

# Prefer loginctl (polkit CanPowerOff=yes); fallback systemctl
if loginctl poweroff; then
  echo "loginctl poweroff issued"
  exit 0
fi
if systemctl poweroff; then
  echo "systemctl poweroff issued"
  exit 0
fi
echo "POWEROFF FAILED" | tee "$OUT/POWEROFF-FAILED.txt"
exit 1
