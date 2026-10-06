# Agent Memory

Projektbezogener persistenter Zustand. Chatverlauf ist kein Speicher.

## Dateien

Im jeweiligen Workspace:

| Datei | Rolle |
|-------|--------|
| `.agent/STATE.md` | kompakter Ist-Zustand |
| `.agent/REQUIREMENTS.md` | stabile Anforderungen |
| `.agent/DECISIONS.md` | append-only Entscheidungen |
| `.agent/TASKS.md` | offene/erledigte Aufgaben |
| `.agent/TOOLS.md` | verfügbare lokale Tools |
| `.agent/history/` | Snapshots vor Updates, nicht in den Prompt laden |

Qwen Managed Auto-Memory (`~/.qwen/projects/...`) bleibt **aus**.

## Ablauf

1. Vor einer relevanten Aufgabe: `mcp__local-tools__memory_load` mit `workspace` = Git- oder Qwen-Workspace.
2. Arbeit ausführen.
3. Danach: `mcp__local-tools__memory_update` mit `summary` plus geänderten Feldern.
4. `decisions` wird immer angehängt. Alte Einträge werden nicht überschrieben. Vorherige Dateien liegen unter `.agent/history/`.

`memory_load` kürzt Dateien (3500 Zeichen/Datei, 14000 gesamt). History liefert nur Dateinamen. `DECISIONS.md` kommt kompakt: die letzten 4 Einträge vollständig, ältere nur als Überschriften. `TASKS.md` behält offene Punkte und zählt erledigte; die volle Liste bleibt auf der Platte. `REQUIREMENTS.md` wird nicht kompaktier. Der Tool-Text sagt: nicht referieren, nach Erfolg sofort das nächste Tool, `memory_update` erst am Ende.

## Grenzen

- Schreibzugriff nur unter erlaubten Roots (`/home/mike/Projects`, `/srv/ai/workspaces`, `/mnt/ai-archive`, Temp).
- MCP-Dienst braucht `ReadWritePaths` auf diese Roots (siehe systemd-Unit).
- Live-MCP auf `:8765` sieht die neuen Tools erst nach `./scripts/deploy-local-tools-mcp.sh`.
- Die unsichtbare QUALITY-Pause nach `pdf_create` war Qwen-Auto-Compact, nicht zu großer Memory-Inhalt. Memory deshalb nicht weiter kürzen. Compact-Schwelle liegt in `~/.qwen/settings.json` (`context.autoCompactThreshold=0.95`, `compactionModel=local-fast`).

## Knowledge Base (getrennt)

Langfristiges Wissen liegt unter `.agent/knowledge/` und wird über `knowledge_search` / `knowledge_get` / `knowledge_record` geladen — nicht über `memory_load`. Details: `docs/KNOWLEDGE_BASE_V2.md`.
