# Qwen Git-Snapshot Patch

Gilt für **Qwen Code 0.24.2**. Teil von `scripts/apply-qwen-toolsearch-mcp-alias-patch.sh`.
Ältere Varianten: `patches/qwen-code/0.23.4/` und `0.21.15/`.

## Warum

`getRecentGitStatus()` hängt Git-Status, Dateiliste und Commits in den Systemprompt. local-fast nimmt das als aktuelle Aufgabe. In 0.24.2 liegt die Funktion in `chunk-IOISNXQ2.js`. Stock injiziert den Snapshot weiterhin.

## Was der Patch tut

`getRecentGitStatus()` gibt sofort `null` zurück. Kein Git-Block im Systemprompt.

Marker: `linux-lokales-ki-omit-git-snapshot`

Ziel 0.24.2: `/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-IOISNXQ2.js`

## Anwenden / Rollback

Wie `docs/QWEN_TOOLSEARCH_MCP_ALIAS.md`. Rollback stellt **Stock** der installierten Version wieder her.
