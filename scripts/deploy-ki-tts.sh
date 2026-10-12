#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="/srv/ai/apps/ki-tts"
mkdir -p "$DEST"
install -m 755 "$ROOT/apps/ki-tts/server.py" "$DEST/server.py"
echo "Deployed ki-tts -> $DEST (systemd: apps/ki-tts/systemd/ki-tts.service)"
