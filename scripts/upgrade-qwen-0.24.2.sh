#!/usr/bin/env bash
# Replace live Qwen Code 0.23.4 with official 0.24.2 tarball, then apply host patches.
# No sudo. Does not change Ollama, models, or ~/.qwen/settings.json.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TAR="/srv/ai/cache/qwen-code-0.24.2/qwen-code-linux-x64.tar.gz"
WANT_TAR_SHA="29101eceb493220fef57b048d58dfa494b2fd256a62acaf00b3a1208f12dadbe"
APP="/srv/ai/apps/qwen-code"
LIVE="$APP/lib/qwen-code"
KEEP="$APP/lib/qwen-code.0.23.4"
WRAPPER="$APP/bin/qwen"
WANT_VERSION="0.24.2"

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
  exec "$REPO_ROOT/scripts/apply-qwen-toolsearch-mcp-alias-patch.sh"
fi
if [[ "$current" != "0.23.4" ]]; then
  printf 'ABBRUCH: Unerwartete Live-Version %s (erwartet 0.23.4).\n' "$current"
  exit 1
fi
if [[ -e "$KEEP" ]]; then
  printf '%s\n' "ABBRUCH: $KEEP existiert schon. Rollback prüfen, nicht überschreiben."
  exit 1
fi

systemctl --user stop qwen-code-web.service 2>/dev/null || true

printf '%s\n' "Qwen-Update 0.23.4 -> 0.24.2"
mv "$LIVE" "$KEEP"
tar -xzf "$TAR" -C "$APP/lib"
if [[ ! -x "$LIVE/bin/qwen" ]]; then
  printf '%s\n' "ABBRUCH: Extract ohne bin/qwen. Stelle 0.23.4 wieder her."
  rm -rf "$LIVE"
  mv "$KEEP" "$LIVE"
  exit 1
fi
got="$("$WRAPPER" --version | tr -d '[:space:]')"
if [[ "$got" != "$WANT_VERSION" ]]; then
  printf 'ABBRUCH: Version nach Extract ist %s. Stelle 0.23.4 wieder her.\n' "$got"
  rm -rf "$LIVE"
  mv "$KEEP" "$LIVE"
  exit 1
fi
printf 'OK   Live %s  Keep %s\n' "$got" "$KEEP"
"$REPO_ROOT/scripts/apply-qwen-toolsearch-mcp-alias-patch.sh"
"$REPO_ROOT/scripts/apply-qwen-toolsearch-mcp-alias-patch.sh" --check
