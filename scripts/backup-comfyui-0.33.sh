#!/usr/bin/env bash
# Snapshot ComfyUI 0.33.0 tree, unit, freeze, workflow and model hashes.
# Does not copy model weights or the 6 GiB venv (original stays at /srv/ai/venvs/comfyui).
set -euo pipefail

OLD_TREE="/srv/ai/apps/ComfyUI"
OLD_VENV="/srv/ai/venvs/comfyui"
UNIT="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/comfyui.service"
WANT_COMMIT="cc0fc21fea7a6a82f568362b15b7fbd713b419c1"
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW="$REPO_ROOT/apps/ki-workplace/workflows/flux2-klein-t2i-api-v1.json"
ARCHIVE="/mnt/ai-archive"

if ! mountpoint -q "$ARCHIVE"; then
  printf '%s\n' "ABBRUCH: Archiv-HDD ist nicht eingehängt."
  exit 1
fi
if [[ ! -d "$OLD_TREE" || ! -x "$OLD_VENV/bin/python" || ! -f "$UNIT" ]]; then
  printf '%s\n' "ABBRUCH: ComfyUI-Tree, Venv oder Unit fehlt."
  exit 1
fi
got="$(git -C "$OLD_TREE" rev-parse HEAD)"
if [[ "$got" != "$WANT_COMMIT" ]]; then
  printf 'ABBRUCH: Tree-Commit ist %s, erwartet %s.\n' "$got" "$WANT_COMMIT"
  exit 1
fi

stamp="${1:-$(date +%Y%m%d-%H%M%S)}"
dest="$ARCHIVE/backups/comfyui-0.33.0-$stamp"
if [[ -e "$dest" ]]; then
  printf 'ABBRUCH: Backup existiert schon: %s\n' "$dest"
  exit 1
fi
mkdir -p "$dest/tree"

printf '%s\n' "Backup nach $dest"
rsync -a --info=progress2 "$OLD_TREE/" "$dest/tree/"
cp -a "$UNIT" "$dest/comfyui.service"
cp -a "$OLD_TREE/extra_model_paths.yaml" "$dest/extra_model_paths.yaml"
cp -a "$WORKFLOW" "$dest/flux2-klein-t2i-api-v1.json"
cp -a "$REPO_ROOT/apps/ki-workplace/server.py" "$dest/ki-workplace-server.py"
"$OLD_VENV/bin/pip" freeze > "$dest/pip-freeze.txt"
readlink -f "$OLD_VENV" > "$dest/venv.path"
"$OLD_VENV/bin/python" -V > "$dest/python-version.txt"
"$OLD_VENV/bin/python" - <<'PY' > "$dest/torch.txt"
import torch
print("torch", torch.__version__)
print("cuda", torch.version.cuda)
print("avail", torch.cuda.is_available())
PY

{
  echo "diffusion_model $(sha256sum /srv/ai/models/comfyui/diffusion_models/flux-2-klein-4b-fp8.safetensors)"
  echo "text_encoder $(sha256sum /srv/ai/models/comfyui/text_encoders/qwen_3_4b.safetensors)"
  echo "vae $(sha256sum /srv/ai/models/comfyui/vae/flux2-vae.safetensors)"
} > "$dest/model-hashes.txt"

{
  echo "git_head $(git -C "$REPO_ROOT" rev-parse --short HEAD)"
  echo "comfy_commit $got"
  echo "unit_sha $(sha256sum "$UNIT")"
  echo "workflow_file_sha $(sha256sum "$WORKFLOW")"
  echo "venv $OLD_VENV"
  echo "enabled $(systemctl --user is-enabled comfyui.service 2>/dev/null || true)"
  echo "active $(systemctl --user is-active comfyui.service 2>/dev/null || true)"
  echo "ollama $(systemctl is-active ollama 2>/dev/null || true)"
  echo "workplace $(systemctl --user is-active ki-workplace.service 2>/dev/null || true)"
  echo "mcp $(systemctl --user is-active local-tools-mcp.service 2>/dev/null || true)"
  echo "qwen $(systemctl --user is-active qwen-code-web.service 2>/dev/null || true)"
} > "$dest/services.txt"

cat > "$dest/ROLLBACK.txt" <<EOF
Restore ComfyUI 0.33.0 without touching model weights:

  $REPO_ROOT/scripts/rollback-comfyui-0.33.0.sh $dest

Keeps /srv/ai/apps/ComfyUI and /srv/ai/venvs/comfyui in place.
Restores only the systemd unit from this backup.
Does not delete /srv/ai/apps/ComfyUI-0.37.0.
EOF

printf 'OK   %s\n' "$dest"
printf '%s\n' "$dest"
