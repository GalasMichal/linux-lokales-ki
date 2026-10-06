#!/usr/bin/env bash
# Restore local-quality to qwen3.6:27b / num_ctx 8192. Does not delete qwen3.8:27b.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$REPO_ROOT/config/modelfiles/local-quality.Modelfile.qwen36-8k"
PARENT="qwen3.6:27b"
ALIAS="local-quality"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: scripts/rollback-local-quality-qwen36.sh

Rebuilds local-quality FROM qwen3.6:27b with num_ctx 8192.
Does not delete qwen3.8:27b or benchmark aliases. local-fast is untouched.
EOF
  exit 0
fi

if [[ ! -f "$MODELFILE" ]]; then
  printf '%s\n' "ABBRUCH: Rollback-Modelfile fehlt."
  exit 1
fi
if ! grep -Eq "^FROM ${PARENT}$" "$MODELFILE"; then
  printf 'ABBRUCH: Rollback-Modelfile FROM ist nicht %s.\n' "$PARENT"
  exit 1
fi
if ! awk '/^PARAMETER num_ctx / { exit ($3 == 8192 ? 0 : 1) }' "$MODELFILE"; then
  printf '%s\n' "ABBRUCH: Rollback-Modelfile hat nicht num_ctx 8192."
  exit 1
fi
if ! ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$PARENT"; then
  printf 'ABBRUCH: Parent %s fehlt in ollama list.\n' "$PARENT"
  exit 1
fi

if ollama ps | awk 'NR>1 {print $1}' | grep -Fxq "$ALIAS"; then
  ollama stop "$ALIAS"
fi

ollama create "$ALIAS" -f "$MODELFILE"
printf 'restored %s from %s\n' "$ALIAS" "$PARENT"
ollama show "$ALIAS" | awk '/FROM|num_ctx/ { print }'
