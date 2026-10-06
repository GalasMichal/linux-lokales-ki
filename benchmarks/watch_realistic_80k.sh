#!/usr/bin/env bash
# Resume remaining 80K realistic runs if the orchestrator dies or stalls.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/realistic-80k-20261004"
HELPER="$REPO/benchmarks/night_scoped_shell.py"
PY="$REPO/benchmarks/realistic_80k_coding.py"
LOG="$OUT/watchdog.log"
DONE="$OUT/DONE.md"
STOP="$OUT/WATCHDOG_STOP"
ORCH_LOG="$OUT/orchestrator.log"
STALE_SEC="${WATCH_STALE_SEC:-1200}"
mkdir -p "$OUT"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG"; }

alive() { pgrep -f "$1" >/dev/null 2>&1; }
coding_active() { pgrep -f '/benchmarks/realistic_80k_coding.py' >/dev/null 2>&1; }
fresh() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  local now mtime
  now=$(date +%s)
  mtime=$(stat -c %Y "$f")
  (( now - mtime < STALE_SEC ))
}

next_json() {
  python3 - <<'PY'
import json
from pathlib import Path
base = Path("/home/mike/Projects/Linux Lokales KI/benchmarks/realistic-80k-20261004")
tasks = ["order_service", "config_merge", "ledger_repair"]
rows = []
p = base / "results.jsonl"
if p.is_file():
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
latest = {}
for r in rows:
    key = (r["task"], int(r["run_id"]))
    prev = latest.get(key)
    if prev is None or int(r.get("attempt") or 1) >= int(prev.get("attempt") or 1):
        latest[key] = r
have = set()
for key, r in latest.items():
    if not r.get("empty_start"):
        have.add(key)
plan = []
for task in tasks:
    missing = [i for i in range(1, 4) if (task, i) not in have]
    if missing:
        plan.append({"task": task, "start": missing[0], "runs": missing[-1], "missing": missing})
print(json.dumps({"attempts": len(rows), "remaining": plan, "done": not plan}, ensure_ascii=False))
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
    python3 "$HELPER" stop || true
    restore_fast
    {
      echo "# Realistic 80K DONE"
      echo
      echo "Finished: $(date -Iseconds)"
      echo
      echo "$js"
    } > "$DONE"
    echo "=== R80 END $(date -Iseconds) ===" >> "$ORCH_LOG"
    log "DONE remaining=0"
    return 0
  fi
  return 1
}

resume_one() {
  local js task start
  js=$(next_json)
  task=$(python3 -c 'import json,sys; p=json.loads(sys.argv[1])["remaining"]; print(p[0]["task"] if p else "")' "$js")
  [[ -n "$task" ]] || return 0
  start=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["remaining"][0]["start"])' "$js")
  python3 "$HELPER" check-user
  curl -sf http://127.0.0.1:4171/health >/dev/null || python3 "$HELPER" start
  log "RESUME $task start=$start"
  CBD_OUT="$OUT" CBD_SERVE='http://127.0.0.1:4171' R80_TASK="$task" R80_START="$start" R80_RUNS=3 \
    python3 "$PY" | tee -a "$OUT/resume-$task.log" >> "$ORCH_LOG"
}

tick() {
  [[ -f "$STOP" ]] && return 0
  if [[ -f "$DONE" ]] || grep -q 'R80 END' "$ORCH_LOG" 2>/dev/null; then
    log "already finished"
    return 0
  fi
  if [[ -f "$OUT/BLOCKED.txt" ]]; then
    log "blocked"
    return 0
  fi
  local js
  js=$(next_json)
  log "tick $js orch=$(alive '/benchmarks/run_realistic_80k.sh' && echo up || echo down)"
  if finish_if_done; then
    return 0
  fi
  if coding_active() && (fresh "$ORCH_LOG" || fresh "$OUT/results.jsonl"); then
    log "healthy coding_active"
    return 0
  fi
  if alive '/benchmarks/run_realistic_80k.sh' && (fresh "$ORCH_LOG" || fresh "$OUT/results.jsonl"); then
    log "healthy orch"
    return 0
  fi
  log "HANG or dead — resume"
  pkill -f '/benchmarks/run_realistic_80k.sh' || true
  pkill -f '/benchmarks/realistic_80k_coding.py' || true
  sleep 2
  resume_one
}

loop() {
  while [[ ! -f "$STOP" && ! -f "$DONE" ]]; do
    echo "AGENT_LOOP_TICK_r80 {\"prompt\":\"check 80k realistic bench and resume if hung\"}"
    tick || log "tick error $?"
    [[ -f "$DONE" || -f "$STOP" ]] && break
    sleep 480
  done
}

cmd="${1:-loop}"
case "$cmd" in
  tick) tick ;;
  loop) loop ;;
  *) echo "usage: $0 tick|loop"; exit 2 ;;
esac
