#!/usr/bin/env bash
# order_service 80K protocol validation — stable Qwen :4171, no prod change, no 64K.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/realistic-80k-order-service-protocol-20261004"
HELPER="$REPO/benchmarks/night_scoped_shell.py"
PY="$REPO/benchmarks/realistic_80k_order_service_protocol.py"
LOG="$OUT/orchestrator.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== PROTOCOL VALIDATION START $(date -Iseconds) ==="
export CBD_OUT="$OUT"
export CBD_SERVE='http://127.0.0.1:4171'
unset QWEN_BIN
unset CBD_SCOPED_PORT

ollama show local-quality --modelfile | grep -q 'num_ctx 65536' || {
  echo "ABBRUCH: local-quality not 65536"; exit 1;
}
python3 "$HELPER" check-user

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

if ! curl -sf http://127.0.0.1:4171/health >/dev/null; then
  python3 "$HELPER" start
fi
python3 "$HELPER" probe || { echo "PROBE FAIL"; exit 2; }

python3 "$PY"
EC=$?

python3 "$HELPER" stop || true
restore_fast
echo "=== PROTOCOL VALIDATION END $(date -Iseconds) exit=$EC ==="
exit "$EC"
