# State

- Project: Linux Lokales KI
- Phase: Stand 12.10.2026. Kein offener Kontext-Cutover.
- Runtime: Ollama **0.35.1**, Qwen Code **0.24.7**, MCP **1.8.0** (34 Tools), Open WebUI **0.11.4**, ComfyUI **0.38.0**, Piper **8792**
- Supervisor: Named Agents `researcher` / `architect` / `reviewer`; `maxSubagentDepth=1`; Agent Team aus; Writer SKIP
- Serve: `/srv/ai/workspaces/.qwen/agents` → Repo `.qwen/agents`
- Knowledge: `.agent/knowledge/` JSONL, lazy `knowledge_*`
- Compact: Schwelle 0.95, Modell `local-fast`. Lazy Schemata. Ledger bleibt
- FAST: `local-fast` (Default, 32768). QUALITY: `local-quality` **65536** (Architektur, Review, Vision)
- Bench-Aliase bleiben Messmodelle. Produktiv sind nur `local-fast` und `local-quality`.
- `trust: false`, `approvalMode: default`, kein YOLO, Computer Use aus
- Backup: `/mnt/ai-archive/backups/runtime-update-20261002-084919`
- Bericht: `docs/RUNTIME_UPDATE_2026-10-02.md`
- Last update: 2026-10-12
- Next: kein Modell-Cutover. Gemma-4-Vergleich bleibt geparkt.
