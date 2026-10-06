#!/usr/bin/env bash
# Cut over productive local-quality to num_ctx 81920. FAST stays 32768.
# Only after fair+retry criteria. Does not delete models or change the systemd override.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$REPO_ROOT/config/modelfiles/local-quality.Modelfile"
ROLLBACK_MF="$REPO_ROOT/config/modelfiles/local-quality.Modelfile.64k"
SET_CTX="$REPO_ROOT/scripts/set-qwen-quality-context.py"
QWEN_SETTINGS="${QWEN_SETTINGS:-/home/mike/.qwen/settings.json}"
PARENT="qwen3.8:27b"
ALIAS="local-quality"
FAST="local-fast"
TARGET_CTX=81920
PREV_CTX=65536
FAST_CTX=32768
EXPECTED_OVERRIDE_SHA="7fb44d5fbe5363ca9196bc92a95cb0d23766b4f853c491de19e134efa6d89bf4"

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
  [[ "$ctx" == "$TARGET_CTX" ]] || { echo "FAIL quality ctx $ctx"; exit 1; }
  [[ "$fast_ctx" == "$FAST_CTX" ]] || { echo "FAIL fast ctx $fast_ctx"; exit 1; }
  [[ "$quality" == "$TARGET_CTX" ]] || { echo "FAIL settings quality $quality"; exit 1; }
  [[ "$default" == "local-fast" ]] || { echo "FAIL default $default"; exit 1; }
  [[ "$trust" == "False" || "$trust" == "false" ]] || { echo "FAIL trust $trust"; exit 1; }
  [[ "$approval" == "default" ]] || { echo "FAIL approval $approval"; exit 1; }
  [[ "$(override_sha)" == "$EXPECTED_OVERRIDE_SHA" ]] || { echo "FAIL override sha"; exit 1; }
  echo "OK   QUALITY $TARGET_CTX FAST $FAST_CTX default local-fast trust false"
}

if [[ "${1:-}" == "--check" ]]; then
  cmd_check
  exit 0
fi
if [[ "${1:-}" == "--help" || -n "${1:-}" ]]; then
  echo "Usage: scripts/apply-local-quality-80k.sh [--check]"
  exit 0
fi

[[ -f "$ROLLBACK_MF" && "$(modelfile_ctx "$ROLLBACK_MF")" == "$PREV_CTX" ]] || {
  echo "ABBRUCH: 64K-Rollback-Modelfile fehlt oder hat nicht num_ctx $PREV_CTX"; exit 1;
}
[[ "$(ollama_num_ctx "$ALIAS")" == "$PREV_CTX" || "$(ollama_num_ctx "$ALIAS")" == "$TARGET_CTX" ]] || {
  echo "ABBRUCH: unexpected live quality ctx"; exit 1;
}
[[ "$(ollama_num_ctx "$FAST")" == "$FAST_CTX" ]] || { echo "ABBRUCH: FAST nicht $FAST_CTX"; exit 1; }
[[ "$(override_sha)" == "$EXPECTED_OVERRIDE_SHA" ]] || { echo "ABBRUCH: override sha"; exit 1; }

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${QUALITY_BACKUP_DIR:-/mnt/ai-archive/backups/local-quality-80k-$STAMP}"
mkdir -p "$BACKUP/qwen" "$BACKUP/modelfiles" "$BACKUP/systemd"
ollama show --modelfile "$ALIAS" >"$BACKUP/modelfiles/local-quality.Modelfile.prev"
ollama show --modelfile "$FAST" >"$BACKUP/modelfiles/local-fast.Modelfile.prev"
cp -a "$QWEN_SETTINGS" "$BACKUP/qwen/user-settings.json"
cp -a /etc/systemd/system/ollama.service.d/override.conf "$BACKUP/systemd/override.conf"
printf 'from=%s target=%s rollback=%s/scripts/rollback-local-quality-80k-to-64k.sh\n' \
  "$(ollama_num_ctx "$ALIAS")" "$TARGET_CTX" "$REPO_ROOT" >"$BACKUP/README.txt"
echo "Backup $BACKUP"

cat >"$MODELFILE" <<EOF
# Productive QUALITY alias. Parent weights stay qwen3.8:27b.
# Apply: scripts/apply-local-quality-80k.sh
# Rollback 64K: scripts/rollback-local-quality-80k-to-64k.sh
FROM qwen3.8:27b
PARAMETER num_ctx $TARGET_CTX
PARAMETER presence_penalty 1.5
PARAMETER temperature 1
PARAMETER top_k 20
PARAMETER top_p 0.95
PARAMETER min_p 0
PARAMETER repeat_penalty 1
PARAMETER draft_num_predict 4
EOF

if ollama ps | awk -v a="$ALIAS" 'NR>1 && index($1,a)==1 { found=1 } END { exit found?0:1 }'; then
  ollama stop "$ALIAS" || true
fi
ollama create "$ALIAS" -f "$MODELFILE"
python3 "$SET_CTX" "$QWEN_SETTINGS" "$TARGET_CTX"
cmd_check
echo "OK   apply local-quality $TARGET_CTX backup $BACKUP"
