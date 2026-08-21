# Qwen-Code-Skills

Stand: 21.08.2026. Gilt für Qwen Code **0.21.13** unter `/srv/ai/apps/qwen-code`.

Dieses Setup ändert **nicht** QUALITY, Quantisierung oder den systemd-Override. FAST-Context 32K ist der dokumentierte Alias (`config/modelfiles/local-fast.Modelfile`).

## Welche Skills Qwen hier verwendet

Quelle im Repo: `skills/<name>/SKILL.md`

Aktivierung: relative Symlinks `.qwen/skills/<name> -> ../../skills/<name>`

| Skill | Zweck |
|-------|--------|
| `local-ai-stack` | lokale FAST/QUALITY-Rollen, localhost, GPU-Regel |
| `caveman` | knappe Antwortform |
| `verify-work` | Nachprüfung nach Änderungen |
| `angular-standalone` | Angular 17+ Standalone/Signals |
| `angular-i18n` | ngx-translate DE/EN |
| `openlayers-gis` | OpenLayers / GIS |
| `roblox-luau` | Roblox Luau |
| `allinkl-ftps-deploy` | All-Inkl FTPS / Portfolio-Deploy |

Zusätzlich liefert Qwen Code gebündelte Skills (`/review`, `/loop`, …). Die werden nicht versioniert.

## Setup

Nach einem Clone:

```bash
./scripts/setup-qwen-skills.sh
```

Wiederholt ausführbar. Korrigiert nur falsche Links auf `../../skills/<name>`. Zerstört keine fremden Dateien unter `.qwen/skills/`.

Prüfen:

```bash
./scripts/setup-qwen-skills.sh --check
```

Qwen-Erkennung (im Repo-Verzeichnis, ohne `--bare` / `--safe-mode`):

```bash
/srv/ai/apps/qwen-code/bin/qwen --debug -p 'Nenne die verfügbaren Projekt-Skills und stoppe.' -m local-fast
```

In einer interaktiven Sitzung: `/skills`.

## Rückgängig

```bash
./scripts/setup-qwen-skills.sh --uninstall
```

Entfernt nur die von diesem Skript gesetzten Relativ-Links. Die Dateien unter `skills/` bleiben.

## Bewusst nicht von Cursor übernommen

Nicht verlinkt und nicht kopiert:

- Cursor-Modellrouting (`model-routing`, `~/.cursor/model-routing.json`)
- Cursor-Subagents (`quick-task`, `verifier` mit Cursor-Modell, `angular-reviewer`, …)
- Codex/Cursor-Produkt-Skills unter `~/.agents/skills/` (`canvas`, `origin`, `statusline`, `create-hook`, …)
- Cursor-Tool-Namen, Hooks, Provider

In **diesem Workspace** sind User-Level-Skills abgeschaltet, damit `~/.agents/skills` Qwen nicht mit Cursor-Anweisungen füttert:

`.qwen/settings.json` (Projekt, überschreibt nicht `~/.qwen/settings.json`):

- `skills.disabledLevels: ["user", "bundled"]` — keine User-Skills aus `~/.agents` und keine gebündelten Qwen-Skills (`new-app`, …) in diesem Workspace. Projekt-Skills inkl. `verify-work` bleiben.
- `tools.computerUse.enabled: false` — keine `computer_use__*`-Tools in diesem Workspace
- `tools.visible: ["mcp__local-tools__generate_image"]` — MCP-Bildtool in der ersten Tool-Welle (Qwen 0.21.13: `alwaysLoadTools` ist ein Boolean am MCP-Server, kein Namens-Array)
- `env.QWEN_CODE_LEGACY_MCP_BLOCKING: "1"` — MCP-Discovery vor dem ersten Modellaufruf (sonst bleibt `generate_image` unsichtbar)
- `memory.enableManagedAutoMemory: false` und `memory.enableManagedAutoDream: false` — kein Auto-Memory-Prompt mit `~/.qwen/projects/<sanitizeCwd>/…` in diesem Workspace. Bestehende Memory-Dateien bleiben auf der Platte; Backup unter `/mnt/ai-archive/backups/qwen-memory/`. Schema-Keys aus Qwen 0.21.15 `SETTINGS_SCHEMA`.
- `ui.enableFollowupSuggestions: false` — keine `commit`-Placeholder im TUI-Input. Schema-Key in Qwen 0.21.15 `SETTINGS_SCHEMA`.

`apps/local-tools/config/qwen-mcp.json` setzt `alwaysLoadTools: true` am Server `local-tools`. Das landet bei einem Deploy in der globalen Qwen-Config, ohne `model.name` oder `trust` zu ändern.

`select:generate_image` und Keyword `image` in ToolSearch brauchen den Patch `docs/QWEN_TOOLSEARCH_MCP_ALIAS.md` (nur Qwen 0.21.15).

## FAST / QUALITY

- FAST: Ollama `local-fast` / `qwen3.5:9b` Q4_K_M, `num_ctx` 32768, Qwen-Provider `contextWindowSize` 32768. Rebuild: `./scripts/apply-local-fast-context.sh`. Rollback 16K: `./scripts/rollback-local-fast-context.sh`.
- QUALITY: Ollama `local-quality` / `qwen3.6:27b`, Qwen-Provider `local-quality`, Context 8K (unverändert)

Host-Default in `~/.qwen/settings.json`: `model.name` = `local-fast`. QUALITY nur explizit (`qwen -m local-quality`). systemd-Override unverändert. Backup vor FAST-32K: `/mnt/ai-archive/backups/ollama-fast-ctx/`.

## Trust

Projekt-`.qwen/settings.json` wirkt nur in einem **vertrauenswürdigen** Workspace. Fehlt Trust, Workspace-Settings und Projekt-Skills ignoriert Qwen. Dann `/trust` im Qwen-CLI oder Eintrag in `~/.qwen/trustedFolders.json` — das ist eine globale Datei und hier **nicht** geschrieben.
