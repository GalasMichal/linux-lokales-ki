#!/usr/bin/env bash
# Download and inspect the official MCP SDK wheels. This script installs nothing.
set -euo pipefail

DESTINATION="${1:-/srv/ai/cache/pip/local-tools-mcp-2.0.0}"

install -d -m 0755 "$DESTINATION"
python3 -m pip download \
  --disable-pip-version-check \
  --only-binary=:all: \
  --dest "$DESTINATION" \
  "mcp==2.0.0"

(
  cd "$DESTINATION"
  sha256sum ./*.whl | sort -k2 > SHA256SUMS
)

MCP_WHEEL="$(find "$DESTINATION" -maxdepth 1 -type f -name 'mcp-2.0.0-*.whl' -print -quit)"
if [[ -z "$MCP_WHEEL" ]]; then
  printf '%s\n' "ABBRUCH: Das erwartete mcp-2.0.0-Wheel fehlt."
  exit 1
fi

printf '%s\n' "--- Offizielle Paket-Metadaten ---"
unzip -p "$MCP_WHEEL" 'mcp-2.0.0.dist-info/METADATA' \
  | sed -n -E '/^(Metadata-Version|Name|Version|Summary|License-Expression|Requires-Python|Project-URL|Requires-Dist):/p'
printf '%s\n' "--- Wheel-Inhalt (erste 80 Einträge) ---"
unzip -l "$MCP_WHEEL" | sed -n '1,86p'
printf '%s\n' "--- SHA-256 ---"
sed -n '1,240p' "$DESTINATION/SHA256SUMS"
printf 'DOWNLOAD_OK=%s\n' "$DESTINATION"
