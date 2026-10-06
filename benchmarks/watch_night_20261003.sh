#!/usr/bin/env bash
# Watch the 2026-10-03 night bench. Resume remaining work if the job dies or stalls.
# Does not wipe results. Does not change productive context. No poweroff.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/context-boundary-night-20261003"
HELPER="$REPO/benchmarks/night_scoped_shell.py"
SCOPED="$REPO/benchmarks/cbd_scoped.py"
PY="$REPO/benchmarks/context_boundary_discovery.py"
LOG="$OUT/watchdog.log"
STOP="$OUT/WATCHDOG_STOP"
DONE="$OUT/DONE.md"
ORCH_LOG="$OUT/orchestrator-night.log"
STALE_SEC="${WATCH_STALE_SEC:-1200}"
mkdir -p "$OUT"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG"; }

alive() {
  local pat="$1"
  pgrep -f "$pat" >/dev/null 2>&1
}

fresh() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  local now mtime
  now=$(date +%s)
  mtime=$(stat -c %Y "$f")
  (( now - mtime < STALE_SEC ))
}

user_ok() {
  python3 "$HELPER" check-user
  ollama show local-quality --modelfile | grep -q 'num_ctx 65536'
  ollama show local-fast --modelfile | grep -q 'num_ctx 32768'
}

next_json() {
  python3 - <<'PY'
import json
from collections import defaultdict
from pathlib import Path
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/context-boundary-night-20261003")
rows = []
p = base / "results.jsonl"
if p.is_file():
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
ladder_started = any(
    r.get("phase") == "ladder" or r.get("suite") not in {"coding", None}
    for r in rows
)

def infer_phase(r):
    phase = r.get("phase")
    if phase:
        return phase
    if r.get("suite") == "coding" and int(r.get("num_ctx") or 0) == 65536:
        return "shell-coding"
    if r.get("suite") == "coding" and int(r.get("num_ctx") or 0) == 81920:
        return "ladder" if ladder_started else "shell-coding"
    return "ladder"

latest = {}
for r in rows:
    key = (infer_phase(r), r["suite"], int(r["num_ctx"]), int(r["run_id"]))
    prev = latest.get(key)
    if prev is None or int(r.get("attempt") or 1) >= int(prev.get("attempt") or 1):
        latest[key] = r
have = set()
for key, r in latest.items():
    if not r.get("empty_start"):
        have.add(key)
plan = []
for ctx in (65536, 81920):
    missing = [i for i in range(1, 6) if ("shell-coding", "coding", ctx, i) not in have]
    if missing:
        plan.append({"phase": "shell-coding", "suite": "coding", "ctx": ctx, "start": missing[0], "runs": missing[-1] - missing[0] + 1, "missing": missing})
if not plan:
    for ctx in (81920, 90112, 98304):
        for suite in ("tool_chain", "compact", "knowledge", "supervisor", "coding", "multi_hop"):
            missing = [i for i in range(1, 6) if ("ladder", suite, ctx, i) not in have]
            if missing:
                plan.append({"phase": "ladder", "suite": suite, "ctx": ctx, "start": missing[0], "runs": missing[-1] - missing[0] + 1, "missing": missing})
print(json.dumps({"attempts": len(rows), "remaining": plan, "done": not plan}, ensure_ascii=False))
PY
}

ensure_4170() {
  curl -sf http://127.0.0.1:4170/health >/dev/null || systemctl --user start qwen-code-web.service
  for i in $(seq 1 40); do curl -sf http://127.0.0.1:4170/health >/dev/null && return 0; sleep 1; done
  return 1
}

ensure_4171() {
  if curl -sf http://127.0.0.1:4171/health >/dev/null; then
    return 0
  fi
  python3 "$HELPER" start
}

