#!/usr/bin/env bash
# Retarget local-quality to qwen3.8:27b / num_ctx 8192. Does not delete parents.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$REPO_ROOT/config/modelfiles/local-quality.Modelfile"
PARENT="qwen3.8:27b"
ALIAS="local-quality"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${QUALITY_BACKUP_DIR:-/mnt/ai-archive/backups/local-quality-$STAMP}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: scripts/apply-local-quality-qwen38.sh

Rebuilds local-quality FROM qwen3.8:27b with num_ctx 8192.
Saves the previous `ollama show --modelfile local-quality` under
/mnt/ai-archive/backups/local-quality-<stamp>/.
Does not change local-fast. Does not delete any models.
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
if ! awk '/^PARAMETER num_ctx / { exit ($3 == 8192 ? 0 : 1) }' "$MODELFILE"; then
  printf '%s\n' "ABBRUCH: Modelfile hat nicht num_ctx 8192."
  exit 1
fi
if ! ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$PARENT"; then
  printf 'ABBRUCH: Parent %s fehlt in ollama list.\n' "$PARENT"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
ollama show --modelfile "$ALIAS" >"$BACKUP_DIR/local-quality.Modelfile.prev"
printf '%s\n' "$BACKUP_DIR" >"$BACKUP_DIR/README.txt"
{
  printf 'Rollback:\n'
  printf '  %s/scripts/rollback-local-quality-qwen36.sh\n' "$REPO_ROOT"
  printf '  # oder: ollama create local-quality -f %s/config/modelfiles/local-quality.Modelfile.qwen36-8k\n' "$REPO_ROOT"
} >>"$BACKUP_DIR/README.txt"

if ollama ps | awk 'NR>1 {print $1}' | grep -Fxq "$ALIAS"; then
  ollama stop "$ALIAS"
fi

ollama create "$ALIAS" -f "$MODELFILE"
printf 'created %s from %s\n' "$ALIAS" "$PARENT"
ollama show "$ALIAS" | awk '/FROM|num_ctx|architecture/ { print }'
printf 'backup=%s\n' "$BACKUP_DIR"
