#!/usr/bin/env bash
# Create additive bench-qwen38-27b-16k. Does not change local-quality or local-fast.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$REPO_ROOT/config/modelfiles/bench-qwen38-27b-16k.Modelfile"
PARENT="qwen3.8:27b"
ALIAS="bench-qwen38-27b-16k"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: scripts/create-bench-qwen38-16k.sh

Creates additive alias bench-qwen38-27b-16k FROM qwen3.8:27b with num_ctx 16384.
Does not change local-quality or local-fast. Does not delete any models.
EOF
  exit 0
fi

if [[ ! -f "$MODELFILE" ]]; then
  printf '%s\n' "ABBRUCH: Modelfile fehlt."
  exit 1
fi
if ! grep -Eq "^FROM ${PARENT}$" "$MODELFILE"; then
  printf 'ABBRUCH: Modelfile FROM ist nicht %s.\n' "$PARENT"
  exit 1
fi
if ! awk '/^PARAMETER num_ctx / { exit ($3 == 16384 ? 0 : 1) }' "$MODELFILE"; then
  printf '%s\n' "ABBRUCH: Modelfile hat nicht num_ctx 16384."
  exit 1
fi
if ! ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$PARENT"; then
  printf 'ABBRUCH: Parent %s fehlt in ollama list.\n' "$PARENT"
  exit 1
fi
if ollama list | awk 'NR>1 {print $1}' | grep -Eq "^${ALIAS}(:latest)?$"; then
  printf '%s\n' "Hinweis: Alias existiert bereits, wird neu erzeugt (Parent bleibt)."
fi

# Do not stop local-quality/local-fast unless this alias is currently loaded.
if ollama ps | awk 'NR>1 {print $1}' | grep -Eq "^${ALIAS}"; then
  ollama stop "$ALIAS"
fi

ollama create "$ALIAS" -f "$MODELFILE"
printf 'created %s from %s\n' "$ALIAS" "$PARENT"
ollama show "$ALIAS" | awk '/FROM|num_ctx|architecture|parameters / { print }'
ollama list | awk -v a="$ALIAS" 'NR==1 || $1 ~ a || $1 ~ /^local-quality/ || $1 ~ /^local-fast/ || $1 ~ /^qwen3.8/'
