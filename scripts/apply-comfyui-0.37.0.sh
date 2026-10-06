#!/usr/bin/env bash
# Point the disabled comfyui.service at the isolated 0.37.0 tree. Does not enable autostart.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
NEW_TREE="/srv/ai/apps/ComfyUI-0.37.0"
OLD_OUTPUT="/srv/ai/apps/ComfyUI/output"
UNIT="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/comfyui.service"
WANT_COMMIT="73c9bad4d21e7addbe1d13bc92eee0f1431b017d"
MARKER="$NEW_TREE/.isolated-flux-pass.json"
VENV_033="/srv/ai/venvs/comfyui"
VENV_037="/srv/ai/venvs/comfyui-0.37"

if [[ ! -d "$NEW_TREE" || "$(git -C "$NEW_TREE" rev-parse HEAD)" != "$WANT_COMMIT" ]]; then
  printf '%s\n' "ABBRUCH: Isolierter 0.37.0-Tree fehlt oder Commit stimmt nicht."
  exit 1
fi
if [[ ! -f "$MARKER" && "${1:-}" != "--force-cutover" ]]; then
  printf '%s\n' "ABBRUCH: Isolierte FLUX-Regression fehlt ($MARKER). Erst Test, dann Cutover."
  exit 1
fi

python_bin="$VENV_033/bin/python"
if [[ -x "$VENV_037/bin/python" ]]; then
  python_bin="$VENV_037/bin/python"
fi
if [[ ! -x "$python_bin" ]]; then
  printf '%s\n' "ABBRUCH: Python für 0.37.0 fehlt."
  exit 1
fi

torch="$("$python_bin" -c 'import torch; print(torch.__version__)')"
if [[ "$torch" != "2.13.0+cu130" ]]; then
  printf 'ABBRUCH: Torch ist %s, erwartet 2.13.0+cu130.\n' "$torch"
  exit 1
fi

systemctl --user stop comfyui.service 2>/dev/null || true
cp -a "$UNIT" "$UNIT.bak-before-0.37.0"
cat > "$UNIT" <<EOF
[Unit]
Description=Local ComfyUI 0.37.0
Documentation=file://$REPO_ROOT/docs/COMFYUI_0_37_UPGRADE.md
After=network.target
StartLimitIntervalSec=180
StartLimitBurst=12

[Service]
Type=simple
WorkingDirectory=$NEW_TREE
Environment=HF_HOME=/srv/ai/cache/huggingface
ExecStartPre=/bin/bash -c 'for i in \$(seq 1 30); do [ -e /dev/nvidia0 ] && exit 0; sleep 1; done; exit 0'
ExecStart=$python_bin main.py --listen 127.0.0.1 --port 8188 --output-directory $OLD_OUTPUT
Restart=on-failure
RestartSec=8

[Install]
WantedBy=default.target graphical-session.target
EOF

systemctl --user daemon-reload
# Autostart stays off.
systemctl --user disable comfyui.service >/dev/null 2>&1 || true
if ! grep -q 'WorkingDirectory=/srv/ai/apps/ComfyUI-0.37.0' "$UNIT"; then
  printf '%s\n' "ABBRUCH: Unit-WorkingDirectory nach Schreiben falsch."
  exit 1
fi
if ! grep -q -- '--listen 127.0.0.1 --port 8188' "$UNIT"; then
  printf '%s\n' "ABBRUCH: localhost:8188 fehlt in ExecStart."
  exit 1
fi
printf 'OK   Cutover Unit -> %s python=%s torch=%s\n' "$NEW_TREE" "$python_bin" "$torch"
systemctl --user is-enabled comfyui.service || true
