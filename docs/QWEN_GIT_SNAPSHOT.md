# Qwen Git-Snapshot Patch

Gilt nur für **Qwen Code 0.21.15**. Teil von `scripts/apply-qwen-toolsearch-mcp-alias-patch.sh`.

## Warum

`getRecentGitStatus()` hängt Git-Status, Dateiliste und Commits in den Systemprompt. local-fast nimmt das als aktuelle Aufgabe.

Nach FAST 32K bleibt der Omit-Patch: der Coding-E2E nutzt `git diff`/`git status` selbst, und ein injizierter Dirty-Tree hat zuvor Tasks gekapert. Weniger Core-Patches sind das Ziel; ToolSearch/Registry bleiben getrennt.

Bewiesen:

1. Volle Dateiliste → „what would you like to do with these modifications?“
2. Nur Branch `codex/ki-arbeitsplatz` → Shell-Pfad `codex/ki-arbeitsplatz/codex/tools/...`

## Was der Patch tut

`getRecentGitStatus()` gibt sofort `null` zurück. Kein Git-Block im Systemprompt.

Marker: `linux-lokales-ki-omit-git-snapshot`

Ziel: `/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-L7RG5PVT.js`

## Anwenden / Rollback

Wie `docs/QWEN_TOOLSEARCH_MCP_ALIAS.md`. Rollback stellt **Stock** wieder her.
