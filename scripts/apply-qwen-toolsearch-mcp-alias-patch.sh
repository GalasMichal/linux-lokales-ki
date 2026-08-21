#!/usr/bin/env bash
# Apply Qwen Code 0.21.15 host patches: ToolSearch MCP alias, registry short-name,
# and git-snapshot branch-only. Idempotent. No sudo. Does not change Ollama.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_DIR="$REPO_ROOT/patches/qwen-code/0.21.15"
INSERT_JS="$PATCH_DIR/tool-search-insert.js"
PATCHER="$PATCH_DIR/patch_toolsearch.py"
REGISTRY_PATCHER="$PATCH_DIR/patch_registry.py"
GIT_PATCHER="$PATCH_DIR/patch_git_snapshot.py"
TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-4NQJASFC.js"
REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-L7RG5PVT.js"
QWEN_BIN="/srv/ai/apps/qwen-code/bin/qwen"
REQUIRED_VERSION="0.21.15"
ORIGINAL_SHA="a40e02e7edb10d750a724830db72ff3a691b1c7495667f171eca3affd34016a0"
SELECT_ONLY_SHA="b6107962cc9c5d4e62ac7aab6ac9026415256c33e0148021589fd2f896b01ffd"
PATCHED_V2_SHA="636ed35b02d0c8773ef9454a90dbfbf25cf2b7fa1e44df441a1f89841ce19364"
REGISTRY_STOCK_SHA="7d3c61a974a5355985fcfa9e3fbe93a4510d9f0142e44ac11cb95b13103e9b02"
BACKUP_BASE="/mnt/ai-archive/backups/qwen-code"
SELECT_MARKER="function resolveSelectToolName("
KEYWORD_MARKER="function collectKeywordCandidateNames("
REGISTRY_MARKER="resolveMcpShortToolName("
GIT_MARKER="linux-lokales-ki-omit-git-snapshot"

usage() {
  cat <<'EOF'
Usage: scripts/apply-qwen-toolsearch-mcp-alias-patch.sh [--check|--help]

  (default)   Patch Qwen Code 0.21.15 (ToolSearch + registry alias + git snapshot).
  --check     Verify version, SHA/pattern, and patch level.
  --help      Show this help.

Rollback: scripts/rollback-qwen-toolsearch-mcp-alias-patch.sh
Restores stock 0.21.15, not an intermediate patch.
Do not apply blindly to a newer Qwen version.
EOF
}

file_sha() {
  sha256sum -- "$1" | awk '{print $1}'
}

check_prereqs() {
  if [[ ! -x "$QWEN_BIN" ]]; then
    printf '%s\n' "ABBRUCH: Qwen fehlt: $QWEN_BIN"
    exit 1
  fi
  local version
  version="$("$QWEN_BIN" --version | tr -d '[:space:]')"
  if [[ "$version" != "$REQUIRED_VERSION" ]]; then
    printf 'ABBRUCH: Qwen-Version ist %s, Patch gilt nur für %s.\n' "$version" "$REQUIRED_VERSION"
    exit 1
  fi
  if [[ ! -f "$TARGET" ]]; then
    printf '%s\n' "ABBRUCH: Zieldatei fehlt: $TARGET"
    exit 1
  fi
  if [[ ! -f "$INSERT_JS" || ! -f "$PATCHER" || ! -f "$REGISTRY_PATCHER" || ! -f "$GIT_PATCHER" ]]; then
    printf '%s\n' "ABBRUCH: Patch-Dateien fehlen unter $PATCH_DIR"
    exit 1
  fi
}

cmd_check() {
  check_prereqs
  local sha reg
  sha="$(file_sha "$TARGET")"
  printf 'SHA tool-search %s\n' "$sha"
  if grep -Fq "$KEYWORD_MARKER" "$TARGET" && grep -Fq "$SELECT_MARKER" "$TARGET"; then
    if [[ "$sha" != "$PATCHED_V2_SHA" ]]; then
      printf 'FAIL Unerwartete v2-SHA:\n  ist  %s\n  soll %s\n' "$sha" "$PATCHED_V2_SHA"
      exit 1
    fi
    printf 'OK   ToolSearch v2\n'
  elif grep -Fq "$SELECT_MARKER" "$TARGET"; then
    printf 'FAIL ToolSearch nur v1, Keyword fehlt\n'
    exit 1
  else
    printf 'FAIL ToolSearch-Patch fehlt\n'
    exit 1
  fi
  if [[ ! -f "$REGISTRY_TARGET" ]]; then
    printf '%s\n' "FAIL Registry-Chunk fehlt"
    exit 1
  fi
  reg="$(file_sha "$REGISTRY_TARGET")"
  printf 'SHA registry %s\n' "$reg"
  if grep -Fq "$REGISTRY_MARKER" "$REGISTRY_TARGET"; then
    printf 'OK   Registry MCP-Kurzname\n'
  elif [[ "$reg" != "$REGISTRY_STOCK_SHA" ]]; then
    printf 'FAIL Registry ohne Marker, unerwartete SHA\n'
    exit 1
  else
    printf 'FAIL Registry-Patch fehlt noch\n'
    exit 1
  fi
  if grep -Fq "$GIT_MARKER" "$REGISTRY_TARGET"; then
    printf 'OK   Git-Snapshot omitted\n'
    return 0
  fi
  printf 'FAIL Git-Snapshot-Patch fehlt noch\n'
  exit 1
}

