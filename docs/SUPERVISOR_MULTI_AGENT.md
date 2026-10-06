# Supervisor / Multi-Agent (Qwen Code 0.24.2)

Stand: 22.09.2026. **PASS** (kontrollierte v1).

Erste Version eines lokalen Supervisor-Teams auf **nativen** Qwen-0.24.2-Subagents. Kein eigenes Orchestrierungsframework. Kein Cloud. Kein neuer Qwen-Runtime-Patch in dieser Phase. MCP unverändert **1.6.0 / 32 Tools**.

## Native Feature-Inventar (installiert 0.24.2)

| Feature | Vorhanden? |
|---------|------------|
| `agent` Tool | ja (war disabled; wieder freigeschaltet) |
| `.qwen/agents/` Named Agents | ja |
| custom named agents | ja (`researcher`, `architect`, `reviewer`) |
| Model Override (`model:`) | ja |
| Tool Allowlist / `disallowedTools` | ja |
| Background Agents | ja (`run_in_background`) |
| `list_agents` | ja (freigeschaltet) |
| `send_message` | ja (freigeschaltet) |
| Fork / `fork_turns` / `fork_tools` | ja (Parameter) |
| Worktree Isolation (`isolation: worktree`) | ja (Parameter; Writer in v1 **SKIP**) |
| Agent Team / `experimental.agentTeam` | ja, experimentell — **produktiv aus** |
| `/coordinate` | ja (bundled skill; Team nur wenn Flag an) |
| Shared Task List | nur mit Agent Team |
| `model.maxSubagentDepth` | ja (produktiv **1**) |

### Named Subagents vs Agent Team

| | Named Subagents (gewählt) | Agent Team |
|--|---------------------------|------------|
| Stabilität | bekannte Allowlists + Contexts | experimentell |
| Context | Supervisor sieht Resultat, nicht volle Historie | Shared Task List / Messaging |
| Modellrouting | per Agent-Frontmatter | Team-Leader/Worker |
| Security | `tools` / `disallowedTools` | Team-Policies unklar |
| Worktree | optional pro Agent-Call | Team-Worktrees |
| Continuity | einzeln, Ledger bleibt | ungetestet produktiv |
| Knowledge | in Agent-Prompts + Tools | unklar |
| Eignung | kleinste stabile v1 für alle Projekttypen | deferred |

Produktive Wahl: **kleinste stabile native Architektur** = Supervisor + Named Subagents.

## Architektur

```text
User
  ↓
Supervisor (local-fast)
  ├── researcher  (local-fast, read-only, optional Browser)
  ├── architect   (local-quality, read-only)
  └── reviewer    (local-quality, read-only)
```

Kein Writer in v1. Desktop und Images bleiben Supervisor-only. Browser nur `researcher` (Single-Owner). Keine Agenten-Kaskade (`maxSubagentDepth=1`).

Später erweiterbar (noch nicht gebaut): Coding, Testing, Browser-only, Desktop-only, Assets/Image, Build/Packaging, projektabhängige Spezialisten — **plattformneutral**, keine feste Bindung an Android/Mobile/Web/Gaming.

## Dateien

```text
.qwen/agents/researcher.md
.qwen/agents/architect.md
.qwen/agents/reviewer.md
```

Serve-CWD ist `/srv/ai/workspaces`. Agents müssen sichtbar sein:

```text
/srv/ai/workspaces/.qwen/agents → <repo>/.qwen/agents
```

Sync: `scripts/sync-qwen-agents-to-workspace.sh`

Skill (Dokumentation; `skill`-Tool bleibt disabled): `skills/supervisor-team/`

## Settings (Host `~/.qwen/settings.json`)

- `tools.disabled`: `agent`, `list_agents`, `send_message` **entfernt** (Shell/YOLO/Worktree-CLI bleiben disabled)
- `model.maxSubagentDepth: 1`
- `model.fastModel: local-fast`
- `agents.modelGrades`: `fast→local-fast`, `quality→local-quality`
- MCP **1.6.0 / 32**, `alwaysLoadTools: false`, `trust: false`, `tools.visible: []`
- Compact `0.95` / `local-fast` + Compact State Ledger unverändert
- `experimental.agentTeam` **nicht** gesetzt

## Tool-Allowlisten (Auszug)

Gemeinsam RO: `tool_search`, `tool_call`, `read_file`, `grep_search`, `glob`, `knowledge_search`, `knowledge_get`, `memory_load`.

| Agent | Extra | Verboten |
|-------|-------|----------|
| researcher | `browser_*` | write/edit/shell/agent/desktop/images/`memory_update`/`knowledge_record` |
| architect | — | + browser |
| reviewer | — | + browser |

