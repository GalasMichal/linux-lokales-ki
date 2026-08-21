---
name: local-ai-stack
description: >
  Local Linux AI stack on this machine: Ollama FAST/QUALITY, Qwen Code, ComfyUI,
  Open WebUI, localhost-only binds. Use for stack paths, GPU sequencing,
  model roles, and what this repo must not change.
---

# Local AI stack

This skill is for the Git repo that documents `/srv/ai`. Do not retune Ollama from here.

## Roles (names only)

| Role | Ollama name | Alias | Context in Qwen | Use |
|------|-------------|-------|-----------------|-----|
| FAST | `qwen3.5:9b` | `local-fast` | 16K | normal coding, small edits, file analysis |
| QUALITY | `qwen3.6:27b` | `local-quality` | 8K | architecture, hard bugs, larger refactors |

Do not download models, change quant, change context, or load both models at once.

## Endpoints (localhost only)

- Ollama: `http://127.0.0.1:11434`
- Qwen Code CLI: `/srv/ai/apps/qwen-code/bin/qwen`
- Do not bind services to LAN.

## Agent safety

- Work in a Git branch or worktree
- Do not use `--yolo`
- Do not overwrite `~/.qwen/settings.json` unless the user explicitly asks
- Do not change `/etc/systemd/system/ollama.service.d/override.conf`

## GPU

16 GB VRAM. One loaded Ollama model. Unload Ollama before ComfyUI image jobs.

## Out of scope for this skill

Cursor model routing, Cursor tools, Codex product skills, cloud providers.
