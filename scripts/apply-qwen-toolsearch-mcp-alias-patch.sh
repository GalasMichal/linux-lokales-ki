#!/usr/bin/env bash
# Apply Qwen Code host patches: ToolSearch MCP alias, registry short-name,
# and git-snapshot omit. Idempotent. No sudo. Does not change Ollama.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
QWEN_BIN="/srv/ai/apps/qwen-code/bin/qwen"
BACKUP_BASE="/mnt/ai-archive/backups/qwen-code"
SELECT_MARKER="function resolveSelectToolName("
KEYWORD_MARKER="function collectKeywordCandidateNames("
REGISTRY_MARKER="resolveMcpShortToolName("
GIT_MARKER="linux-lokales-ki-omit-git-snapshot"

usage() {
  cat <<'EOF'
Usage: scripts/apply-qwen-toolsearch-mcp-alias-patch.sh [--check|--help]

  (default)   Patch the installed Qwen Code (version-pinned SHA checks).
  --check     Verify version, SHA/pattern, and patch level.
  --help      Show this help.

Rollback: scripts/rollback-qwen-toolsearch-mcp-alias-patch.sh
Restores stock files for the installed version, not an intermediate patch.
Do not apply a 0.21.15 patch set to 0.23.4 or the reverse.
EOF
}

file_sha() {
  sha256sum -- "$1" | awk '{print $1}'
}

detect_version() {
  if [[ ! -x "$QWEN_BIN" ]]; then
    printf '%s\n' "ABBRUCH: Qwen fehlt: $QWEN_BIN"
    exit 1
  fi
  "$QWEN_BIN" --version | tr -d '[:space:]'
}

