# State

- Project: Linux Lokales KI
- Phase: Runtime-Update 02.10.2026 **PASS**; Context-Probe additiv **PASS** (kein Cutover)
- Runtime (live 2026-10-02): Ollama **0.35.0**, Qwen Code **0.24.7** + ToolSearch/Registry/Git + Compact-State-Ledger, MCP **1.7.0** (33 Tools inkl. `moe_consult`), Open WebUI **0.11.0**, ComfyUI **0.38.0** (`--disable-comfy-compiler`)
- Supervisor: Named Agents `researcher` / `architect` / `reviewer`; `maxSubagentDepth=1`; Agent Team aus; Writer SKIP
- Serve: `/srv/ai/workspaces/.qwen/agents` → Repo `.qwen/agents`
- Knowledge: `.agent/knowledge/` JSONL, lazy `knowledge_*`
- Compact: Schwelle 0.95, Modell `local-fast`. Lazy Schemata. Ledger bleibt
- FAST: `local-fast` (Default). QUALITY: `local-quality` **16384** (Architecture/Review)
- Additive Bench: `bench-qwen38-27b-{16,24,32}k` — Probe ohne schwere Artefakte; produktiv unverändert
- `trust: false`, `approvalMode: default`, kein YOLO, Computer Use aus
- Backup: `/mnt/ai-archive/backups/runtime-update-20261002-084919`
- Bericht: `docs/RUNTIME_UPDATE_2026-10-02.md`
- Last update: 2026-10-02T09:07Z
- Next: Serve/Agent-E2E für QUALITY 24K/32K planen — kein automatischer Cutover