stop_4171() {
  python3 "$HELPER" stop || true
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

finish_if_done() {
  local js
  js=$(next_json)
  if python3 -c 'import json,sys; raise SystemExit(0 if json.loads(sys.argv[1])["done"] else 1)' "$js"; then
    stop_4171
    restore_fast
    user_ok || true
    write_status
    {
      echo "# Night 2026-10-03 DONE"
      echo
      echo "Finished: $(date -Iseconds)"
      echo
      echo "$js"
    } > "$DONE"
    echo "=== NIGHT END $(date -Iseconds) ===" >> "$ORCH_LOG"
    log "DONE remaining=0"
    return 0
  fi
  return 1
}

resume_one() {
  local js phase suite ctx start runs
  js=$(next_json)
  log "resume plan $js"
  phase=$(python3 -c 'import json,sys; p=json.loads(sys.argv[1])["remaining"]; print(p[0]["phase"] if p else "")' "$js")
  [[ -n "$phase" ]] || return 0
  suite=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["remaining"][0]["suite"])' "$js")
  ctx=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["remaining"][0]["ctx"])' "$js")
  start=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["remaining"][0]["start"])' "$js")
  runs=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["remaining"][0]["runs"])' "$js")
  user_ok
  ensure_4170
  if [[ "$phase" == "shell-coding" ]]; then
    ensure_4171
    log "RESUME A $suite ctx=$ctx start=$start runs=$runs"
    echo "=== WATCH RESUME A-$suite-ctx$ctx-r${start}n${runs} $(date -Iseconds) ===" >> "$ORCH_LOG"
    CBD_OUT="$OUT" CBD_FAMILY=quality CBD_SERVE='http://127.0.0.1:4171' \
      python3 "$SCOPED" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
      | tee -a "$OUT/run-A-${suite}-ctx${ctx}-r${start}n${runs}.log" >> "$ORCH_LOG"
    tag_phase shell-coding
  else
    stop_4171
    log "RESUME B $suite ctx=$ctx start=$start runs=$runs"
    echo "=== WATCH RESUME B-$suite-ctx$ctx-r${start}n${runs} $(date -Iseconds) ===" >> "$ORCH_LOG"
    CBD_OUT="$OUT" CBD_FAMILY=quality \
      python3 "$PY" --suite "$suite" --ctx "$ctx" --runs "$runs" --start-run "$start" \
      | tee -a "$OUT/run-B-${suite}-ctx${ctx}-r${start}n${runs}.log" >> "$ORCH_LOG"
    tag_phase ladder
  fi
  write_status
  user_ok || true
}

kill_stuck() {
  log "killing stuck night workers (keep 4170, keepawake, ollama)"
  pkill -f '/benchmarks/run_night_20261003.sh' || true
  pkill -f '/benchmarks/cbd_scoped.py' || true
  pkill -f '/benchmarks/context_boundary_discovery.py' || true
  sleep 2
}

tick() {
  if [[ -f "$STOP" ]]; then
    log "STOP file present"
    return 0
  fi
  if [[ -f "$DONE" ]] || grep -q 'NIGHT END' "$ORCH_LOG" 2>/dev/null; then
    log "already finished"
    return 0
  fi
  user_ok || log "WARN user/settings gate"
  local js
  js=$(next_json)
  log "tick $js orch=$(alive '/benchmarks/run_night_20261003.sh' && echo up || echo down) logfresh=$(fresh "$ORCH_LOG" && echo yes || echo no)"
  if finish_if_done; then
    return 0
  fi
  if alive '/benchmarks/run_night_20261003.sh' && (fresh "$ORCH_LOG" || fresh "$OUT/results.jsonl"); then
    log "healthy, leave running"
    write_status || true
    return 0
  fi
  log "HANG or dead — resume remaining"
  kill_stuck
  resume_one
}

loop() {
  log "watchdog start stale=${STALE_SEC}s"
  while [[ ! -f "$STOP" && ! -f "$DONE" ]]; do
    echo "AGENT_LOOP_TICK_nightwatch {\"prompt\":\"check night bench and resume if hung\"}"
    tick || log "tick error $?"
    if [[ -f "$DONE" || -f "$STOP" ]]; then
      break
    fi
    sleep 480
  done
  log "watchdog exit"
}

cmd="${1:-loop}"
case "$cmd" in
  tick) tick ;;
  resume) kill_stuck; resume_one ;;
  status) next_json; write_status ;;
  loop) loop ;;
  *) echo "usage: $0 tick|resume|status|loop"; exit 2 ;;
esac
