#!/usr/bin/env bash
# Cut over productive local-quality to qwen3.8:27b / num_ctx 65536.
# Does not change local-fast, parents, bench aliases, or the Ollama systemd override.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$REPO_ROOT/config/modelfiles/local-quality.Modelfile"
ROLLBACK_MF="$REPO_ROOT/config/modelfiles/local-quality.Modelfile.16k"
SET_CTX="$REPO_ROOT/scripts/set-qwen-quality-context.py"
QWEN_SETTINGS="${QWEN_SETTINGS:-/home/mike/.qwen/settings.json}"
PARENT="qwen3.8:27b"
ALIAS="local-quality"
FAST="local-fast"
TARGET_CTX=65536
PREV_CTX=16384
FAST_CTX=32768
EXPECTED_OVERRIDE_SHA="7fb44d5fbe5363ca9196bc92a95cb0d23766b4f853c491de19e134efa6d89bf4"

usage() {
  cat <<'EOF'
Usage: scripts/apply-local-quality-64k.sh [--check|--help]

  (default)  Backup, rebuild local-quality with num_ctx 65536, set Qwen contextWindowSize 65536.
  --check    Verify ollama num_ctx, Qwen provider, default model, trust, FAST 32768.

Does not pull or delete models. local-fast and systemd override stay unchanged.
Rollback: scripts/rollback-local-quality-64k.sh  (back to 16384)
EOF
}

modelfile_ctx() {
  awk '/^PARAMETER num_ctx / { print $3; found=1 } END { if (!found) exit 1 }' "$1"
}

ollama_num_ctx() {
  ollama show "$1" | awk '/num_ctx/ { print $2; found=1 } END { if (!found) exit 1 }'
}

override_sha() {
  sha256sum -- /etc/systemd/system/ollama.service.d/override.conf | awk '{print $1}'
}

