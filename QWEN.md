# Qwen Code — this repository

Workspace root is `/home/mike/Projects/Linux Lokales KI`. All relative repo paths resolve against the current Git workspace.

Never treat `~/.qwen/projects/...` memory storage as a project source path. Spaces in the workspace path are real; do not rewrite them to hyphens. Git branch names are not filesystem paths.

Default model: FAST `local-fast` (32K). QUALITY only with `-m local-quality` (8K). Do not change Ollama beyond the documented FAST 32K alias.

For coding tasks: execute the user's current request. Change only the files the user named. Do not scaffold new package trees. Read a target file before modifying it. After edits run relevant tests, inspect the diff, then call the skill tool with skill=verify-work. Do not skip that skill call. Do not invent commit or push work.

Coding, tests, and refactors are not image requests. Call `mcp__local-tools__generate_image` only when the user asked to create an image.

Image generation uses `mcp__local-tools__generate_image`.

Project skills: `skills/` → `.qwen/skills/` (`scripts/setup-qwen-skills.sh`). User-level skills are off here. See `docs/QWEN_SKILLS.md`.
