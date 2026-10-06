#!/usr/bin/env bash
# Post-64K QUALITY deepen: 80K fill → 88K → 96K (+ harder coding / multi_hop).
# Productive local-quality stays 65536. No higher cutover. No poweroff.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/context-boundary-post64k-20261003"
PY="$REPO/benchmarks/context_boundary_discovery.py"
export CBD_OUT="$OUT"
export CBD_FAMILY=quality
LOG="$OUT/orchestrator-post64k.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== POST64K START $(date -Iseconds) ==="
echo "CBD_OUT=$CBD_OUT — QUALITY benches only. Productive stays 64K. NO higher cutover. NO POWEROFF."

write_status() {
  python3 - <<'PY'
import json, time
from collections import defaultdict
from pathlib import Path
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-post64k-20261003")
rows = []
p = base / "results.jsonl"
if p.is_file():
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
by = defaultdict(lambda: {"n": 0, "pass": 0, "fail": 0, "drift": 0})
for r in rows:
    k = (r["suite"], r["num_ctx"])
    by[k]["n"] += 1
    by[k]["pass" if r.get("pass") else "fail"] += 1
    if r.get("drift"):
        by[k]["drift"] += 1
suites = ["tool_chain", "compact", "knowledge", "supervisor", "coding", "multi_hop"]
ctxs = [81920, 90112, 98304]
lines = [
    "# Context Boundary Discovery — STATUS (Post-64K)",
    "",
    f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}. Runs={len(rows)}.",
    "Productive local-quality = **65536**. No higher cutover from this job.",
    "Keep-awake: systemd-inhibit pc-keepawake active separately.",
    "",
    "| Context | Tool | Compact | KB | Supervisor | Coding | MultiHop | Drift |",
    "|---|---|---|---|---|---|---|---|",
]
for c in ctxs:
    cells = []
    drift = 0
    for s in suites:
        v = by.get((s, c))
        if not v:
            cells.append("—")
        else:
            cells.append(f"{v['pass']}/{v['n']}")
            drift += v["drift"]
    lines.append(f"| {c} | " + " | ".join(cells) + f" | {drift} |")
(base / "STATUS.md").write_text("\n".join(lines) + "\n")
print("STATUS refreshed", len(rows))
PY
}

gate() {
  ollama show local-quality --modelfile | grep -qE 'num_ctx 65536|num_ctx 16384' || {
    echo "ABBRUCH: local-quality num_ctx unexpected"; exit 1;
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
  CBD_OUT="$OUT" CBD_FAMILY=quality python3 "$PY" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
    | tee -a "$OUT/run-${tag}.log"
  write_status
  echo "=== END $tag $(date -Iseconds) ==="
}

write_status

# --- 1) 80K deepen (prior partial) + harder suites ---
run_suite knowledge 81920 5 1
run_suite supervisor 81920 5 1
run_suite coding 81920 5 1
run_suite multi_hop 81920 5 1
run_suite compact 81920 5 1
run_suite tool_chain 81920 3 6

# --- 2) 88K full ladder ---
for s in tool_chain compact knowledge supervisor coding multi_hop; do
  run_suite "$s" 90112 5 1
done

# --- 3) 96K full ladder ---
for s in tool_chain compact knowledge supervisor coding multi_hop; do
  run_suite "$s" 98304 5 1
done

# Restore UI model + summarize; keep productive 64K
python3 - <<'PY'
import json, os, importlib.util, subprocess
from pathlib import Path
os.environ["CBD_OUT"] = "/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-post64k-20261003"
os.environ["CBD_FAMILY"] = "quality"
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
show = subprocess.check_output(["ollama", "show", "local-quality", "--modelfile"], text=True)
assert "num_ctx 65536" in show or "num_ctx 16384" in show
print("productive local-quality still OK")
PY

write_status

echo "=== POST64K END $(date -Iseconds) ==="
echo "NO HIGHER CUTOVER. NO POWEROFF. PC stays on."
