#!/usr/bin/env bash
# 80K-only realistic coding. Isolated :4171 scoped shell. No 64K. No YOLO.
set -euo pipefail
REPO='/home/mike/Projects/Linux Lokales KI'
OUT="$REPO/benchmarks/realistic-80k-20261004"
HELPER="$REPO/benchmarks/night_scoped_shell.py"
PY="$REPO/benchmarks/realistic_80k_coding.py"
LOG="$OUT/orchestrator.log"
mkdir -p "$OUT"
exec >>"$LOG" 2>&1

echo "=== R80 START $(date -Iseconds) ==="
export CBD_OUT="$OUT"
export CBD_FAMILY=quality
export CBD_SERVE='http://127.0.0.1:4171'

prod_gate() {
  ollama show local-quality --modelfile | grep -q 'num_ctx 65536' || {
    echo "ABBRUCH: local-quality not 65536"; exit 1;
  }
  ollama show local-fast --modelfile | grep -q 'num_ctx 32768' || {
    echo "ABBRUCH: local-fast not 32768"; exit 1;
  }
  python3 "$HELPER" check-user
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

prod_gate
if ! curl -sf http://127.0.0.1:4171/health >/dev/null; then
  python3 "$HELPER" start
fi

echo "=== PROBES $(date -Iseconds) ==="
set +e
python3 "$HELPER" probe
PROBE_RC=$?
set -e
if [[ "$PROBE_RC" -ne 0 ]]; then
  echo "PROBES FAILED — no unattended shell test."
  python3 "$HELPER" stop || true
  restore_fast
  echo "blocked=1" > "$OUT/BLOCKED.txt"
  echo "=== R80 BLOCKED $(date -Iseconds) ==="
  exit 2
fi

python3 "$PY"
restore_fast
python3 "$HELPER" check-user
python3 "$HELPER" stop || true
echo "=== R80 END $(date -Iseconds) ==="
echo "NO POWEROFF. Cutover only after DECISION.json cutover=true and manager apply."