cmd_apply() {
  check_prereqs
  if ! mountpoint -q /mnt/ai-archive; then
    printf '%s\n' "ABBRUCH: /mnt/ai-archive ist nicht eingehängt."
    exit 1
  fi
  local stamp backup
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup="$BACKUP_BASE/toolsearch-mcp-alias-$stamp"
  install -d -m 0755 "$backup"

  if grep -Fq "$KEYWORD_MARKER" "$TARGET" && grep -Fq "$SELECT_MARKER" "$TARGET"; then
    printf '%s\n' "OK   ToolSearch v2 bereits angewendet"
  else
    local sha
    sha="$(file_sha "$TARGET")"
    if [[ "$sha" != "$ORIGINAL_SHA" && "$sha" != "$SELECT_ONLY_SHA" ]]; then
      printf 'ABBRUCH: ToolSearch-SHA passt nicht.\n  ist  %s\n' "$sha"
      exit 1
    fi
    cp -a "$TARGET" "$backup/tool-search-4NQJASFC.js.pre-apply"
    if [[ "$sha" == "$ORIGINAL_SHA" ]]; then
      cp -a "$TARGET" "$backup/tool-search-4NQJASFC.js.bak"
    fi
    python3 "$PATCHER" "$TARGET" "$INSERT_JS"
    if ! grep -Fq "$KEYWORD_MARKER" "$TARGET"; then
      printf '%s\n' "ABBRUCH: ToolSearch-Marker fehlen."
      exit 1
    fi
  fi

  if grep -Fq "$REGISTRY_MARKER" "$REGISTRY_TARGET"; then
    printf '%s\n' "OK   Registry-Patch bereits angewendet"
  else
    local reg_sha
    reg_sha="$(file_sha "$REGISTRY_TARGET")"
    if [[ "$reg_sha" != "$REGISTRY_STOCK_SHA" ]]; then
      printf 'ABBRUCH: Registry-SHA ist nicht Stock 0.21.15.\n  ist  %s\n' "$reg_sha"
      exit 1
    fi
    cp -a "$REGISTRY_TARGET" "$backup/chunk-L7RG5PVT.js.bak"
    printf '%s\n' "$reg_sha" > "$backup/registry-sha-before.txt"
    python3 "$REGISTRY_PATCHER" "$REGISTRY_TARGET"
    if ! grep -Fq "$REGISTRY_MARKER" "$REGISTRY_TARGET"; then
      printf '%s\n' "ABBRUCH: Registry-Marker fehlt, stelle Backup wieder her."
      cp -a "$backup/chunk-L7RG5PVT.js.bak" "$REGISTRY_TARGET"
      exit 1
    fi
    printf '%s\n' "$(file_sha "$REGISTRY_TARGET")" > "$backup/registry-sha-after.txt"
    printf 'OK   Registry-Patch angewendet\n'
  fi

  if grep -Fq "$GIT_MARKER" "$REGISTRY_TARGET"; then
    printf '%s\n' "OK   Git-Snapshot-Patch bereits angewendet"
  else
    cp -a "$REGISTRY_TARGET" "$backup/chunk-L7RG5PVT.js.pre-git-snapshot"
    python3 "$GIT_PATCHER" "$REGISTRY_TARGET"
    if ! grep -Fq "$GIT_MARKER" "$REGISTRY_TARGET"; then
      printf '%s\n' "ABBRUCH: Git-Snapshot-Marker fehlt, stelle Backup wieder her."
      cp -a "$backup/chunk-L7RG5PVT.js.pre-git-snapshot" "$REGISTRY_TARGET"
      exit 1
    fi
    printf 'OK   Git-Snapshot-Patch angewendet\n'
    printf 'SHA registry nach Git-Snapshot %s\n' "$(file_sha "$REGISTRY_TARGET")"
  fi

  sha256sum -- "$TARGET" "$REGISTRY_TARGET"
  printf 'Backup %s\n' "$backup"
  "$QWEN_BIN" --version
}

case "${1:-}" in
  --help|-h) usage ;;
  --check) cmd_check ;;
  "") cmd_apply ;;
  *) usage; exit 1 ;;
esac
