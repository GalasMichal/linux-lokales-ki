#!/usr/bin/env bash
# Rollback Qwen Code 0.24.6 -> kept 0.24.2 tree. No sudo.
set -euo pipefail

APP="/srv/ai/apps/qwen-code"
LIVE="$APP/lib/qwen-code"
KEEP="$APP/lib/qwen-code.0.24.2"
WRAPPER="$APP/bin/qwen"
FAIL_TREE="$APP/lib/qwen-code.0.24.6-failed"

if [[ ! -d "$KEEP" ]]; then
  printf '%s\n' "ABBRUCH: Keep-Tree fehlt: $KEEP"
  exit 1
fi

systemctl --user stop qwen-code-web.service 2>/dev/null || true

if [[ -d "$LIVE" ]]; then
  if [[ -e "$FAIL_TREE" ]]; then
    rm -rf "$FAIL_TREE"
  fi
  mv "$LIVE" "$FAIL_TREE"
fi
mv "$KEEP" "$LIVE"
got="$("$WRAPPER" --version | tr -d '[:space:]')"
if [[ "$got" != "0.24.2" ]]; then
  printf 'ABBRUCH: nach Rollback Version %s\n' "$got"
  exit 1
fi
printf 'OK   Rollback auf Qwen 0.24.2. Failed tree: %s\n' "$FAIL_TREE"
