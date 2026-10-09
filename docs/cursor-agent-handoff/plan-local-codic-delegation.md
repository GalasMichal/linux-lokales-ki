# Plan B: Cloud coordinator + local Codic (stub)

Full plan (scripts, roles, `package.json` QA matrix) lives in the **mg-games Project store** — not duplicated here:

`~/.local/state/cursor/agent-stores/cursor_agent_stores/bc-14f20dd9-1542-4bde-8e43-68e0efb28c2f/files/docs/plan-local-codic-delegation.md`

## Summary

| Role | Where | Does |
|------|--------|------|
| **Cloud Project coordinator** | Cursor Cloud (mg-games) | Plan, delegate, PR text; no ComfyUI/emulator on generic VM |
| **Self-hosted Cursor worker** | Vollstrecker | Same as today: repo edits, visual QA, `127.0.0.1` media |
| **Qwen Code (“Codic”)** | This repo (`Linux Lokales KI`) | Terminal supervisor: `kinder-spiele` npm/android tools, MCP `local-tools` |

**Repos:** App [`GalasMichal/kinder-spiele`](https://github.com/GalasMichal/kinder-spiele); website/umbrella separate under `~/Projects/mg-games`. Agent workflows for the app: [`docs/agent/`](https://github.com/GalasMichal/kinder-spiele/tree/master/docs/agent) on GitHub.

**Qwen:** [`QWEN.md`](../../QWEN.md), `.qwen/agents/`, PATH for Node per plan. Before UI work: store workflows `visual-review-gate.md` / `visual-review-az.md` (mirrored in kinder-spiele `docs/agent/`).
