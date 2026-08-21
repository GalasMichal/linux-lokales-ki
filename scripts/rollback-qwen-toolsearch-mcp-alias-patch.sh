#!/usr/bin/env bash
# Restore stock Qwen 0.21.15 ToolSearch (not an intermediate patch).
set -euo pipefail

TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-4NQJASFC.js"
REGISTRY_TARGET="/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-L7RG5PVT.js"
BACKUP_BASE="/mnt/ai-archive/backups/qwen-code"
ORIGINAL_SHA="a40e02e7edb10d750a724830db72ff3a691b1c7495667f171eca3affd34016a0"
REGISTRY_STOCK_SHA="7d3c61a974a5355985fcfa9e3fbe93a4510d9f0142e44ac11cb95b13103e9b02"
QWEN_BIN="/srv/ai/apps/qwen-code/bin/qwen"

usage() {
  cat <<'EOF'
Usage: scripts/rollback-qwen-toolsearch-mcp-alias-patch.sh [--help]

Restores ToolSearch and ToolRegistry chunks to stock Qwen 0.21.15.
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

bak=""
while IFS= read -r candidate; do
  sha="$(sha256sum -- "$candidate" | awk '{print $1}')"
  if [[ "$sha" == "$ORIGINAL_SHA" ]]; then
    bak="$candidate"
    break
  fi
done < <(find "$BACKUP_BASE" -type f \( -name 'tool-search-4NQJASFC.js.bak' -o -name 'tool-search-4NQJASFC.js.pre-apply' \) | LC_ALL=C sort)

if [[ -z "$bak" ]]; then
  printf '%s\n' "ABBRUCH: Kein Stock-Backup mit Original-SHA unter $BACKUP_BASE"
  exit 1
fi
cp -a "$bak" "$TARGET"
after="$(sha256sum -- "$TARGET" | awk '{print $1}')"
if [[ "$after" != "$ORIGINAL_SHA" ]]; then
  printf '%s\n' "ABBRUCH: ToolSearch-Restore-SHA stimmt nicht."
  exit 1
fi

reg_bak=""
while IFS= read -r candidate; do
  sha="$(sha256sum -- "$candidate" | awk '{print $1}')"
  if [[ "$sha" == "$REGISTRY_STOCK_SHA" ]]; then
    reg_bak="$candidate"
    break
  fi
done < <(find "$BACKUP_BASE" -type f -name 'chunk-L7RG5PVT.js.bak' | LC_ALL=C sort)
if [[ -n "$reg_bak" ]]; then
  cp -a "$reg_bak" "$REGISTRY_TARGET"
  after_reg="$(sha256sum -- "$REGISTRY_TARGET" | awk '{print $1}')"
  if [[ "$after_reg" != "$REGISTRY_STOCK_SHA" ]]; then
    printf '%s\n' "ABBRUCH: Registry-Restore-SHA stimmt nicht."
    exit 1
  fi
  printf 'OK   Registry-Rollback aus %s\n' "$reg_bak"
fi

printf 'OK   Stock-Rollback aus %s\n' "$bak"
sha256sum -- "$TARGET"
"$QWEN_BIN" --version
