#!/usr/bin/env bash
# Restore local-fast to 16K from the repo 16k Modelfile and reset Qwen provider context.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$REPO_ROOT/config/modelfiles/local-fast.Modelfile.16k"
SET_CTX="$REPO_ROOT/scripts/set-qwen-fast-context.py"
QWEN_SETTINGS="${QWEN_SETTINGS:-/home/mike/.qwen/settings.json}"
PARENT="qwen3.5:9b"
ALIAS="local-fast"
TARGET_CTX="16384"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: scripts/rollback-local-fast-context.sh

Rebuilds local-fast from config/modelfiles/local-fast.Modelfile.16k (num_ctx 16384)
and sets Qwen local-fast contextWindowSize back to 16384. QUALITY stays 8192.
EOF
  exit 0
fi

if [[ ! -f "$MODELFILE" || ! -f "$SET_CTX" ]]; then
  printf '%s\n' "ABBRUCH: 16k-Modelfile oder Setter fehlt."
  exit 1
fi
if ! grep -Eq "^FROM ${PARENT}$" "$MODELFILE"; then
  printf 'ABBRUCH: 16k-Modelfile FROM ist nicht %s.\n' "$PARENT"
  exit 1
fi
if ! awk '/^PARAMETER num_ctx / { exit ($3 == 16384 ? 0 : 1) }' "$MODELFILE"; then
  printf '%s\n' "ABBRUCH: 16k-Modelfile hat nicht num_ctx 16384."
  exit 1
fi
if ollama ps | grep -q "$ALIAS"; then
  ollama stop "$ALIAS"
fi
ollama create "$ALIAS" -f "$MODELFILE"
python3 "$SET_CTX" "$QWEN_SETTINGS" "$TARGET_CTX"
printf 'ollama num_ctx=%s\n' "$(ollama show "$ALIAS" | awk '/num_ctx/ { print $2; exit }')"
python3 "$SET_CTX" --show "$QWEN_SETTINGS"
printf 'OK   rollback local-fast 16384\n'
