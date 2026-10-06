#!/usr/bin/env bash
# Isolated Qwen nightly diagnostic — order_service only, 80K, no prod touch.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/realistic-80k-nightly-diag-20261004"
NIGHT_BIN="$REPO/.agent/tmp/qwen-code-nightly-20261003/qwen-code/bin/qwen"
HELPER="$REPO/benchmarks/night_scoped_shell.py"
PY="$REPO/benchmarks/realistic_80k_coding.py"
LOG="$OUT/orchestrator.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== NIGHTLY DIAG START $(date -Iseconds) ==="
test -x "$NIGHT_BIN" || { echo "ABBRUCH: nightly qwen missing"; exit 1; }
echo "qwen=$("$NIGHT_BIN" --version)"

export CBD_OUT="$OUT"
export CBD_SERVE='http://127.0.0.1:4172'
export CBD_SCOPED_PORT=4172
export QWEN_BIN="$NIGHT_BIN"

ollama show local-quality --modelfile | grep -q 'num_ctx 65536' || { echo "ABBRUCH: prod num_ctx"; exit 1; }
python3 "$HELPER" check-user

if ! curl -sf http://127.0.0.1:4172/health >/dev/null; then
  python3 "$HELPER" start
fi
python3 "$HELPER" probe || { echo "PROBE FAIL"; exit 2; }

# Same fixtures/prompts: order_service runs 2–3 only (original abort cases).
R80_TASK=order_service R80_START=2 R80_RUNS=3 python3 "$PY"

python3 "$HELPER" stop || true
echo "=== NIGHTLY DIAG END $(date -Iseconds) ==="
