# Changelog

Host Vollstrecker, 2026-08-18. Phasen in dieser Reihenfolge. Phase 4 (Coding-Suite) übersprungen auf Anweisung.

## Phase 0 — Inventur und Pfade

- Snapshot `/.snapshots/2026-08-18-phase0-vor-ai`
- fstab-Backup `~/ai-stack-rollback/fstab.phase0`
- Seagate UUID `CE0AB35E0AB3426F` → `/mnt/ai-archive` (ntfs-3g, nofail)
- `/etc/local-ai/stack.env` ohne Secrets
- `/srv/ai` auf Crucial SATA SSD
- Archiv-Videos: `ki-videos` statt `videos/` (NTFS-Kollision mit `Videos/`)

## Phase 1–2 — Ollama Runtime

- Ollama **0.32.14** (`/usr/local/bin/ollama`), `127.0.0.1:11434`
- Drop-in: `OLLAMA_MODELS=/srv/ai/models/ollama`, KEEP_ALIVE 5m, MAX_LOADED_MODELS=1, FLASH_ATTENTION, KV `q8_0`, NUM_PARALLEL=1
- GitHub `GalasMichal/linux-lokales-ki` privat

## Phase 3 — FAST / QUALITY

- Pull `qwen3.5:9b` (6,6 GB) und `qwen3.6:27b` (17 GB)
- Aliase `local-fast` (16K), `local-quality` (8K)
- 8K-QUALITY-Smoke stabil; 16K-QUALITY einmal ok, Default bleibt 8K
- 256K aus; optionale Tags nicht gezogen
- Coding-Benchmark **nicht** gelaufen

## Phase 4 — nicht ausgeführt

Fünf Coding-Aufgaben / Agentenzyklus: deferred.

## Phase 5 — Qwen Code

- Standalone 0.21.13 nach `/srv/ai/apps/qwen-code`
- Settings `~/.qwen/settings.json`, Dummy-Key, nicht yolo
- Smoke `OK` mit `local-fast`, plan-mode, 16K-Prompt-Tokens beobachtet

## Phase 6 — ComfyUI

- Clone `Comfy-Org/ComfyUI` Commit `cc0fc21`, Version 0.33.0
- venv Python 3.13.14, torch 2.13.0+cu130
- User-Unit `comfyui.service`, Bind `127.0.0.1:8188`, linger
- `extra_model_paths.yaml` → `/srv/ai/models/comfyui`
- HTTP 200 `/system_stats`; keine Custom-Node-Packs

## Phase 7 — FLUX.2 [klein] 4B

- fp8 UNET + `qwen_3_4b` + `flux2-vae` auf die SSD
- Offizielle Workflows nach `/srv/ai/workflows/comfyui/`
- Qualitäts-T2I-Suite zuerst deferred; später Smoke (siehe unten)

## Nach Phase 7 — 18.08.2026

- Z-Image-Template + FLUX-Dateien → Shape-Error `512x2560 vs 7680x3072`
- Offizieller Graph, CLIP-Typ `flux2`; Smoke Seed 42: **4,32 s**, VRAM-Peak **14701 MiB**, Bild `/mnt/ai-archive/images/inbox/flux2_klein_smoke_s42_00001_.png`
- Open WebUI Quadlet `:main` auf `127.0.0.1:3000`, Pasta loopback, Daten auf SSD
- KI-Zentrale: Hub `:8790`, Desktop-Symbol, Knöpfe Chat / Arbeiten / Bilder, Unload vor Bild

## KI-Arbeitsplatz — 21.08.2026

- Alte KI-Zentrale gesichert und deaktiviert, nicht gelöscht
- Neue Desktop-Starter `KI-Arbeitsplatz` und `Lokaler Chat`
- KI-Arbeitsplatz auf `127.0.0.1:8790`
- fester Qwen-Einbettungsproxy auf `127.0.0.1:8791`
- Qwen Code Web auf `127.0.0.1:4170`, Start nur im Agent-Modus
- ComfyUI-Autostart deaktiviert, Start nur im Bildermodus
- App-Fenster mit eigenen lokalen Brave-Profilen
- Schließen des letzten KI-Fensters stoppt Qwen und ComfyUI und entlädt Ollama
- Qwen-Provider-Ansicht auf `local-fast` und `local-quality` über Ollama gefiltert
- Provider-Anmeldung und Cloud-Modellwechsel über den Arbeitsplatz gesperrt
- Einfacher FLUX-T2I-Workflow mit Größenlimit, Batch-Limit, Job-ID und Manifest
- End-to-End-Test 512 × 512, Seed 42: ComfyUI 27,88 s; Gesamt 55,156 s inklusive erstmaliger SHA-256-Berechnung
- Cleanup nach Bildauftrag: ComfyUI/Qwen inaktiv, Ollama leer, VRAM 596 MiB
- Sicherungen: `/mnt/ai-archive/backups/ki-ui/20260821-090954` und `/mnt/ai-archive/backups/ki-ui/20260821-091646`

## Qwen-Skills — 21.08.2026

- Portable Skills unter `skills/` (kein Cursor-Modellrouting)
- Setup `scripts/setup-qwen-skills.sh` setzt relative Links nach `.qwen/skills/`
- Projekt-`.qwen/settings.json` schaltet User-Level-Skills in diesem Workspace aus
- Globale `~/.qwen/settings.json`: Default `local-fast` (Backup `/mnt/ai-archive/backups/qwen/20260821-112638/`)
- Ollama unverändert
- Doku: `docs/QWEN_SKILLS.md`

## Bewusst offen

MCP, Phase-4-Zyklus, Vision-Suite, Image Editing, optionale LLMs, 256K, formale A01–A14-Abnahme.
