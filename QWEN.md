# Qwen Code — this repository

Project skills live under `skills/` and are linked into `.qwen/skills/` by `scripts/setup-qwen-skills.sh`.

User-level skills (`~/.qwen/skills`, `~/.agents/skills`) are disabled in this workspace so Cursor/Codex skills are not loaded. Bundled Qwen skills remain available.

Local models (do not retune Ollama here):

- Default / FAST: `local-fast` (`qwen3.5:9b`, 16K)
- QUALITY: `local-quality` (`qwen3.6:27b`, 8K) — only with `-m local-quality`

See `docs/QWEN_SKILLS.md`.