load_version_paths() {
  local version="$1"
  PATCH_DIR="$REPO_ROOT/patches/qwen-code/$version"
  INSERT_JS="$PATCH_DIR/tool-search-insert.js"
  PATCHER="$PATCH_DIR/patch_toolsearch.py"
  REGISTRY_PATCHER="$PATCH_DIR/patch_registry.py"
  GIT_PATCHER="$PATCH_DIR/patch_git_snapshot.py"
  case "$version" in
    0.24.7)
      TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-AO4V2HFN.js"
      REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-AN36BHDM.js"
      GIT_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-L3A6AVZE.js"
      ORIGINAL_SHA="30a18693d2580717cbf8874e0c0ad0749a96e4c29da7143f0dd9286ce9bb00ea"
      PATCHED_TOOLSEARCH_SHA="2e7228baa28660669f56375e8066fecfcb9bb4993892f0580054e18268861c86"
      REGISTRY_STOCK_SHA="e927d87f7d3ce5e8a3ee9013258acfbf5bdbb702424a5b35e7ac0d49a970a411"
      REGISTRY_PATCHED_SHA="795e81a9c9ddbfeeff926e24d1b9a077a92a108abf68e3628abff1861ae62a49"
      GIT_STOCK_SHA="7ae4db66f5918c64a576dce08ef080c137d3adb6ae13c28f078b2c08ce24fec8"
      GIT_PATCHED_SHA="4c41e35fb568efe39e63ce3d4548ef5c052b6a77f8da4aefdb7ea5a7536586fc"
      TOOLSEARCH_BAK_NAME="tool-search-AO4V2HFN.js.bak"
      REGISTRY_BAK_NAME="chunk-AN36BHDM.js.bak"
      GIT_BAK_NAME="chunk-L3A6AVZE.js.bak"
      # 0.24.7: collectCandidates(bindings) + MCP short-name insert
      KEYWORD_MARKER="mcpShortNameForSelect"
      ;;
    0.24.6)
      TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-5QBXSAXP.js"
      REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-4DAVFJGK.js"
      GIT_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-ZRIS5TFG.js"
      ORIGINAL_SHA="64798dd41a86a36e33808ac7985807ba7794ae18021c471f71165a9de036b088"
      PATCHED_TOOLSEARCH_SHA="f3ccfc6cd8ee3048b9d294fb06b381704c8dc04dcab219b872ce4de869865161"
      REGISTRY_STOCK_SHA="be1e8c2f3df694ae8769d8601f5280117337607c0ccef9d5ba303517b9d5d791"
      REGISTRY_PATCHED_SHA="18858095a358d84c9ec968fe1b9561441548e01fed5fbbc47d5bbd9c2e93cc51"
      GIT_STOCK_SHA="322badbf463683412106b6a10c65090a9cd5e90f8a83fcde7c7c106f512d9776"
      GIT_PATCHED_SHA="5b8cba89a87d366b0bd3deb493a4a44dca95e9b87a65c1656c49def372688196"
      TOOLSEARCH_BAK_NAME="tool-search-5QBXSAXP.js.bak"
      REGISTRY_BAK_NAME="chunk-4DAVFJGK.js.bak"
      GIT_BAK_NAME="chunk-ZRIS5TFG.js.bak"
      # 0.24.6 uses collectCandidates rewrite, not collectKeywordCandidateNames insert.
      KEYWORD_MARKER="mcpShortNameForSelect"
      ;;
    0.24.2)
      TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-ANXFKRMW.js"
      REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-VQUX7GWP.js"
      GIT_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-IOISNXQ2.js"
      ORIGINAL_SHA="c883f6def29f1eb479254a540a9c3d63c6dd44d31b5aef3d8efa81b13653fabc"
      PATCHED_TOOLSEARCH_SHA="2034ea26db4eb499fc2ac4138d698597315c1ef1ac2df22ed7f8451b1ccd8cb4"
      REGISTRY_STOCK_SHA="901b95cd0105ffa0d4c90159e556885e6edca990687727278e98916d90dcc9c5"
      REGISTRY_PATCHED_SHA="2433fc7ca45bc5afc22efc91be0da87ba1f420b213d5d9e61a180e9525924035"
      GIT_STOCK_SHA="ffee7068d4e3df196ee71949d1a0c966a96a03147ffda529a7ad0777e726e017"
      GIT_PATCHED_SHA="263eaabf01768c1837bb6224f404916b63cce24d74477b7dbbbc57f60d1e7a2f"
      TOOLSEARCH_BAK_NAME="tool-search-ANXFKRMW.js.bak"
      REGISTRY_BAK_NAME="chunk-VQUX7GWP.js.bak"
      GIT_BAK_NAME="chunk-IOISNXQ2.js.bak"
      ;;
    0.23.4)
      TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-XCEN7VXX.js"
      REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-DCRVSIK6.js"
      GIT_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-NXUZFW3G.js"
      ORIGINAL_SHA="0a4102a6c626f09c42c76227e49893f2769523876704029261fc277120a92378"
      PATCHED_TOOLSEARCH_SHA="dcdf42c5a9eae6886f21967634818b94c70f98aeab036d0eb870d061d14418f6"
      REGISTRY_STOCK_SHA="951396560a737fcbfbfb05dfa3f83efd6b309cb80072cf0d5d303d480c5a8e58"
      REGISTRY_PATCHED_SHA="ac82a673836a95776588c3bbe155b75e0bcb630c3ce5e1ca1e4ab8ca9bd7bc46"
      GIT_STOCK_SHA="6a4773e4bf518a029d88fc2d89d8911155be26a58f8af5ffc4ee188ccf84736e"
      GIT_PATCHED_SHA="aad7c86aa166989ca6da1be6e0c0a9c66ffb9a92e31089cb642782262ce11da2"
      TOOLSEARCH_BAK_NAME="tool-search-XCEN7VXX.js.bak"
      REGISTRY_BAK_NAME="chunk-DCRVSIK6.js.bak"
      GIT_BAK_NAME="chunk-NXUZFW3G.js.bak"
      ;;
    0.21.15)
      TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-4NQJASFC.js"
      REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-L7RG5PVT.js"
      GIT_TARGET="$REGISTRY_TARGET"
      ORIGINAL_SHA="a40e02e7edb10d750a724830db72ff3a691b1c7495667f171eca3affd34016a0"
      PATCHED_TOOLSEARCH_SHA="636ed35b02d0c8773ef9454a90dbfbf25cf2b7fa1e44df441a1f89841ce19364"
      REGISTRY_STOCK_SHA="7d3c61a974a5355985fcfa9e3fbe93a4510d9f0142e44ac11cb95b13103e9b02"
      REGISTRY_PATCHED_SHA=""
      GIT_STOCK_SHA=""
      GIT_PATCHED_SHA=""
      TOOLSEARCH_BAK_NAME="tool-search-4NQJASFC.js.bak"
      REGISTRY_BAK_NAME="chunk-L7RG5PVT.js.bak"
      GIT_BAK_NAME="chunk-L7RG5PVT.js.bak"
      ;;
    *)
      printf 'ABBRUCH: Kein Patch-Set für Qwen %s.\n' "$version"
      exit 1
      ;;
  esac
}

check_prereqs() {
  local version
  version="$(detect_version)"
  load_version_paths "$version"
  if [[ ! -f "$TARGET" || ! -f "$REGISTRY_TARGET" || ! -f "$GIT_TARGET" ]]; then
    printf '%s\n' "ABBRUCH: Zieldatei fehlt."
    exit 1
  fi
  if [[ ! -f "$INSERT_JS" || ! -f "$PATCHER" || ! -f "$REGISTRY_PATCHER" || ! -f "$GIT_PATCHER" ]]; then
    printf '%s\n' "ABBRUCH: Patch-Dateien fehlen unter $PATCH_DIR"
    exit 1
  fi
  printf 'Qwen %s\n' "$version"
}

