# ComfyUI 0.38.0 Upgrade

Stand: 2026-10-02. Offizielle Stable `v0.38.0` (nicht Pre-Release).

## Cutover

- Tree: `/srv/ai/apps/ComfyUI-0.38.0` (Tag `v0.38.0`)
- Venv: `/srv/ai/venvs/comfyui-0.38` (Torch 2.13.0+cu130)
- Unit: `~/.config/systemd/user/comfyui.service` → WorkingDirectory 0.38.0, Port `8188`
- **Pflicht-Flag:** `--disable-comfy-compiler`
  - Ohne Flag: Qwen-Image-2.1 Edit scheitert mit `aimdo memory compile error`
  - Mit Flag: Edit 512 PASS (~35 s isoliert)
- Output bleibt `/srv/ai/apps/ComfyUI/output`
- Modelle/Workflows unverändert

## Workplace

`COMFY_INPUT` muss `/srv/ai/apps/ComfyUI-0.38.0/input` sein (nicht 0.37.0), sonst findet `LoadImage` staged Edit-Dateien nicht.

## Rollback

1. Unit auf 0.37.0 zurück:
   - WorkingDirectory `/srv/ai/apps/ComfyUI-0.37.0`
   - ExecStart `/srv/ai/venvs/comfyui-0.37/bin/python main.py --listen 127.0.0.1 --port 8188 --output-directory /srv/ai/apps/ComfyUI/output`
2. `COMFY_INPUT` in ki-workplace wieder auf `ComfyUI-0.37.0/input`
3. `systemctl --user daemon-reload && systemctl --user restart ki-workplace`
4. Backup der 0.37-Unit: `/mnt/ai-archive/backups/runtime-update-20261002-084919/comfyui/`

## Tests

| Test | Ergebnis |
|------|----------|
| Isoliert FLUX 512 | PASS ~35 s, Peak ~13600 MiB |
| Isoliert Edit 512 ohne Compiler-Flag | FAIL aimdo |
| Isoliert Edit 512 mit `--disable-comfy-compiler` | PASS ~35 s |
| MCP `generate_image` 512 | PASS ~60 s inkl. Cleanup |
| MCP `edit_image` 512 nach Input-Pfad-Fix | PASS |
