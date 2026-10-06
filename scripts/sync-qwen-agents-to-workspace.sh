#!/usr/bin/env bash
# Link project .qwen/agents into the Qwen serve workspace root.
set -euo pipefail
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="/srv/ai/workspaces/.qwen/agents"
mkdir -p /srv/ai/workspaces/.qwen
ln -sfn "$REPO/.qwen/agents" "$TARGET"
printf 'OK %s -> %s\n' "$TARGET" "$(readlink -f "$TARGET")"
