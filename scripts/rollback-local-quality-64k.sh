#!/usr/bin/env bash
# Restore productive local-quality to qwen3.8:27b / num_ctx 16384 (pre-64K).
# Forces Qwen default model back to local-fast. Does not delete models.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$REPO_ROOT/config/modelfiles/local-quality.Modelfile.16k"
LIVE_MF="$REPO_ROOT/config/modelfiles/local-quality.Modelfile"
SET_CTX="$REPO_ROOT/scripts/set-qwen-quality-context.py"
QWEN_SETTINGS="${QWEN_SETTINGS:-/home/mike/.qwen/settings.json}"
PARENT="qwen3.8:27b"
ALIAS="local-quality"
FAST="local-fast"
TARGET_CTX=16384
FAST_CTX=32768

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: scripts/rollback-local-quality-64k.sh

Rebuilds local-quality FROM qwen3.8:27b with num_ctx 16384.
Sets Qwen local-quality.contextWindowSize 16384 and model.name=local-fast.
Does not delete qwen3.8:27b, bench aliases, or local-fast.
EOF
  exit 0
fi

if [[ ! -f "$MODELFILE" || ! -f "$SET_CTX" || ! -f "$QWEN_SETTINGS" ]]; then
  printf '%s\n' "ABBRUCH: Rollback-Modelfile, Setter oder Qwen-Settings fehlen."
  exit 1
fi
if ! grep -Eq "^FROM ${PARENT}$" "$MODELFILE"; then
  printf 'ABBRUCH: Rollback-Modelfile FROM ist nicht %s.\n' "$PARENT"
  exit 1
fi
if ! awk '/^PARAMETER num_ctx / { exit ($3 == 16384 ? 0 : 1) }' "$MODELFILE"; then
  printf '%s\n' "ABBRUCH: Rollback-Modelfile hat nicht num_ctx 16384."
  exit 1
fi
if ! ollama list | awk -v p="$PARENT" 'NR>1 && ($1==p || $1==p":latest") { found=1 } END { exit found?0:1 }'; then
  printf 'ABBRUCH: Parent %s fehlt.\n' "$PARENT"
  exit 1
fi
if [[ "$(ollama show "$FAST" | awk '/num_ctx/ { print $2; found=1 } END { if (!found) exit 1 }')" != "$FAST_CTX" ]]; then
  printf 'ABBRUCH: local-fast num_ctx ist nicht %s.\n' "$FAST_CTX"
  exit 1
fi

if ollama ps | awk -v a="$ALIAS" 'NR>1 && index($1, a)==1 { found=1 } END { exit found?0:1 }'; then
  ollama stop "$ALIAS" || true
fi

# Keep the live Modelfile in sync with the restored 16k alias.
cat >"$LIVE_MF" <<'EOF'
# Productive QUALITY alias. Parent weights stay qwen3.8:27b.
# Apply: scripts/apply-local-quality-64k.sh
# Rollback 16K: scripts/rollback-local-quality-64k.sh
FROM qwen3.8:27b
PARAMETER num_ctx 16384
PARAMETER presence_penalty 1.5
PARAMETER temperature 1
PARAMETER top_k 20
PARAMETER top_p 0.95
PARAMETER min_p 0
PARAMETER repeat_penalty 1
PARAMETER draft_num_predict 4
EOF

ollama create "$ALIAS" -f "$MODELFILE"
python3 "$SET_CTX" "$QWEN_SETTINGS" "$TARGET_CTX"

ctx="$(ollama show "$ALIAS" | awk '/num_ctx/ { print $2; found=1 } END { if (!found) exit 1 }')"
fast="$(ollama show "$FAST" | awk '/num_ctx/ { print $2; found=1 } END { if (!found) exit 1 }')"
state="$(python3 "$SET_CTX" --show "$QWEN_SETTINGS")"
printf 'ollama %s num_ctx=%s\n' "$ALIAS" "$ctx"
printf 'ollama %s num_ctx=%s\n' "$FAST" "$fast"
printf '%s\n' "$state"
if [[ "$ctx" != "$TARGET_CTX" ]]; then
  printf 'FAIL Rollback num_ctx=%s\n' "$ctx"
  exit 1
fi
if [[ "$fast" != "$FAST_CTX" ]]; then
  printf 'FAIL FAST verändert: %s\n' "$fast"
  exit 1
fi
printf 'OK   rolled back local-quality %s, default local-fast\n' "$TARGET_CTX"
