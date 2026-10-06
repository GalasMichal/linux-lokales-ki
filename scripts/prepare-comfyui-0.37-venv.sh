#!/usr/bin/env bash
# Copy the 0.33 venv and install only 0.37.0 requirement bumps. Never mutates /srv/ai/venvs/comfyui.
# Does not upgrade torch.
set -euo pipefail

SRC="/srv/ai/venvs/comfyui"
DST="/srv/ai/venvs/comfyui-0.37"
NEW_TREE="/srv/ai/apps/ComfyUI-0.37.0"

if [[ ! -x "$SRC/bin/python" ]]; then
  printf '%s\n' "ABBRUCH: Quell-Venv fehlt."
  exit 1
fi
if [[ -x "$DST/bin/python" ]]; then
  torch="$("$DST/bin/python" -c 'import torch; print(torch.__version__)')"
  if [[ "$torch" != "2.13.0+cu130" ]]; then
    printf 'ABBRUCH: %s hat Torch %s.\n' "$DST" "$torch"
    exit 1
  fi
  printf 'OK   Venv existiert schon: %s torch=%s\n' "$DST" "$torch"
  exit 0
fi

printf '%s\n' "Kopiere Venv $SRC -> $DST (Torch bleibt 2.13.0+cu130)"
cp -a "$SRC" "$DST"
# Copied scripts keep the 0.33 shebang. Rewrite before any pip install.
find "$DST/bin" -type f -exec grep -l '/srv/ai/venvs/comfyui/bin/python' {} + | while read -r file; do
  sed -i 's|/srv/ai/venvs/comfyui/bin/python|/srv/ai/venvs/comfyui-0.37/bin/python|g' "$file"
done
"$DST/bin/python" -c 'import sys; assert sys.prefix == "/srv/ai/venvs/comfyui-0.37", sys.prefix'
"$DST/bin/python" -c 'import torch; assert torch.__version__ == "2.13.0+cu130", torch.__version__'
"$DST/bin/python" -m pip install --upgrade \
  "comfyui-frontend-package==1.52.7" \
  "comfyui-workflow-templates==0.11.66" \
  "comfyui-embedded-docs==0.5.12" \
  "comfy-kitchen==0.2.35" \
  "comfy-aimdo==0.5.5"
torch="$("$DST/bin/python" -c 'import torch; print(torch.__version__)')"
if [[ "$torch" != "2.13.0+cu130" ]]; then
  printf 'ABBRUCH: Torch nach pip ist %s. Venv nicht verwenden.\n' "$torch"
  exit 1
fi
"$DST/bin/pip" freeze > "$NEW_TREE/pip-freeze-0.37.txt"
printf 'OK   %s torch=%s\n' "$DST" "$torch"
