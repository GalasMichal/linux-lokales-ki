# Qwen-Code-Skills

Stand: 21.08.2026. Gilt für Qwen Code **0.21.13** unter `/srv/ai/apps/qwen-code`.

Dieses Setup ändert **nicht** Ollama (kein Re-Download, keine Quantisierung, kein Context-Tuning).

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

`.qwen/settings.json` → `skills.disabledLevels: ["user"]`

Das ist eine **Projekt**-Datei. `~/.qwen/settings.json` wird nicht überschrieben.

## FAST / QUALITY

- FAST: Ollama `local-fast` / `qwen3.5:9b`, Qwen-Provider `local-fast`, Context 16K
- QUALITY: Ollama `local-quality` / `qwen3.6:27b`, Qwen-Provider `local-quality`, Context 8K

Host-Default in `~/.qwen/settings.json`: `model.name` = `local-fast`. QUALITY nur explizit (`qwen -m local-quality`). Ollama-Tuning bleibt unberührt. Backup vor der Umschaltung: `/mnt/ai-archive/backups/qwen/20260821-112638/settings.json`.

## Trust

Projekt-`.qwen/settings.json` wirkt nur in einem **vertrauenswürdigen** Workspace. Fehlt Trust, Workspace-Settings und Projekt-Skills ignoriert Qwen. Dann `/trust` im Qwen-CLI oder Eintrag in `~/.qwen/trustedFolders.json` — das ist eine globale Datei und hier **nicht** geschrieben.
