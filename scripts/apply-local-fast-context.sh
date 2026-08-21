#!/usr/bin/env bash
# Rebuild Ollama alias local-fast from parent qwen3.5:9b with repo Modelfile.
# Does not pull models, does not change QUALITY or systemd override.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$REPO_ROOT/config/modelfiles/local-fast.Modelfile"
SET_CTX="$REPO_ROOT/scripts/set-qwen-fast-context.py"
QWEN_SETTINGS="${QWEN_SETTINGS:-/home/mike/.qwen/settings.json}"
BACKUP_BASE="/mnt/ai-archive/backups/ollama-fast-ctx"
PARENT="qwen3.5:9b"
ALIAS="local-fast"
TARGET_CTX="${TARGET_CTX:-32768}"

usage() {
  cat <<'EOF'
Usage: scripts/apply-local-fast-context.sh [--check|--help]

  (default)  Backup, ollama create local-fast from repo Modelfile, sync Qwen provider context.
  --check    Verify parent, alias num_ctx, and Qwen local-fast contextWindowSize.

Does not download weights. QUALITY and /etc/systemd/.../ollama override stay unchanged.
Rollback: scripts/rollback-local-fast-context.sh
EOF
}

file_sha() {
  sha256sum -- "$1" | awk '{print $1}'
}

modelfile_ctx() {
  awk '/^PARAMETER num_ctx / { print $3; found=1 } END { if (!found) exit 1 }' "$1"
}

ollama_num_ctx() {
  ollama show "$1" | awk '/num_ctx/ { print $2; exit }'
}

cmd_check() {
  if ! ollama show "$PARENT" >/dev/null 2>&1; then
    printf 'FAIL Parent fehlt: %s\n' "$PARENT"
    exit 1
  fi
  local ctx provider_fast provider_quality
  ctx="$(ollama_num_ctx "$ALIAS")"
  provider_fast="$(python3 "$SET_CTX" --show "$QWEN_SETTINGS" | awk -F= '/^local-fast=/ { print $2 }')"
  provider_quality="$(python3 "$SET_CTX" --show "$QWEN_SETTINGS" | awk -F= '/^local-quality=/ { print $2 }')"
  printf 'ollama %s num_ctx=%s\n' "$ALIAS" "$ctx"
  printf 'qwen local-fast=%s local-quality=%s\n' "$provider_fast" "$provider_quality"
  if [[ "$ctx" != "$TARGET_CTX" ]]; then
    printf 'FAIL ollama num_ctx ist %s, erwartet %s\n' "$ctx" "$TARGET_CTX"
    exit 1
  fi
  if [[ "$provider_fast" != "$TARGET_CTX" ]]; then
    printf 'FAIL Qwen contextWindowSize ist %s, erwartet %s\n' "$provider_fast" "$TARGET_CTX"
    exit 1
  fi
  if [[ "$provider_quality" != "8192" ]]; then
    printf 'FAIL QUALITY contextWindowSize ist %s, erwartet 8192\n' "$provider_quality"
    exit 1
  fi
  printf 'OK   FAST %s, QUALITY 8192\n' "$TARGET_CTX"
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--check" ]]; then
  cmd_check
  exit 0
fi
if [[ -n "${1:-}" ]]; then
  usage
  exit 2
fi

if [[ ! -f "$MODELFILE" || ! -f "$SET_CTX" || ! -f "$QWEN_SETTINGS" ]]; then
  printf '%s\n' "ABBRUCH: Modelfile, Setter oder Qwen-Settings fehlen."
  exit 1
fi
if ! mountpoint -q /mnt/ai-archive; then
  printf '%s\n' "ABBRUCH: /mnt/ai-archive ist nicht eingehängt."
  exit 1
fi
if ! ollama show "$PARENT" >/dev/null 2>&1; then
  printf 'ABBRUCH: Parent %s fehlt. Kein Pull.\n' "$PARENT"
  exit 1
fi
mf_ctx="$(modelfile_ctx "$MODELFILE")"
if [[ "$mf_ctx" != "$TARGET_CTX" ]]; then
  printf 'ABBRUCH: Modelfile num_ctx=%s, Skript erwartet %s.\n' "$mf_ctx" "$TARGET_CTX"
  exit 1
fi
if ! grep -Eq "^FROM ${PARENT}$" "$MODELFILE"; then
  printf 'ABBRUCH: Modelfile FROM ist nicht %s.\n' "$PARENT"
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_BASE/$STAMP"
install -d -m 0755 "$BACKUP"
ollama show --modelfile "$ALIAS" > "$BACKUP/local-fast.Modelfile.before"
cp -a "$QWEN_SETTINGS" "$BACKUP/qwen-settings.json"
if [[ -f "$REPO_ROOT/.qwen/settings.json" ]]; then
  cp -a "$REPO_ROOT/.qwen/settings.json" "$BACKUP/project-settings.json"
fi
{
  printf 'parent=%s\n' "$PARENT"
  printf 'target_ctx=%s\n' "$TARGET_CTX"
  printf 'modelfile_sha=%s\n' "$(file_sha "$MODELFILE")"
  printf 'qwen_settings_sha=%s\n' "$(file_sha "$QWEN_SETTINGS")"
  printf 'override_sha=%s\n' "$(sha256sum -- /etc/systemd/system/ollama.service.d/override.conf | awk '{print $1}')"
} > "$BACKUP/meta.txt"
(
  cd "$BACKUP"
  sha256sum -- local-fast.Modelfile.before qwen-settings.json meta.txt > SHA256SUMS
  if [[ -f project-settings.json ]]; then
    sha256sum -- project-settings.json >> SHA256SUMS
  fi
)
printf 'Backup %s\n' "$BACKUP"

if ollama ps | grep -q "$ALIAS"; then
  ollama stop "$ALIAS"
fi

ollama create "$ALIAS" -f "$MODELFILE"
python3 "$SET_CTX" "$QWEN_SETTINGS" "$TARGET_CTX"
cmd_check
printf 'OK   apply local-fast %s, backup %s\n' "$TARGET_CTX" "$BACKUP"