cmd_check() {
  local ctx fast_ctx state quality default trust approval
  ctx="$(ollama_num_ctx "$ALIAS")"
  fast_ctx="$(ollama_num_ctx "$FAST")"
  state="$(python3 "$SET_CTX" --show "$QWEN_SETTINGS")"
  quality="$(printf '%s\n' "$state" | awk -F= '/^local-quality=/ { print $2 }')"
  default="$(printf '%s\n' "$state" | awk -F= '/^model.name=/ { print $2 }')"
  trust="$(printf '%s\n' "$state" | awk -F= '/^trust=/ { print $2 }')"
  approval="$(printf '%s\n' "$state" | awk -F= '/^approvalMode=/ { print $2 }')"
  printf 'ollama %s num_ctx=%s\n' "$ALIAS" "$ctx"
  printf 'ollama %s num_ctx=%s\n' "$FAST" "$fast_ctx"
  printf '%s\n' "$state"
  printf 'override_sha=%s\n' "$(override_sha)"
  if [[ "$ctx" != "$TARGET_CTX" ]]; then
    printf 'FAIL ollama local-quality num_ctx ist %s, erwartet %s\n' "$ctx" "$TARGET_CTX"
    exit 1
  fi
  if [[ "$fast_ctx" != "$FAST_CTX" ]]; then
    printf 'FAIL ollama local-fast num_ctx ist %s, erwartet %s\n' "$fast_ctx" "$FAST_CTX"
    exit 1
  fi
  if [[ "$quality" != "$TARGET_CTX" ]]; then
    printf 'FAIL Qwen local-quality contextWindowSize ist %s, erwartet %s\n' "$quality" "$TARGET_CTX"
    exit 1
  fi
  if [[ "$default" != "local-fast" ]]; then
    printf 'FAIL Default-Modell ist %s, erwartet local-fast\n' "$default"
    exit 1
  fi
  if [[ "$trust" != "False" && "$trust" != "false" ]]; then
    printf 'FAIL trust ist %s, erwartet false\n' "$trust"
    exit 1
  fi
  if [[ "$approval" != "default" ]]; then
    printf 'FAIL approvalMode ist %s, erwartet default\n' "$approval"
    exit 1
  fi
  if [[ "$(override_sha)" != "$EXPECTED_OVERRIDE_SHA" ]]; then
    printf 'FAIL Override-SHA geändert\n'
    exit 1
  fi
  printf 'OK   QUALITY %s, FAST %s, default local-fast, trust false\n' "$TARGET_CTX" "$FAST_CTX"
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

if [[ ! -f "$MODELFILE" || ! -f "$ROLLBACK_MF" || ! -f "$SET_CTX" || ! -f "$QWEN_SETTINGS" ]]; then
  printf '%s\n' "ABBRUCH: Modelfile, Rollback-Modelfile, Setter oder Qwen-Settings fehlen."
  exit 1
fi
if ! mountpoint -q /mnt/ai-archive; then
  printf '%s\n' "ABBRUCH: /mnt/ai-archive ist nicht eingehängt."
  exit 1
fi
if ! grep -Eq "^FROM ${PARENT}$" "$MODELFILE"; then
  printf 'ABBRUCH: Modelfile FROM ist nicht %s.\n' "$PARENT"
  exit 1
fi
if [[ "$(modelfile_ctx "$MODELFILE")" != "$TARGET_CTX" ]]; then
  printf 'ABBRUCH: Modelfile num_ctx=%s, erwartet %s.\n' "$(modelfile_ctx "$MODELFILE")" "$TARGET_CTX"
  exit 1
fi
if [[ "$(modelfile_ctx "$ROLLBACK_MF")" != "$PREV_CTX" ]]; then
  printf 'ABBRUCH: Rollback-Modelfile hat nicht num_ctx %s.\n' "$PREV_CTX"
  exit 1
fi
if ! ollama list | awk -v p="$PARENT" 'NR>1 && ($1==p || $1==p":latest") { found=1 } END { exit found?0:1 }'; then
  printf 'ABBRUCH: Parent %s fehlt. Kein Pull.\n' "$PARENT"
  exit 1
fi
if [[ "$(ollama_num_ctx "$FAST")" != "$FAST_CTX" ]]; then
  printf 'ABBRUCH: local-fast num_ctx ist %s, nicht %s.\n' "$(ollama_num_ctx "$FAST")" "$FAST_CTX"
  exit 1
fi
if [[ "$(override_sha)" != "$EXPECTED_OVERRIDE_SHA" ]]; then
  printf '%s\n' "ABBRUCH: systemd-Override-SHA weicht ab. Override nicht anfassen."
  exit 1
fi

current="$(ollama_num_ctx "$ALIAS")"
if [[ "$current" != "$PREV_CTX" && "$current" != "$TARGET_CTX" ]]; then
  printf 'ABBRUCH: unerwarteter local-quality num_ctx=%s (erwartet %s oder %s)\n' "$current" "$PREV_CTX" "$TARGET_CTX"
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${QUALITY_BACKUP_DIR:-/mnt/ai-archive/backups/local-quality-64k-$STAMP}"
mkdir -p "$BACKUP/qwen" "$BACKUP/modelfiles" "$BACKUP/systemd"
ollama show --modelfile "$ALIAS" >"$BACKUP/modelfiles/local-quality.Modelfile.prev"
ollama show --modelfile "$FAST" >"$BACKUP/modelfiles/local-fast.Modelfile.prev"
cp -a "$QWEN_SETTINGS" "$BACKUP/qwen/user-settings.json"
if [[ -f "$REPO_ROOT/.qwen/settings.json" ]]; then
  cp -a "$REPO_ROOT/.qwen/settings.json" "$BACKUP/qwen/project-settings.json"
fi
cp -a /etc/systemd/system/ollama.service.d/override.conf "$BACKUP/systemd/override.conf"
cp -a "$ROLLBACK_MF" "$BACKUP/modelfiles/local-quality.Modelfile.16k"
{
  printf 'parent=%s\n' "$PARENT"
  printf 'from_ctx=%s\n' "$current"
  printf 'target_ctx=%s\n' "$TARGET_CTX"
  printf 'override_sha=%s\n' "$(override_sha)"
  printf 'Rollback:\n'
  printf '  %s/scripts/rollback-local-quality-64k.sh\n' "$REPO_ROOT"
} >"$BACKUP/README.txt"
printf 'Backup %s\n' "$BACKUP"

if ollama ps | awk -v a="$ALIAS" 'NR>1 && ($1==a || $1==a":latest" || index($1, a)==1) { found=1 } END { exit found?0:1 }'; then
  ollama stop "$ALIAS" || true
fi

ollama create "$ALIAS" -f "$MODELFILE"
python3 "$SET_CTX" "$QWEN_SETTINGS" "$TARGET_CTX"
cmd_check
printf 'OK   apply local-quality %s, backup %s\n' "$TARGET_CTX" "$BACKUP"
