#!/usr/bin/env bash
# Night bench 2026-10-03: scoped-shell coding, then no-shell ladder.
# Does not mutate ~/.qwen/settings.json except the existing model.name restore.
# No YOLO. No trust:true. No productive ctx change. No poweroff.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/context-boundary-night-20261003"
PY="$REPO/benchmarks/context_boundary_discovery.py"
SCOPED="$REPO/benchmarks/cbd_scoped.py"
HELPER="$REPO/benchmarks/night_scoped_shell.py"
export CBD_OUT="$OUT"
export CBD_FAMILY=quality
export CBD_SERVE='http://127.0.0.1:4171'
LOG="$OUT/orchestrator-night.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== NIGHT START $(date -Iseconds) ==="

write_status() {
  python3 - <<'PY'
import json, time
from collections import defaultdict
from pathlib import Path
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-night-20261003")
rows = []
p = base / "results.jsonl"
if p.is_file():
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
latest = {}
for r in rows:
    key = (r.get("phase"), r["suite"], r["num_ctx"], r["run_id"])
    prev = latest.get(key)
    if prev is None or int(r.get("attempt") or 1) >= int(prev.get("attempt") or 1):
        latest[key] = r
valid = [r for r in latest.values() if not r.get("empty_start")]
by = defaultdict(lambda: {"n": 0, "pass": 0, "fail": 0, "empty_first": 0, "agent": 0})
for r in rows:
    if r.get("attempt", 1) == 1 and r.get("empty_start"):
        by[(r.get("phase"), r["suite"], r["num_ctx"])]["empty_first"] += 1
for r in valid:
    k = (r.get("phase"), r["suite"], r["num_ctx"])
    by[k]["n"] += 1
    by[k]["pass" if r.get("pass") else "fail"] += 1
    if r.get("error_class") == "agent":
        by[k]["agent"] += 1
lines = [
    "# Night 2026-10-03 — STATUS",
    "",
    f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}. attempts={len(rows)} valid={len(valid)}.",
    "Phase A = isolated serve :4171 scoped shell. Phase B = production :4170 no shell.",
    "Productive local-quality stays **65536**. No cutover from this job.",
    "",
]
for phase, ctxs, suites in (
    ("shell-coding", [65536, 81920], ["coding"]),
    ("ladder", [81920, 90112, 98304], ["tool_chain", "compact", "knowledge", "supervisor", "coding", "multi_hop"]),
):
    lines += [f"## {phase}", "", "| Context | " + " | ".join(suites) + " | empty_a1 | agent |", "|---|" + "---|" * (len(suites) + 2)]
    for c in ctxs:
        cells = []
        empty = 0
        agent = 0
        for s in suites:
            v = by.get((phase, s, c))
            if not v or v["n"] == 0:
                cells.append("—")
            else:
                cells.append(f"{v['pass']}/{v['n']}")
                empty += v["empty_first"]
                agent += v["agent"]
        lines.append(f"| {c} | " + " | ".join(cells) + f" | {empty} | {agent} |")
    lines.append("")
if rows:
    last = rows[-1]
    lines += [f"Last: phase={last.get('phase')} {last.get('suite')} ctx={last.get('num_ctx')} r={last.get('run_id')} a={last.get('attempt')} class={last.get('error_class')} pass={last.get('pass')}"]
(base / "STATUS.md").write_text("\n".join(lines) + "\n")
print("STATUS", len(rows), "valid", len(valid))
PY
}

tag_phase() {
  local phase="$1"
  python3 - "$phase" <<'PY'
import json, sys
from pathlib import Path
phase = sys.argv[1]
p = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-night-20261003/results.jsonl")
if not p.is_file():
    raise SystemExit(0)
lines = []
changed = False
for raw in p.read_text().splitlines():
    if not raw.strip():
        continue
    row = json.loads(raw)
    if "phase" not in row:
        row["phase"] = phase
        changed = True
    lines.append(json.dumps(row, ensure_ascii=False))
if changed:
    p.write_text("\n".join(lines) + "\n")
PY
}

