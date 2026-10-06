#!/usr/bin/env bash
# Replace live Qwen Code 0.24.6 with official 0.24.7 tarball, then apply host patches.
# No sudo. Does not change Ollama, models, or ~/.qwen/settings.json trust/approval.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TAR="/srv/ai/cache/qwen-code-0.24.7/qwen-code-linux-x64.tar.gz"
WANT_TAR_SHA="5f1953eac22a413348c36a6eba542f93915f90d3c61ecbeff1ee32bbacfb640a"
APP="/srv/ai/apps/qwen-code"
LIVE="$APP/lib/qwen-code"
KEEP="$APP/lib/qwen-code.0.24.6"
WRAPPER="$APP/bin/qwen"
WANT_VERSION="0.24.7"
LEDGER_PATCHER="$REPO_ROOT/patches/qwen-code/0.24.7/patch_compact_state_ledger.py"
LEDGER_TARGET="$LIVE/lib/chunks/chunk-AN36BHDM.js"
LEDGER_MARKER="linux-lokales-ki-compact-state-ledger"

file_sha() {
  sha256sum -- "$1" | awk '{print $1}'
}

if [[ ! -f "$TAR" ]]; then
  printf '%s\n' "ABBRUCH: Tarball fehlt: $TAR"
  exit 1
fi
if [[ "$(file_sha "$TAR")" != "$WANT_TAR_SHA" ]]; then
  printf '%s\n' "ABBRUCH: Tarball-SHA stimmt nicht."
  exit 1
fi
if [[ ! -x "$WRAPPER" ]]; then
  printf '%s\n' "ABBRUCH: Wrapper fehlt: $WRAPPER"
  exit 1
fi
if [[ ! -d "$LIVE" ]]; then
  printf '%s\n' "ABBRUCH: Live-Tree fehlt: $LIVE"
  exit 1
fi

current="$("$WRAPPER" --version | tr -d '[:space:]')"
if [[ "$current" == "$WANT_VERSION" ]]; then
  printf '%s\n' "OK   Qwen $WANT_VERSION ist bereits installiert"
  "$REPO_ROOT/scripts/apply-qwen-toolsearch-mcp-alias-patch.sh"
  if ! grep -Fq "$LEDGER_MARKER" "$LEDGER_TARGET"; then
    python3 "$LEDGER_PATCHER" apply "$LEDGER_TARGET"
  fi
  exit 0
fi
if [[ "$current" != "0.24.6" ]]; then
  printf 'ABBRUCH: Unerwartete Live-Version %s (erwartet 0.24.6).\n' "$current"
  exit 1
fi
if [[ -e "$KEEP" ]]; then
  printf '%s\n' "ABBRUCH: $KEEP existiert schon. Rollback prüfen, nicht überschreiben."
  exit 1
fi

systemctl --user stop qwen-code-web.service 2>/dev/null || true

printf '%s\n' "Qwen-Update 0.24.6 -> 0.24.7"
mv "$LIVE" "$KEEP"
tar -xzf "$TAR" -C "$APP/lib"
if [[ ! -x "$LIVE/bin/qwen" ]]; then
  printf '%s\n' "ABBRUCH: Extract ohne bin/qwen. Stelle 0.24.6 wieder her."
  rm -rf "$LIVE"
  mv "$KEEP" "$LIVE"
  exit 1
fi
got="$("$WRAPPER" --version | tr -d '[:space:]')"
if [[ "$got" != "$WANT_VERSION" ]]; then
  printf 'ABBRUCH: Version nach Extract ist %s. Stelle 0.24.6 wieder her.\n' "$got"
  rm -rf "$LIVE"
  mv "$KEEP" "$LIVE"
  exit 1
fi
printf 'OK   Live %s  Keep %s\n' "$got" "$KEEP"

"$REPO_ROOT/scripts/apply-qwen-toolsearch-mcp-alias-patch.sh"
"$REPO_ROOT/scripts/apply-qwen-toolsearch-mcp-alias-patch.sh" --check

REG_AFTER_CORE="$(file_sha "$LEDGER_TARGET")"
printf 'Registry+core SHA after ToolSearch/Registry/Git: %s\n' "$REG_AFTER_CORE"
python3 "$LEDGER_PATCHER" apply "$LEDGER_TARGET"
if ! grep -Fq "$LEDGER_MARKER" "$LEDGER_TARGET"; then
  printf '%s\n' "ABBRUCH: Compact-State-Ledger fehlt nach Apply."
  exit 1
fi
printf 'OK   Compact-State-Ledger\n'
"$WRAPPER" --version
"$REPO_ROOT/scripts/apply-qwen-toolsearch-mcp-alias-patch.sh" --check
printf 'OK Qwen 0.24.7 + Patches\n'
