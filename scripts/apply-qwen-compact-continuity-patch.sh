#!/usr/bin/env bash
# Compact-continuity prompt patch for Qwen Code 0.24.2 only.
# Idempotent. Does not remove ToolSearch, registry, or git-snapshot patches.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
QWEN_BIN="/srv/ai/apps/qwen-code/bin/qwen"
PATCHER="$REPO_ROOT/patches/qwen-code/0.24.2/patch_compact_continuity.py"
PROMPT_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-CXXHL3XJ.js"
TRAILER_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-VQUX7GWP.js"
PROMPT_STOCK_SHA="859c4a89149f02e271f73039bf4aa4d31eead0e08dd333d3a17f790bd754986c"
MARKER="linux-lokales-ki-compact-continuity"
REGISTRY_MARKER="resolveMcpShortToolName("
BACKUP_BASE="/mnt/ai-archive/backups/qwen-code"

usage() {
  cat <<'EOF'
Usage: scripts/apply-qwen-compact-continuity-patch.sh [--check|--rollback|--help]

  (default)    Apply the compact-continuity prompt patch.
  --check      Verify version, known SHA, and marker.
  --rollback   Remove only this patch. Other 0.24.2 patches stay.
  --help       Show this help.
EOF
}

file_sha() {
  sha256sum -- "$1" | awk '{print $1}'
}

require_version() {
  if [[ ! -x "$QWEN_BIN" ]]; then
    printf '%s\n' "ABBRUCH: Qwen fehlt: $QWEN_BIN"
    exit 1
  fi
  local version
  version="$("$QWEN_BIN" --version | tr -d '[:space:]')"
  if [[ "$version" != "0.24.2" ]]; then
    printf 'ABBRUCH: nur Qwen 0.24.2, installiert ist %s.\n' "$version"
    exit 1
  fi
  if [[ ! -f "$PROMPT_TARGET" || ! -f "$TRAILER_TARGET" || ! -f "$PATCHER" ]]; then
    printf '%s\n' "ABBRUCH: Zieldatei oder Patcher fehlt."
    exit 1
  fi
}

prompt_ready() {
  grep -Fq "$MARKER" "$PROMPT_TARGET" \
    && grep -Fq "<completed_tool_calls>" "$PROMPT_TARGET"
}

trailer_ready() {
  grep -Fq "$MARKER" "$TRAILER_TARGET" \
    && grep -Fq "completed_tool_calls" "$TRAILER_TARGET"
}

cmd_check() {
  require_version
  local sha
  sha="$(file_sha "$PROMPT_TARGET")"
  printf 'Qwen 0.24.2\nSHA prompt %s\n' "$sha"
  if prompt_ready && trailer_ready; then
    if ! grep -Fq "$REGISTRY_MARKER" "$TRAILER_TARGET"; then
      printf '%s\n' "FAIL Registry-Patch fehlt"
      exit 1
    fi
    printf 'OK   Compact-Continuity\n'
    return 0
  fi
  if [[ "$sha" == "$PROMPT_STOCK_SHA" ]] && grep -Fq "$REGISTRY_MARKER" "$TRAILER_TARGET"; then
    printf 'FAIL Compact-Patch fehlt noch (bekannte Basis)\n'
    exit 1
  fi
  printf 'ABBRUCH: unbekannte Prompt-Datei oder Registry-Patch fehlt.\n'
  exit 1
}

cmd_apply() {
  printf '%s\n' "ABBRUCH: Compact-Prompt bleibt nicht installiert. Der Lauf am 22.09.2026 zeigt: FAST schreibt ein erfolgreiches pdf_create danach trotzdem nicht als erledigt. Der Patch ist geprüft und zurückgerollt. ToolSearch, Registry und Git-Snapshot bleiben."
  exit 1
}

cmd_rollback() {
  require_version
  if ! prompt_ready || ! trailer_ready; then
    printf '%s\n' "ABBRUCH: Compact-Patch ist nicht aktiv. Nichts zurückgesetzt."
    exit 1
  fi
  python3 "$PATCHER" rollback-prompt "$PROMPT_TARGET"
  python3 "$PATCHER" rollback-trailer "$TRAILER_TARGET"
  if prompt_ready || trailer_ready; then
    printf '%s\n' "ABBRUCH: Rollback unvollständig."
    exit 1
  fi
  if ! grep -Fq "$REGISTRY_MARKER" "$TRAILER_TARGET"; then
    printf '%s\n' "ABBRUCH: Registry-Patch nach Rollback weg."
    exit 1
  fi
  local sha
  sha="$(file_sha "$PROMPT_TARGET")"
  if [[ "$sha" != "$PROMPT_STOCK_SHA" ]]; then
    printf 'ABBRUCH: Prompt nach Rollback hat nicht die Stock-SHA.\n  ist %s\n' "$sha"
    exit 1
  fi
  printf 'OK   Compact-Patch zurück. ToolSearch/Registry/Git bleiben.\n'
}

case "${1:-}" in
  --help|-h) usage ;;
  --check) cmd_check ;;
  --rollback) cmd_rollback ;;
  "") cmd_apply ;;
  *) usage; exit 2 ;;
esac
