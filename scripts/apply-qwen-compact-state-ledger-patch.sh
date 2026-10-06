#!/usr/bin/env bash
# Compact state ledger for Qwen Code 0.24.2.
# Idempotent. Does not remove ToolSearch, registry, or git-snapshot patches.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
QWEN_BIN="/srv/ai/apps/qwen-code/bin/qwen"
PATCHER="$REPO_ROOT/patches/qwen-code/0.24.2/patch_compact_state_ledger.py"
TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-VQUX7GWP.js"
STOCK_SHA="2433fc7ca45bc5afc22efc91be0da87ba1f420b213d5d9e61a180e9525924035"
MARKER="linux-lokales-ki-compact-state-ledger"
REGISTRY_MARKER="resolveMcpShortToolName("
GIT_MARKER="linux-lokales-ki-omit-git-snapshot"
BACKUP_BASE="/mnt/ai-archive/backups/qwen-code"

usage() {
  cat <<'EOF'
Usage: scripts/apply-qwen-compact-state-ledger-patch.sh [--check|--rollback|--help]

  (default)    Apply the compact state ledger.
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
  if [[ ! -f "$TARGET" || ! -f "$PATCHER" ]]; then
    printf '%s\n' "ABBRUCH: Zieldatei oder Patcher fehlt."
    exit 1
  fi
}

ledger_ready() {
  grep -Fq "$MARKER" "$TARGET" && grep -Fq "function applyCompactStateLedger(" "$TARGET"
}

cmd_check() {
  require_version
  local sha
  sha="$(file_sha "$TARGET")"
  printf 'Qwen 0.24.2\nSHA registry %s\n' "$sha"
  if ! grep -Fq "$REGISTRY_MARKER" "$TARGET" || ! grep -Fq "$GIT_MARKER" /srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-IOISNXQ2.js; then
    printf '%s\n' "FAIL Registry- oder Git-Patch fehlt"
    exit 1
  fi
  if ledger_ready; then
    printf 'OK   Compact-State-Ledger\n'
    return 0
  fi
  if [[ "$sha" == "$STOCK_SHA" ]]; then
    printf 'FAIL Compact-State-Ledger fehlt noch (bekannte Basis)\n'
    exit 1
  fi
  printf 'ABBRUCH: unbekannte Registry-Datei.\n'
  exit 1
}

cmd_apply() {
  require_version
  if ! mountpoint -q /mnt/ai-archive; then
    printf '%s\n' "ABBRUCH: /mnt/ai-archive ist nicht eingehängt."
    exit 1
  fi
  if ! grep -Fq "$REGISTRY_MARKER" "$TARGET"; then
    printf '%s\n' "ABBRUCH: Registry-Patch fehlt. Ledger stoppt."
    exit 1
  fi
  if ledger_ready; then
    printf '%s\n' "OK   Compact-State-Ledger schon aktiv."
    return 0
  fi
  local sha
  sha="$(file_sha "$TARGET")"
  if [[ "$sha" != "$STOCK_SHA" ]]; then
    printf 'ABBRUCH: Registry-SHA ist nicht die bekannte Basis.\n  ist  %s\n  soll %s\n' "$sha" "$STOCK_SHA"
    exit 1
  fi
  local stamp backup
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup="$BACKUP_BASE/compact-state-ledger-$stamp"
  mkdir -p -- "$backup"
  cp -a -- "$TARGET" "$backup/chunk-VQUX7GWP.js"
  cp -a -- "$HOME/.qwen/settings.json" "$backup/home-settings.json"
  cp -a -- "$REPO_ROOT/.qwen/settings.json" "$backup/project-settings.json"
  printf '%s\n' "$backup" > "$backup/BACKUP.path"
  python3 "$PATCHER" apply "$TARGET"
  if ! ledger_ready || ! grep -Fq "$REGISTRY_MARKER" "$TARGET"; then
    printf '%s\n' "ABBRUCH: Patch unvollständig. Rollback."
    python3 "$PATCHER" rollback "$TARGET" || true
    exit 1
  fi
  printf 'OK   Compact-State-Ledger\nBackup %s\n' "$backup"
}

cmd_rollback() {
  require_version
  if ! ledger_ready; then
    printf '%s\n' "ABBRUCH: Ledger ist nicht aktiv. Nichts zurückgesetzt."
    exit 1
  fi
  python3 "$PATCHER" rollback "$TARGET"
  if ledger_ready; then
    printf '%s\n' "ABBRUCH: Rollback unvollständig."
    exit 1
  fi
  local sha
  sha="$(file_sha "$TARGET")"
  if [[ "$sha" != "$STOCK_SHA" ]]; then
    printf 'ABBRUCH: Datei nach Rollback hat nicht die Basis-SHA.\n  ist %s\n' "$sha"
    exit 1
  fi
  if ! grep -Fq "$REGISTRY_MARKER" "$TARGET"; then
    printf '%s\n' "ABBRUCH: Registry-Patch nach Rollback weg."
    exit 1
  fi
  printf 'OK   Ledger zurück. ToolSearch/Registry/Git bleiben.\n'
}

case "${1:-}" in
  --help|-h) usage ;;
  --check) cmd_check ;;
  --rollback) cmd_rollback ;;
  "") cmd_apply ;;
  *) usage; exit 2 ;;
esac
