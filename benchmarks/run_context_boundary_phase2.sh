#!/usr/bin/env bash
# Phase 2: deepen Context Boundary Discovery after Phase-1 orchestrator.
# Wait for Phase-1 PID if still alive. No productive cutover.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/context-boundary-20261002"
PY="$REPO/benchmarks/context_boundary_discovery.py"
LOG="$OUT/orchestrator-phase2.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== PHASE2 START $(date -Iseconds) ==="

PHASE1_PID="$(cat "$OUT/orchestrator.pid" 2>/dev/null || true)"
if [[ -n "${PHASE1_PID}" ]] && kill -0 "$PHASE1_PID" 2>/dev/null; then
  echo "waiting for phase1 pid=$PHASE1_PID"
  while kill -0 "$PHASE1_PID" 2>/dev/null; do sleep 30; done
  echo "phase1 done $(date -Iseconds)"
else
  echo "phase1 not running"
fi

gate() {
  ollama show local-quality --modelfile | grep -q 'num_ctx 16384' || {
    echo "ABBRUCH: local-quality not 16384"; exit 1;
  }
  curl -sf http://127.0.0.1:4170/health >/dev/null || systemctl --user start qwen-code-web.service
  for i in $(seq 1 40); do curl -sf http://127.0.0.1:4170/health >/dev/null && break; sleep 1; done
}

run_suite() {
  local suite="$1"
  local ctx="$2"
  local runs="$3"
  local start="${4:-1}"
  local tag="${suite}-ctx${ctx}-r${start}n${runs}"
  gate
  echo "=== RUN $tag $(date -Iseconds) ==="
  python3 "$PY" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
    | tee -a "$OUT/run-${tag}.log"
  echo "=== END $tag $(date -Iseconds) ==="
}

# A) Deepen 48K compact (was 1/3) → total 10 runs
run_suite compact 49152 7 4

# B) Suites at 56K (tool_chain already 5/5; compact 2/3; coding from phase1)
run_suite knowledge 57344 3 1
run_suite supervisor 57344 3 1
# extra compact at 56K if only 3 exist → add 2 more toward 5
run_suite compact 57344 2 4

# C) Full suite spot at 64K (tool_chain already 5/5)
for suite in compact knowledge supervisor coding; do
  run_suite "$suite" 65536 3 1
done

# D) Climb: 72K tool_chain x5, then compact+coding x3 if tool looks workable
run_suite tool_chain 73728 5 1
run_suite compact 73728 3 1
run_suite coding 73728 3 1

# E) If still climbing: 80K tool_chain x5 only (stop early on hard fail via report)
run_suite tool_chain 81920 5 1

python3 - <<'PY'
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location(
    "cbd",
    "/home/mike/Projects/Linux Lokales KI/benchmarks/context_boundary_discovery.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(mod.summarize())
PY

python3 - <<'PY'
import json
from pathlib import Path
p = Path.home() / ".qwen" / "settings.json"
d = json.loads(p.read_text())
d["model"]["name"] = "local-fast"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("restored model.name=local-fast")
# productive gate
import subprocess
show = subprocess.check_output(["ollama", "show", "local-quality", "--modelfile"], text=True)
assert "num_ctx 16384" in show
print("local-quality still 16384")
PY

# refresh STATUS snapshot
python3 - <<'PY'
import json
from pathlib import Path
from collections import defaultdict
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-20261002")
rows = []
for line in (base / "results.jsonl").read_text().splitlines():
    if line.strip():
        rows.append(json.loads(line))
by = defaultdict(lambda: {"pass": 0, "fail": 0, "drift": 0, "n": 0})
for r in rows:
    k = (r["suite"], r["num_ctx"])
    by[k]["n"] += 1
    by[k]["pass" if r.get("pass") else "fail"] += 1
    if r.get("drift"):
        by[k]["drift"] += 1
lines = ["# Context Boundary Discovery — STATUS", "", f"Stand: auto-update after Phase2. Runs={len(rows)}. **Kein Cutover.**", "", "| Suite | Ctx | Pass | Fail | Drift | N |", "|---|---:|---:|---:|---:|---:|"]
for (suite, ctx), s in sorted(by.items(), key=lambda x: (x[0][1], x[0][0])):
    lines.append(f"| {suite} | {ctx} | {s['pass']} | {s['fail']} | {s['drift']} | {s['n']} |")
(base / "STATUS.md").write_text("\n".join(lines) + "\n")
print("STATUS.md refreshed")
PY

echo "=== PHASE2 END $(date -Iseconds) ==="
echo "NO CUTOVER. local-quality must stay 16384."
