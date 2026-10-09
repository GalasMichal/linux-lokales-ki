# Cursor / Qwen agent handoff (mg-games)

Local agents on **Vollstrecker** that start from this repo (`Linux Lokales KI`) or from **Qwen Code** here should know where game workflows live and how release discipline works.

**mg-games** spans the private **kinder-spiele** app repo and the **mg-games** website/umbrella work. Coordinators use the Cursor **Project store** for edits; **git** is what Cloud and Qwen see. For the Kinder-Spiele app, the committed agent index is canonical on GitHub: [kinder-spiele `docs/agent/AGENT-CONTEXT.md`](https://github.com/GalasMichal/kinder-spiele/blob/master/docs/agent/AGENT-CONTEXT.md). Read that first for visual gates, preferences, and Cloud vs self-hosted capabilities.

**Process (short):** Implement → dedicated **visual-review** agent (A–Z) must **PASS** before you call the work done or ping Mike ([release-approval-gate.md](./release-approval-gate.md), [visual-review-gate on GitHub](https://github.com/GalasMichal/kinder-spiele/blob/master/docs/agent/visual-review-gate.md)). Routine `git pull` / merge / CI-style checks are for agents on Vollstrecker; **release/sign-off pushes** (telling Mike “ready to ship”, Play-bound version bumps, or pushing when he asked to wait) only after **Mike OK**. Do not shorten his constraint lists when delegating.

## Files in this folder

| File | Role |
|------|------|
| [release-approval-gate.md](./release-approval-gate.md) | Review PASS → then Mike OK for release messaging / guarded pushes |
| [plan-local-codic-delegation.md](./plan-local-codic-delegation.md) | Stub: Cloud coordinator + Qwen Code on this machine |
| [cloud-sync-maintain.md](./cloud-sync-maintain.md) | Stub: store → `kinder-spiele/docs/agent/` sync |

## Qwen Code from this repo

- Entry doc: [`QWEN.md`](../../QWEN.md) (repo root)
- Binary (reference PC): `/srv/ai/apps/qwen-code/bin/qwen`
- Subagents: `.qwen/agents/` (researcher, architect, reviewer)

## Related (stack, not game UI)

- [`docs/KI_ARBEITSPLATZ.md`](../KI_ARBEITSPLATZ.md) — ports, GPU sharing
- [`docs/DESKTOP_AGENT.md`](../DESKTOP_AGENT.md) — desktop automation
- Game media rule in app repo: [`.cursor/rules/lokaler-stack-medien.mdc`](https://github.com/GalasMichal/kinder-spiele/blob/master/.cursor/rules/lokaler-stack-medien.mdc)
