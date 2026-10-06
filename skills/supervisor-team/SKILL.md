---
name: supervisor-team
description: >
  Native Qwen Code 0.24.2 supervisor with project agents researcher, architect,
  and reviewer. Use when delegating research, architecture, or review. Not for
  trivial single-file reads.
---

# Supervisor team

Project agents (`.qwen/agents/`):

| Agent | Model | Role |
|-------|--------|------|
| `researcher` | local-fast | Knowledge + docs (+ optional browser). Read-only |
| `architect` | local-quality | Design/tradeoffs. Read-only. No browser |
| `reviewer` | local-quality | Risks, KB failures, security, acceptance. Read-only |

## Delegate when

- Multi-source research
- Architecture / platform-neutral planning
- Independent review of a plan
- Known regression / failure lookup needs depth

## Do not delegate when

- One file read, Git HEAD, trivial rename, single clear tool call

## CPU MoE second opinion (`moe_consult`)

- On-demand only (no systemd, no permanent load). Main agent stays `local-fast`.
- Architect/reviewer MAY call `mcp__local-tools__moe_consult` for complex architecture,
  large reviews, multi-cause debugging, security/regression review, ticket breakdown.
- Do NOT call MoE for trivial renames, one-line fixes, CSS tweaks, simple file ops.
- MoE answer is advisory — verify against code/tests; never treat as authority.
- Researcher normally skips MoE.

## Always

1. `knowledge_search` before inventing repairs
2. `agent` args must include non-empty `description`, `prompt`, and named `subagent_type`
3. `run_in_background: false` when the current turn needs the result
4. No nested agents
5. No shell, no YOLO, desktop/images supervisor-only
6. One browser owner (`researcher` only)
7. Never omit `subagent_type` (general-purpose bypasses allowlists)

Details: `docs/SUPERVISOR_MULTI_AGENT.md`.