prod_gate() {
  ollama show local-quality --modelfile | grep -q 'num_ctx 65536' || {
    echo "ABBRUCH: local-quality not 65536"; exit 1;
  }
  ollama show local-fast --modelfile | grep -q 'num_ctx 32768' || {
    echo "ABBRUCH: local-fast not 32768"; exit 1;
  }
  curl -sf http://127.0.0.1:4170/health >/dev/null || systemctl --user start qwen-code-web.service
  for i in $(seq 1 40); do curl -sf http://127.0.0.1:4170/health >/dev/null && break; sleep 1; done
  python3 "$HELPER" check-user
}

run_scoped() {
  local suite="$1" ctx="$2" runs="$3" start="${4:-1}"
  local tag="A-${suite}-ctx${ctx}-r${start}n${runs}"
  prod_gate
  curl -sf http://127.0.0.1:4171/health >/dev/null || {
    echo "ABBRUCH: isolated serve down"; exit 1;
  }
  echo "=== RUN $tag $(date -Iseconds) ==="
  CBD_OUT="$OUT" CBD_FAMILY=quality CBD_SERVE='http://127.0.0.1:4171' \
    python3 "$SCOPED" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
    | tee -a "$OUT/run-${tag}.log"
  tag_phase shell-coding
  write_status
  python3 "$HELPER" check-user
  echo "=== END $tag $(date -Iseconds) ==="
}

run_ladder() {
  local suite="$1" ctx="$2" runs="$3" start="${4:-1}"
  local tag="B-${suite}-ctx${ctx}-r${start}n${runs}"
  prod_gate
  echo "=== RUN $tag $(date -Iseconds) ==="
  CBD_OUT="$OUT" CBD_FAMILY=quality \
    python3 "$PY" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
    | tee -a "$OUT/run-${tag}.log"
  tag_phase ladder
  write_status
  python3 "$HELPER" check-user
  echo "=== END $tag $(date -Iseconds) ==="
}

restore_fast() {
  python3 - <<'PY'
import json
from pathlib import Path
p = Path.home() / ".qwen" / "settings.json"
d = json.loads(p.read_text())
d["model"]["name"] = "local-fast"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("restored model.name=local-fast")
PY
}

write_status
prod_gate

echo "=== PHASE A PROBES $(date -Iseconds) ==="
PROBE_RC=1
if curl -sf http://127.0.0.1:4171/health >/dev/null \
  && python3 -c 'import json; raise SystemExit(0 if json.load(open("'"$OUT"'/PROBES.json")).get("ok") else 1)' 2>/dev/null; then
  echo "Reusing verified PROBES.json; isolated serve healthy."
  PROBE_RC=0
else
  set +e
  python3 "$HELPER" probe
  PROBE_RC=$?
  set -e
fi
if [[ "$PROBE_RC" -ne 0 ]]; then
  echo "PROBES FAILED — no unattended shell test. Ladder only on production 4170."
  echo "shell_skipped=1" > "$OUT/SHELL_SKIPPED.txt"
  python3 "$HELPER" stop || true
else
  echo "PROBES PASSED — coding 64K/80K on isolated :4171"
  run_scoped coding 65536 5 1
  run_scoped coding 81920 5 1
  python3 "$HELPER" stop
  python3 "$HELPER" check-user
fi

echo "=== PHASE B LADDER $(date -Iseconds) ==="
unset CBD_SERVE
for ctx in 81920 90112 98304; do
  for suite in tool_chain compact knowledge supervisor coding multi_hop; do
    run_ladder "$suite" "$ctx" 5 1
  done
done

restore_fast
python3 "$HELPER" check-user
write_status
echo "=== NIGHT END $(date -Iseconds) ==="
echo "NO CUTOVER IN THIS SCRIPT. NO POWEROFF."
