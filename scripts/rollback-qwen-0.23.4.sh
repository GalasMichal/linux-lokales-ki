#!/usr/bin/env bash
# Restore Qwen Code 0.23.4 from the sibling tree left by upgrade-qwen-0.24.2.sh.
# Keeps Ollama as-is.
set -euo pipefail

APP="/srv/ai/apps/qwen-code"
LIVE="$APP/lib/qwen-code"
KEEP="$APP/lib/qwen-code.0.23.4"
FAILED="$APP/lib/qwen-code.0.24.2.failed"
WRAPPER="$APP/bin/qwen"

if [[ ! -d "$KEEP" ]]; then
  printf '%s\n' "ABBRUCH: 0.23.4-Tree fehlt: $KEEP"
  exit 1
fi

systemctl --user stop qwen-code-web.service 2>/dev/null || true

if [[ -d "$LIVE" ]]; then
  rm -rf "$FAILED"
  mv "$LIVE" "$FAILED"
fi
mv "$KEEP" "$LIVE"
got="$("$WRAPPER" --version | tr -d '[:space:]')"
if [[ "$got" != "0.23.4" ]]; then
  printf 'ABBRUCH: Nach Rollback ist Version %s.\n' "$got"
  exit 1
fi
printf 'OK   Qwen %s wieder aktiv. 0.24.2 liegt unter %s\n' "$got" "$FAILED"
