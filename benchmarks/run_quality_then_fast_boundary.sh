#!/usr/bin/env bash
# Sequential: finish QUALITY Phase3 deepen, then FAST boundary.
# Keep awake via outer systemd-inhibit. No cutover. No poweroff.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
QOUT="$REPO/benchmarks/context-boundary-20261002"
FOUT="$REPO/benchmarks/context-boundary-fast-20261003"
LOG="$QOUT/orchestrator-quality-then-fast.log"
mkdir -p "$QOUT" "$FOUT"
exec >>"$LOG" 2>&1

echo "=== CHAIN START $(date -Iseconds) ==="
echo "1) QUALITY phase3 deepen  2) FAST boundary  — NO CUTOVER"

# --- Quality phase3 ---
export CBD_OUT="$QOUT"
export CBD_FAMILY=quality
bash "$REPO/benchmarks/run_context_boundary_phase3.sh"
echo "=== QUALITY PHASE3 DONE $(date -Iseconds) ==="

# restore between phases
python3 - <<'PY'
import json
from pathlib import Path
p=Path.home()/".qwen"/"settings.json"
d=json.loads(p.read_text())
d["model"]["name"]="local-fast"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False)+"\n")
print("restored local-fast")
PY
for m in $(ollama ps | awk 'NR>1{print $1}'); do ollama stop "$m" || true; done
sleep 3

# --- Fast ---
bash "$REPO/benchmarks/run_context_boundary_fast.sh"
echo "=== FAST DONE $(date -Iseconds) ==="

python3 - <<'PY'
import json, subprocess
from pathlib import Path
p=Path.home()/".qwen"/"settings.json"
d=json.loads(p.read_text())
d["model"]["name"]="local-fast"
p.write_text(json.dumps(d, indent=2, ensure_ascii=False)+"\n")
qf=subprocess.check_output(["ollama","show","local-quality","--modelfile"], text=True)
ff=subprocess.check_output(["ollama","show","local-fast","--modelfile"], text=True)
assert "num_ctx 16384" in qf
assert "num_ctx 32768" in ff
print("productive OK: quality=16384 fast=32768")
PY

echo "=== CHAIN END $(date -Iseconds) ==="
echo "NO CUTOVER. PC stays on."
