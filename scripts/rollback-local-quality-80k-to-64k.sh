#!/usr/bin/env bash
# Restore productive local-quality from 80K to 64K. FAST stays 32768.
set -euo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$REPO_ROOT/config/modelfiles/local-quality.Modelfile.64k"
LIVE_MF="$REPO_ROOT/config/modelfiles/local-quality.Modelfile"
SET_CTX="$REPO_ROOT/scripts/set-qwen-quality-context.py"
QWEN_SETTINGS="${QWEN_SETTINGS:-/home/mike/.qwen/settings.json}"
ALIAS="local-quality"
FAST="local-fast"
TARGET_CTX=65536
FAST_CTX=32768

awk '/^PARAMETER num_ctx / { exit ($3 == 65536 ? 0 : 1) }' "$MODELFILE" || {
  echo "ABBRUCH: Rollback-Modelfile hat nicht num_ctx 65536"; exit 1;
}
if ollama ps | awk -v a="$ALIAS" 'NR>1 && index($1,a)==1 { found=1 } END { exit found?0:1 }'; then
  ollama stop "$ALIAS" || true
fi
cp -a "$MODELFILE" "$LIVE_MF"
ollama create "$ALIAS" -f "$MODELFILE"
python3 "$SET_CTX" "$QWEN_SETTINGS" "$TARGET_CTX"
ctx="$(ollama show "$ALIAS" | awk '/num_ctx/ { print $2 }')"
fast="$(ollama show "$FAST" | awk '/num_ctx/ { print $2 }')"
[[ "$ctx" == "$TARGET_CTX" && "$fast" == "$FAST_CTX" ]] || {
  echo "FAIL rollback ctx=$ctx fast=$fast"; exit 1;
}
echo "OK   rolled back local-quality $TARGET_CTX, FAST $FAST_CTX"
