---
name: knowledge-base
description: >
  Long-term project knowledge under .agent/knowledge/. Search before repairs
  and architecture changes. Record decisions, failures, fixes, fallbacks,
  replans, and research. Separate from compact .agent/ memory state.
---

# Knowledge base

Store: `.agent/knowledge/entries.jsonl` (plus `index.json`). Not chat history. Not `.agent/history/`.

Memory (`memory_load` / `memory_update`) = current project state.
Knowledge (`knowledge_*`) = durable lessons: Failure → Fix → Fallback → Replan.

## When to search

Call `mcp__local-tools__knowledge_search` first when:

- an error or regression appears
- a prior approach might already exist
- architecture, model, dependency, or security choices
- replanning the roadmap
- research that should not be repeated

Skip search for trivial single-file edits and routine tool use.

## When to write

Call `mcp__local-tools__knowledge_record` only for lasting facts:

- decision (with reason)
- failure (`do_not_repeat` when the approach must not be retried)
- validated fix (link `fixes` to failure ids)
- fallback
- replan (`supersedes` old decision id)
- research (optional `confidence`: high/medium/low)
- success pattern

Do not store chat fluff, temporary test values, or every tool dump.

## How

1. `knowledge_search` with a short query → read the compact `package`
2. `knowledge_get` only for one id if detail is needed
3. Prefer validated fixes and active decisions; respect `do_not_repeat` and SUPERSEDED
4. After a validated outcome, record with `evidence` paths that actually exist

No Shell. No network. No secrets. Keep packages small.
