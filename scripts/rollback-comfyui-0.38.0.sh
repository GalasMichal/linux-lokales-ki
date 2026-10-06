#!/usr/bin/env bash
# Rollback productive ComfyUI 0.38.0 -> 0.37.0 unit + workplace input path.
set -euo pipefail
UNIT="$HOME/.config/systemd/user/comfyui.service"
WP_LIVE="/srv/ai/apps/ki-workplace/server.py"
WP_REPO="/home/mike/Projects/Linux Lokales KI/apps/ki-workplace/server.py"

systemctl --user stop comfyui.service 2>/dev/null || true
cat > "$UNIT" <<'UNIT'
[Unit]
Description=Local ComfyUI 0.37.0
Documentation=file:///home/mike/Projects/Linux Lokales KI/docs/COMFYUI_0_37_UPGRADE.md
After=network.target
StartLimitIntervalSec=180
StartLimitBurst=12

[Service]
Type=simple
WorkingDirectory=/srv/ai/apps/ComfyUI-0.37.0
Environment=HF_HOME=/srv/ai/cache/huggingface
ExecStartPre=/bin/bash -c 'for i in $(seq 1 30); do [ -e /dev/nvidia0 ] && exit 0; sleep 1; done; exit 0'
ExecStart=/srv/ai/venvs/comfyui-0.37/bin/python main.py --listen 127.0.0.1 --port 8188 --output-directory /srv/ai/apps/ComfyUI/output
Restart=on-failure
RestartSec=8

[Install]
WantedBy=default.target graphical-session.target
UNIT
systemctl --user daemon-reload
for f in "$WP_LIVE" "$WP_REPO"; do
  if [[ -f "$f" ]]; then
    sed -i 's|/srv/ai/apps/ComfyUI-0.38.0/input|/srv/ai/apps/ComfyUI-0.37.0/input|' "$f"
  fi
done
systemctl --user restart ki-workplace.service
printf 'OK Rollback ComfyUI unit -> 0.37.0; COMFY_INPUT -> 0.37.0/input\n'
