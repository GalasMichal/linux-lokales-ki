---
name: agent-memory
description: >
  Persistent project memory under .agent/. Use at the start of every relevant
  task and after finishing work. Load STATE, TASKS, DECISIONS. Do not rely on
  chat history. Updates STATE/TASKS and appends DECISIONS.
---

# Agent memory

Source of truth is the workspace `.agent/` directory, not the chat transcript and not `~/.qwen/projects/`.

Required files:

- `.agent/STATE.md`
- `.agent/REQUIREMENTS.md`
- `.agent/DECISIONS.md`
- `.agent/TASKS.md`
- `.agent/TOOLS.md`
- `.agent/history/` (audit snapshots, do not load into the prompt)

## Before a task

Call `mcp__local-tools__memory_load` with `workspace` set to the Git/Qwen workspace root. If MCP is down, read the five markdown files with `read_file`. Keep the loaded text compact; do not open history files unless you are auditing.

## After a task

Call `mcp__local-tools__memory_update` with a short `summary` plus the fields that changed:

- `state` and `tasks` replace those files
- `decisions` **appends** a dated entry; never rewrite old decisions
- optional `requirements` / `tools`

## Rules

- Chat history is a hint, not memory
- Do not paste long logs into STATE.md
- Do not delete previous DECISIONS entries
- Do not treat `~/.qwen/projects/...` as a project path