cmd_check() {
  check_prereqs
  local sha
  sha="$(file_sha "$TARGET")"
  printf 'SHA tool-search %s\n' "$sha"
  if grep -Fq "$KEYWORD_MARKER" "$TARGET" && grep -Fq "$SELECT_MARKER" "$TARGET"; then
    if [[ -n "$PATCHED_TOOLSEARCH_SHA" && "$sha" != "$PATCHED_TOOLSEARCH_SHA" ]]; then
      printf 'FAIL Unerwartete ToolSearch-SHA:\n  ist  %s\n  soll %s\n' "$sha" "$PATCHED_TOOLSEARCH_SHA"
      exit 1
    fi
    printf 'OK   ToolSearch MCP-Alias\n'
  else
    printf 'FAIL ToolSearch-Patch fehlt\n'
    exit 1
  fi
  printf 'SHA registry %s\n' "$(file_sha "$REGISTRY_TARGET")"
  if grep -Fq "$REGISTRY_MARKER" "$REGISTRY_TARGET"; then
    printf 'OK   Registry MCP-Kurzname\n'
  else
    printf 'FAIL Registry-Patch fehlt noch\n'
    exit 1
  fi
  if grep -Fq "$GIT_MARKER" "$GIT_TARGET"; then
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
    printf '%s\n' "OK   ToolSearch bereits angewendet"
  else
    local sha
    sha="$(file_sha "$TARGET")"
    if [[ "$sha" != "$ORIGINAL_SHA" ]]; then
      printf 'ABBRUCH: ToolSearch-SHA passt nicht.\n  ist  %s\n' "$sha"
      exit 1
    fi
    cp -a "$TARGET" "$backup/$TOOLSEARCH_BAK_NAME"
    python3 "$PATCHER" "$TARGET" "$INSERT_JS"
    if ! grep -Fq "$KEYWORD_MARKER" "$TARGET"; then
      printf '%s\n' "ABBRUCH: ToolSearch-Marker fehlen."
      cp -a "$backup/$TOOLSEARCH_BAK_NAME" "$TARGET"
      exit 1
    fi
  fi

  if grep -Fq "$REGISTRY_MARKER" "$REGISTRY_TARGET"; then
    printf '%s\n' "OK   Registry-Patch bereits angewendet"
  else
    local reg_sha
    reg_sha="$(file_sha "$REGISTRY_TARGET")"
    if [[ "$reg_sha" != "$REGISTRY_STOCK_SHA" ]]; then
      printf 'ABBRUCH: Registry-SHA ist nicht Stock.\n  ist  %s\n' "$reg_sha"
      exit 1
    fi
    cp -a "$REGISTRY_TARGET" "$backup/$REGISTRY_BAK_NAME"
    python3 "$REGISTRY_PATCHER" "$REGISTRY_TARGET"
    if ! grep -Fq "$REGISTRY_MARKER" "$REGISTRY_TARGET"; then
      printf '%s\n' "ABBRUCH: Registry-Marker fehlt, stelle Backup wieder her."
      cp -a "$backup/$REGISTRY_BAK_NAME" "$REGISTRY_TARGET"
      exit 1
    fi
    printf 'OK   Registry-Patch angewendet\n'
  fi

  if grep -Fq "$GIT_MARKER" "$GIT_TARGET"; then
    printf '%s\n' "OK   Git-Snapshot-Patch bereits angewendet"
  else
    local git_sha
    git_sha="$(file_sha "$GIT_TARGET")"
    if [[ -n "$GIT_STOCK_SHA" && "$git_sha" != "$GIT_STOCK_SHA" ]]; then
      printf 'ABBRUCH: Git-Chunk-SHA ist nicht Stock.\n  ist  %s\n' "$git_sha"
      exit 1
    fi
    cp -a "$GIT_TARGET" "$backup/$GIT_BAK_NAME"
    python3 "$GIT_PATCHER" "$GIT_TARGET"
    if ! grep -Fq "$GIT_MARKER" "$GIT_TARGET"; then
      printf '%s\n' "ABBRUCH: Git-Snapshot-Marker fehlt, stelle Backup wieder her."
      cp -a "$backup/$GIT_BAK_NAME" "$GIT_TARGET"
      exit 1
    fi
    printf 'OK   Git-Snapshot-Patch angewendet\n'
  fi

  sha256sum -- "$TARGET" "$REGISTRY_TARGET" "$GIT_TARGET"
  printf 'Backup %s\n' "$backup"
  "$QWEN_BIN" --version
}

case "${1:-}" in
  --help|-h) usage ;;
  --check) cmd_check ;;
  "") cmd_apply ;;
  *) usage; exit 1 ;;
esac
