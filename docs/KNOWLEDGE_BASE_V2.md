# Knowledge Base v2

Stand: 22.09.2026. Ergebnis: **PASS** (Compact-Regression mit bekannter Limitation).

Persistentes Erfahrungswissen für den lokalen Agenten. Getrennt vom kompakten `.agent/`-Zustand (STATE/TASKS/…). Ziel: vor Reparaturen und Architekturentscheidungen gezielt abrufen, was schon scheiterte oder funktionierte.

## Architektur

```text
.agent/knowledge/entries.jsonl   # eine JSON-Zeile pro Eintrag
.agent/knowledge/index.json      # id/topic Index, neu gebaut bei Schreibvorgängen
```

Kein Vector-DB. Kein Netz. Keine Home-Indexierung. Nur Workspace unter erlaubten Roots.

Memory bleibt:

| API | Rolle |
|-----|--------|
| `memory_load` / `memory_update` | aktueller Projektzustand |
| `knowledge_search` / `knowledge_get` / `knowledge_record` | langfristiges Wissen |

## Typen

`decision` · `failure` · `fix` · `fallback` · `replan` · `research` · `success`

Status: `active` · `superseded` · `failed` · `validated` · `deprecated`

IDs: `KB-YYYYMMDD-TOPIC-NNN` (deterministisch, menschenlesbar). Seed-IDs z. B. `KB-20260922-LEDGER-002`.

## Relations / Supersede / Dedupe

- `relations.fixes`, `relations.fallback_for`, `relations.relates_to`
- `supersedes` + Ziel wird `status=superseded` mit `superseded_by`
- Identischer Fingerprint (`type|topic|summary`) → Evidence mergen, keine neue ID (`force_new=true` überschreibt)

## Retrieval

Keyword-/Topic-Ranking (kein Embedding):

1. Topic-/Keyword-Treffer
2. bekannte Phrasen (17216, ledger, systemd, …)
3. Status-Gewicht (`validated`/`active` vor `superseded`)
4. Relation-Nachzug angrenzender IDs
5. kompaktes `package` (Default `max_results=5`)

Tokenziel: typisch **300–800**, hart ≤ **1500**. Slim-Hits in der Tool-Antwort (Details nur via `knowledge_get`).

## MCP

- Version **1.6.0**, **32 Tools** (vorher 1.5.0 / 29)
- Neu: `knowledge_search`, `knowledge_get`, `knowledge_record`
- Lazy: `alwaysLoadTools=false`, alle Namen in `includeTools`
- Skill: `skills/knowledge-base/` → `.qwen/skills/knowledge-base`

## Migration (Provenance)

18 kuratierte Einträge aus Repo-Docs, u. a.:

| ID | Inhalt | Quelle |
|----|--------|--------|
| `KB-20260922-COMPACT-001/002` | 0.85→0.95 Compact | `docs/QWEN_COMPACT_CONTINUITY.md` |
| `KB-20260922-COMPACT-003` | Prompt-only FAIL | dieselbe |
| `KB-20260922-LAZY-001/002` | 17216 / Lazy Tools | `docs/QWEN_LAZY_TOOL_LOADING.md` |
| `KB-20260922-LEDGER-001..004` | 16231 / State Ledger PASS / Stock-Prompt-Fallback | `docs/QWEN_COMPACT_STATE_LEDGER.md` |
| `KB-20260922-BOOT-001/002` | systemd-Zyklus | `docs/ACCEPTANCE_A01_A14.md` |
| `KB-20260921-ROADMAP-000/001` | Desktop→1536 superseded | `docs/MASTER_PLAN.md` |
| Image-/ToolSearch-Einträge | Originalbild, 1024-Cap, ToolSearch, Git-omit | Handoff / ToolSearch-Docs |

## Tests / Belege

| Test | Ergebnis |
|------|----------|
| Unit `tests/test_knowledge_base.py` | 11 OK |
| Retrieval-Suite | avg **324.5** Tokens, max **448**, inkl. no-hit |
| FAST E2E | PASS Session `0716174d…` |
| QUALITY E2E | PASS Session `4f20170c…` |
| Compact+KB Kern | PASS Session `90ce6e13…` — Compact + Ledger, Folgeprompt max **13231**, kein sofortiger 2. Compact |
| Compact+KB Vollkette | Limitation: `memory_update` einmal übersprungen / später Duplikate bei längerem Drift |

Belege: `benchmarks/knowledge-base-20260922/`.

## Security

Unverändert: `trust: false`, `approvalMode: default`, kein YOLO, localhost only, keine Secrets in Queries/Records, keine Shell, keine URL-Fetches.

## Backup / Rollback

- Phasen-Backup: `/mnt/ai-archive/backups/knowledge-base-v2-20260922-121004`
- MCP-Deploy-Backup: `/mnt/ai-archive/backups/local-tools-mcp/20260922-121004`
- Rollback MCP: `…/rollback-local-tools-mcp.sh` (stellt 1.5.0 wieder her; `.agent/knowledge/` bleibt auf Disk)

Compact State Ledger und Lazy Tools bleiben davon unberührt.

## Nicht in dieser Phase

Kein Supervisor. Kein 24K/32K-Cutover. Kein 1536. Keine Game-Pipeline.
