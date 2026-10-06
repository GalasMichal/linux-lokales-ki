#!/usr/bin/env bash
# Phase 3 — Quality deepen at 64K / fill 72K+80K suites. No cutover. No auto-poweroff.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/context-boundary-20261002"
PY="$REPO/benchmarks/context_boundary_discovery.py"
export CBD_OUT="$OUT"
LOG="$OUT/orchestrator-phase3.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== PHASE3 START $(date -Iseconds) ==="
echo "CBD_OUT=$CBD_OUT — deepen QUALITY benches. NO CUTOVER. NO POWEROFF."

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
  CBD_OUT="$OUT" python3 "$PY" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
    | tee -a "$OUT/run-${tag}.log"
  echo "=== END $tag $(date -Iseconds) ==="
}

# 1) Deepen productive candidate 64K → ~10 runs each core suite
run_suite tool_chain 65536 5 6
run_suite compact 65536 7 4
run_suite coding 65536 7 4
run_suite knowledge 65536 2 4
run_suite supervisor 65536 2 4

# 2) 56K compact deepen (was 4/5) → +5
run_suite compact 57344 5 6

# 3) 72K fill KB/Supervisor + more tool (clarify drift)
run_suite knowledge 73728 3 1
run_suite supervisor 73728 3 1
run_suite tool_chain 73728 5 6

# 4) 80K fill suites (tool already 5/5)
run_suite compact 81920 5 1
run_suite knowledge 81920 3 1
run_suite supervisor 81920 3 1
run_suite coding 81920 5 1

# Restore + summarize into same OUT
python3 - <<'PY'
import json, os, importlib.util
from pathlib import Path
os.environ["CBD_OUT"] = "/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-20261002"
spec = importlib.util.spec_from_file_location(
    "cbd",
    "/home/mike/Projects/Linux Lokales KI/benchmarks/context_boundary_discovery.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(mod.summarize())
p = Path.home() / ".qwen" / "settings.json"
d = json.loads(p.read_text())
d["model"]["name"] = "local-fast"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("restored model.name=local-fast")
import subprocess
show = subprocess.check_output(["ollama", "show", "local-quality", "--modelfile"], text=True)
assert "num_ctx 16384" in show
print("local-quality still 16384")
PY

# Refresh STATUS/REPORT snapshot
python3 - <<'PY'
import json
from collections import defaultdict
from pathlib import Path
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-20261002")
rows = [json.loads(l) for l in (base/"results.jsonl").read_text().splitlines() if l.strip()]
by = defaultdict(lambda: {"n":0,"pass":0,"fail":0,"drift":0})
for r in rows:
    k=(r["suite"], r["num_ctx"])
    by[k]["n"] += 1
    by[k]["pass" if r.get("pass") else "fail"] += 1
    if r.get("drift"): by[k]["drift"] += 1
suites=["tool_chain","compact","knowledge","supervisor","coding"]
ctxs=[32768,40960,49152,57344,65536,73728,81920]
lines=["# Context Boundary Discovery — STATUS (Phase3)", "", f"Updated: phase3 end. Runs={len(rows)}. **Kein Cutover.**", "",
"| Context | Tool | Compact | KB | Supervisor | Coding | Drift |",
"|---|---|---|---|---|---|---|"]
for c in ctxs:
    cells=[]; drift=0
    for s in suites:
        v=by.get((s,c))
        if not v: cells.append("—")
        else:
            cells.append(f"{v['pass']}/{v['n']}")
            drift += v["drift"]
    lines.append(f"| {c} | "+" | ".join(cells)+f" | {drift} |")
(base/"STATUS.md").write_text("\n".join(lines)+"\n")
print("STATUS refreshed")
PY

echo "=== PHASE3 END $(date -Iseconds) ==="
echo "NO CUTOVER. NO POWEROFF. PC stays on for user return."