**Pflicht:** `subagent_type` setzen. Ohne Named Type startet **general-purpose** mit voller Tool-Liste (Allowlist-Bypass).

**Pflicht Agent-Args:** `description` (non-empty) + `prompt` (non-empty). Sonst `invalid_tool_params`.

## Modellrouting / GPU

| Rolle | Modell |
|-------|--------|
| Supervisor | `local-fast` |
| Research | `local-fast` |
| Architecture | `local-quality` |
| Review | `local-quality` |

Ollama `MAX_LOADED_MODELS=1`: FAST↔QUALITY seriell. Nachweis t02: Supervisor/Researcher `local-fast`; Architect `local-quality` (VRAM Peak ~14.3 GiB beim Quality-Lauf).

## Context-Isolation

Subagents haben eigene `prompt_id` (`…#researcher-…`, `…#architect-…`) und eigene Prompt-Token-Zähler. Supervisor erhält kompakte Resultate, nicht die volle Subagent-Historie.

Beispiel t02: Supervisor max ~15226; Researcher eigener Context (bis ~24k bei langen Runs); Architect ~5–6k; Agent-Result-Auszug im Parent klein.

## Delegationsregeln

Delegieren: Multi-Source-Research, Architektur, Review, Regressionstiefe, mehrere Fachbereiche.
Nicht delegieren: triviales Lesen (Git HEAD, eine Datei), eine klare Tool-Aktion.
Knowledge-first bei Fehlern/Architektur/Security/Replans.
Subagents: RESULT / EVIDENCE / RISKS / RECOMMENDATION / OPEN (≤1200 Tokens, Research ≤1800).
Kein Doppelarbeiten: Supervisor synthetisiert, wiederholt nicht die volle Analyse.

## Plattformneutralität

Kein Android-/Mobile-/Web-/Game-Hardcoding. Plattform und Stack werden **pro Projekt** aus Anforderungen abgeleitet (Web, Desktop, Mobile, Spiel, Tool, Automatisierung).

## Writer-Regel

Worktree-Isolation existiert als Agent-Parameter, aber v1 hat **keinen** Writer-Subagent. Schreibzugriff bleibt beim Supervisor. Kein paralleles Schreiben auf dem Hauptworkspace. Kein Git-Push.

## Security

- Read-only per Allowlist + `disallowedTools` (technisch, nicht nur Prompt)
- Permission-Test: Researcher ohne `write_file` im Schema → BLOCKED; `/tmp/researcher-should-not-write.txt` fehlt
- Parent: `trust: false`, `approvalMode: default`, kein YOLO, kein Shell
- Subagents erben keine YOLO-/Shell-Freigabe

## Backup / Rollback

Backup: `/mnt/ai-archive/backups/supervisor-multi-agent-20260922-125913`

Rollback: Settings aus Backup; Agents-Symlink entfernen; `agent`/`list_agents`/`send_message` wieder in `tools.disabled`. MCP/Ledger/Lazy unberührt.

## Tests

Belege: `benchmarks/supervisor-multi-agent-20260922/` (`summary.json` **pass: true**).

| Test | Ergebnis |
|------|----------|
| Failure-Prevention / Knowledge-first | PASS (Ledger erkannt) |
| Architecture Research+Architect | PASS |
| No-Delegation (Git HEAD) | PASS |
| Research local-fast | PASS |
| Review | PASS |
| Permission Isolation | PASS |
| Platform-neutral Web/Desktop/Game | PASS |
| Model Routing | PASS (Telemetry) |
| Context Isolation | PASS (Telemetry) |
| Writer / Worktree | SKIP |
| Agent Team | deferred / aus |

Regressions: Compact State Ledger `--check` OK; KB Search OK; Lazy (`alwaysLoadTools=false`, `visible=[]`); Security unverändert; MCP 1.6.0/32.

## Bekannte Grenzen

- Serve-CWD `/srv/ai/workspaces` braucht Agents-Symlink.
- Agent-Tool oft erst nach `tool_search` (`select:agent`).
- Ohne `subagent_type` → general-purpose (Security-Risiko; Supervisor-Prompt/Skill warnt).
- Ohne `description`/`prompt` → Tool-Fehler.
- Researcher kann Browser öffnen; parallel kein zweiter Browser-Owner.
- Agent Team / `/coordinate` nicht produktiv.
- Writer deferred.
- Kein autonomes Dauerlaufen / keine Spawn-Loops.
- Continuity-Compact in langer Multi-Agent-Session nicht als eigener Dauerlauf erzwungen; Ledger-Patch bleibt aktiv.

## Nächste Phase (nicht automatisch starten)

**Context-Strategie: 24K / 32K / ggf. höher für `local-quality` kontrolliert benchmarken — kein automatischer Cutover.**
