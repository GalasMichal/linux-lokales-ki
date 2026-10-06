#!/usr/bin/env bash
# Re-runs after empty-start harness fix. New OUT only. Does not overwrite fair-64vs80.
# No cutover. No poweroff. FAST stays 32K. Productive QUALITY stays 64K.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/context-boundary-retry-empty-20261003"
PY="$REPO/benchmarks/context_boundary_discovery.py"
export CBD_OUT="$OUT"
export CBD_FAMILY=quality
LOG="$OUT/orchestrator-retry.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== RETRY EMPTY START $(date -Iseconds) ==="

write_status() {
  python3 - <<'PY'
import json, time
from collections import defaultdict
from pathlib import Path
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-retry-empty-20261003")
rows = []
p = base / "results.jsonl"
if p.is_file():
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
# latest attempt per suite/ctx/run
latest = {}
for r in rows:
    key = (r["suite"], r["num_ctx"], r["run_id"])
    prev = latest.get(key)
    if prev is None or int(r.get("attempt") or 1) >= int(prev.get("attempt") or 1):
        latest[key] = r
valid = [r for r in latest.values() if not r.get("empty_start")]
by = defaultdict(lambda: {"n": 0, "pass": 0, "fail": 0, "empty_first": 0, "agent": 0})
for r in rows:
    if r.get("attempt", 1) == 1 and r.get("empty_start"):
        by[(r["suite"], r["num_ctx"])]["empty_first"] += 1
for r in valid:
    k = (r["suite"], r["num_ctx"])
    by[k]["n"] += 1
    by[k]["pass" if r.get("pass") else "fail"] += 1
    if r.get("error_class") == "agent":
        by[k]["agent"] += 1
suites = ["compact", "coding", "multi_hop", "supervisor"]
ctxs = [65536, 81920]
lines = [
    "# Retry empty-start — STATUS",
    "",
    f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}. attempts={len(rows)} valid={len(valid)}.",
    "New folder. Fair-64vs80 Rohdaten unberührt. Productive stays **65536**.",
    "",
    "| Context | Compact | Coding | MultiHop | Supervisor | empty_a1 | agent_fails |",
    "|---|---|---|---|---|---|---|",
]
for c in ctxs:
    cells = []
    empty = 0
    agent = 0
    for s in suites:
        v = by.get((s, c))
        if not v or v["n"] == 0:
            cells.append("—")
        else:
            cells.append(f"{v['pass']}/{v['n']}")
            empty += v["empty_first"]
            agent += v["agent"]
    lines.append(f"| {c} | " + " | ".join(cells) + f" | {empty} | {agent} |")
if rows:
    last = rows[-1]
    lines += ["", f"Last: {last.get('suite')} ctx={last.get('num_ctx')} r={last.get('run_id')} a={last.get('attempt')} empty={last.get('empty_start')} class={last.get('error_class')} pass={last.get('pass')}"]
(base / "STATUS.md").write_text("\n".join(lines) + "\n")
print("STATUS", len(rows), "valid", len(valid))
PY
}

gate() {
  ollama show local-quality --modelfile | grep -q 'num_ctx 65536' || {
    echo "ABBRUCH: local-quality not 65536"; exit 1;
  }
  ollama show local-fast --modelfile | grep -q 'num_ctx 32768' || {
    echo "ABBRUCH: local-fast not 32768"; exit 1;
  }
  curl -sf http://127.0.0.1:4170/health >/dev/null || systemctl --user start qwen-code-web.service
  for i in $(seq 1 40); do curl -sf http://127.0.0.1:4170/health >/dev/null && break; sleep 1; done
}

run_suite() {
  local suite="$1" ctx="$2" runs="$3" start="${4:-1}"
  local tag="${suite}-ctx${ctx}-r${start}n${runs}"
  gate
  echo "=== RUN $tag $(date -Iseconds) ==="
  CBD_OUT="$OUT" CBD_FAMILY=quality python3 "$PY" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
    | tee -a "$OUT/run-${tag}.log"
  write_status
  echo "=== END $tag $(date -Iseconds) ==="
}

write_status

# Affected empty-start suites + targeted real-error repeats
run_suite compact 65536 5 1
run_suite coding 65536 5 1
run_suite multi_hop 65536 5 1
run_suite coding 81920 5 1
run_suite multi_hop 81920 5 1
run_suite supervisor 81920 5 1

python3 - <<'PY'
import json
from pathlib import Path
p = Path.home() / ".qwen" / "settings.json"
d = json.loads(p.read_text())
d["model"]["name"] = "local-fast"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("restored model.name=local-fast")
PY

write_status
echo "=== RETRY EMPTY END $(date -Iseconds) ==="
echo "NO CUTOVER IN THIS SCRIPT. NO POWEROFF."
