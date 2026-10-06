#!/usr/bin/env bash
# Restore stock Qwen Code ToolSearch / registry / git-snapshot chunks.
set -euo pipefail

QWEN_BIN="/srv/ai/apps/qwen-code/bin/qwen"
BACKUP_BASE="/mnt/ai-archive/backups/qwen-code"

usage() {
  cat <<'EOF'
Usage: scripts/rollback-qwen-toolsearch-mcp-alias-patch.sh [--help]

Restores ToolSearch, ToolRegistry, and git-snapshot chunks to stock
for the currently installed Qwen Code version.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if ! mountpoint -q /mnt/ai-archive; then
  printf '%s\n' "ABBRUCH: /mnt/ai-archive ist nicht eingehängt."
  exit 1
fi

version="$("$QWEN_BIN" --version | tr -d '[:space:]')"
case "$version" in
  0.24.2)
    TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-ANXFKRMW.js"
    REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-VQUX7GWP.js"
    GIT_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-IOISNXQ2.js"
    ORIGINAL_SHA="c883f6def29f1eb479254a540a9c3d63c6dd44d31b5aef3d8efa81b13653fabc"
    REGISTRY_STOCK_SHA="901b95cd0105ffa0d4c90159e556885e6edca990687727278e98916d90dcc9c5"
    GIT_STOCK_SHA="ffee7068d4e3df196ee71949d1a0c966a96a03147ffda529a7ad0777e726e017"
    TOOLSEARCH_GLOB='tool-search-ANXFKRMW.js.bak'
    REGISTRY_GLOB='chunk-VQUX7GWP.js.bak'
    GIT_GLOB='chunk-IOISNXQ2.js.bak'
    ;;
  0.23.4)
    TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-XCEN7VXX.js"
    REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-DCRVSIK6.js"
    GIT_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-NXUZFW3G.js"
    ORIGINAL_SHA="0a4102a6c626f09c42c76227e49893f2769523876704029261fc277120a92378"
    REGISTRY_STOCK_SHA="951396560a737fcbfbfb05dfa3f83efd6b309cb80072cf0d5d303d480c5a8e58"
    GIT_STOCK_SHA="6a4773e4bf518a029d88fc2d89d8911155be26a58f8af5ffc4ee188ccf84736e"
    TOOLSEARCH_GLOB='tool-search-XCEN7VXX.js.bak'
    REGISTRY_GLOB='chunk-DCRVSIK6.js.bak'
    GIT_GLOB='chunk-NXUZFW3G.js.bak'
    ;;
  0.21.15)
    TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-4NQJASFC.js"
    REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-L7RG5PVT.js"
    GIT_TARGET="$REGISTRY_TARGET"
    ORIGINAL_SHA="a40e02e7edb10d750a724830db72ff3a691b1c7495667f171eca3affd34016a0"
    REGISTRY_STOCK_SHA="7d3c61a974a5355985fcfa9e3fbe93a4510d9f0142e44ac11cb95b13103e9b02"
    GIT_STOCK_SHA=""
    TOOLSEARCH_GLOB='tool-search-4NQJASFC.js.bak'
    REGISTRY_GLOB='chunk-L7RG5PVT.js.bak'
    GIT_GLOB='chunk-L7RG5PVT.js.bak'
    ;;
  *)
    printf 'ABBRUCH: Kein Stock-Rollback für Qwen %s.\n' "$version"
    exit 1
    ;;
esac

restore_by_sha() {
  local glob="$1" want_sha="$2" dest="$3" label="$4"
  local bak="" candidate sha
  while IFS= read -r candidate; do
    sha="$(sha256sum -- "$candidate" | awk '{print $1}')"
    if [[ "$sha" == "$want_sha" ]]; then
      bak="$candidate"
      break
    fi
  done < <(find "$BACKUP_BASE" -type f -name "$glob" | LC_ALL=C sort)
  if [[ -z "$bak" ]]; then
    printf 'ABBRUCH: Kein Stock-Backup (%s) mit SHA %s unter %s\n' "$label" "$want_sha" "$BACKUP_BASE"
    exit 1
  fi
  cp -a "$bak" "$dest"
  local after
  after="$(sha256sum -- "$dest" | awk '{print $1}')"
  if [[ "$after" != "$want_sha" ]]; then
    printf 'ABBRUCH: %s-Restore-SHA stimmt nicht.\n' "$label"
    exit 1
  fi
  printf 'OK   %s-Rollback aus %s\n' "$label" "$bak"
}

restore_by_sha "$TOOLSEARCH_GLOB" "$ORIGINAL_SHA" "$TARGET" "ToolSearch"
restore_by_sha "$REGISTRY_GLOB" "$REGISTRY_STOCK_SHA" "$REGISTRY_TARGET" "Registry"
if [[ "$GIT_TARGET" != "$REGISTRY_TARGET" && -n "$GIT_STOCK_SHA" ]]; then
  restore_by_sha "$GIT_GLOB" "$GIT_STOCK_SHA" "$GIT_TARGET" "Git-Snapshot"
fi

sha256sum -- "$TARGET" "$REGISTRY_TARGET" "$GIT_TARGET"
"$QWEN_BIN" --version
