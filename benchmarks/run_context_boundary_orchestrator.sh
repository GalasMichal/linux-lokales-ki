#!/usr/bin/env bash
# Context Boundary Discovery orchestrator — append-only, no productive cutover.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/context-boundary-20261002"
PY="$REPO/benchmarks/context_boundary_discovery.py"
mkdir -p "$OUT"
LOG="$OUT/orchestrator.log"
exec >>"$LOG" 2>&1

echo "=== ORCH START $(date -Iseconds) ==="

wait_pid() {
  local pid="$1"
  local name="$2"
  if [[ -z "$pid" ]]; then
    echo "no pid for $name"
    return 0
  fi
  echo "wait $name pid=$pid"
  while kill -0 "$pid" 2>/dev/null; do
    sleep 20
  done
  echo "done $name $(date -Iseconds)"
}

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

# 1) Wait for initial tool_chain 32/40/48 x5 if still running
INIT_PID="$(cat "$OUT/run-tool_chain-32-40-48.pid" 2>/dev/null || true)"
if [[ -n "${INIT_PID}" ]] && kill -0 "$INIT_PID" 2>/dev/null; then
  wait_pid "$INIT_PID" "tool_chain-32-40-48-x5"
else
  echo "initial tool_chain not running (may already be finished)"
fi

# 2) Extra tool_chain depth on 40K and 48K (total toward 10+)
run_suite tool_chain 40960 5 6
run_suite tool_chain 49152 5 6

# 3) Climb: 56K and 64K tool_chain x5 each
run_suite tool_chain 57344 5 1
run_suite tool_chain 65536 5 1

# 4) Other suites at 32K (baseline) and 48K (interesting) — 3 runs each first pass
for suite in compact knowledge supervisor coding; do
  run_suite "$suite" 32768 3 1
  run_suite "$suite" 49152 3 1
done

# 5) If 56K tool_chain looked workable, add compact/coding spot checks (3 runs)
# Always run spot checks; report will show if failed.
for suite in compact coding; do
  run_suite "$suite" 57344 3 1
done

# refresh summary via python
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

# restore default model name
python3 - <<'PY'
import json
from pathlib import Path
p = Path.home() / ".qwen" / "settings.json"
d = json.loads(p.read_text())
d["model"]["name"] = "local-fast"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print("restored model.name=local-fast")
PY

echo "=== ORCH END $(date -Iseconds) ==="
echo "NO CUTOVER. local-quality must stay 16384."
