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

## Local-Tools MCP — 21.08.2026

- Gateway `apps/local-tools/` auf `127.0.0.1:8765`, ein Tool `generate_image`
- Ruft den KI-Arbeitsplatz `flux2-klein-t2i-v1` auf, kein eigener Comfy-Client
- Live-Test 512×512 Seed 20260821: Job `2a7951cb7860`, ~39 s, GPU-Cleanup ok
- Qwen sieht den MCP-Server (`qwen mcp list`: Connected)
- Projekt-`.qwen/settings.json`: `generate_image` als `mcp__local-tools__generate_image` sichtbar, `computer_use` aus, MCP-Discovery blockierend. Interaktives FAST ruft das Tool trotzdem oft nur im Text auf, ohne Function-Call.
- Rollback stellt nur MCP-Schlüssel in `~/.qwen/settings.json` wieder her, nicht das Default-Modell

## Qwen ToolSearch MCP — 21.08.2026

- `select:generate_image` und Keyword `image` finden `mcp__local-tools__generate_image`
- Apply: `scripts/apply-qwen-toolsearch-mcp-alias-patch.sh` (nur 0.21.15, SHA-Check)
- Rollback geht auf Stock, nicht auf den Zwischenpatch
- Git-Snapshot-Omit im selben Apply (Task-Hijack); Doku `docs/QWEN_GIT_SNAPSHOT.md`
- Gateway akzeptiert numerische Seed-Strings und `size` wie `512x512`
- Doku: `docs/QWEN_TOOLSEARCH_MCP_ALIAS.md`

## FAST 32K Coding-Context — 21.08.2026

- Einmalige Policy: FAST `num_ctx` 16384 → 32768, Parent `qwen3.5:9b` Q4_K_M, kein Pull
- Qwen-Provider `local-fast.contextWindowSize` 32768; QUALITY bleibt 8192
- 100 % GPU, `ollama ps` CONTEXT 32768, ~6.1 GB; Override-SHA unverändert
- Projekt: Auto-Memory aus, Follow-up-Suggestions aus (`ui.enableFollowupSuggestions: false`)
- Apply/Rollback: `scripts/apply-local-fast-context.sh`, `scripts/rollback-local-fast-context.sh` (`config/modelfiles/local-fast.Modelfile`)
- Backup: `/mnt/ai-archive/backups/ollama-fast-ctx/`

## KI-Arbeitsplatz Agent-Ladeanzeige — 22.08.2026

- Agent-Tab: Fortschritt nur bei echten Ereignissen (Comfy-Stop, Qwen-Start, `/health`, iframe-Load)
- Balken sitzt dauerhaft im Header, solange Agent offen ist; Overlay deckt das Fenster nicht mehr zu
- Proxy strippt `Origin`/`Referer` Richtung Qwen und spiegelt CORS für 8790/8791 — sonst bleibt das iframe weiß (`crossorigin` JS/CSS)
- Chat-UI ist unabhängig vom Ollama-Modell; Timeout 90s; iframe `?theme=dark`

## Persistent Memory + PDF-Tools — 15.09.2026

- `.agent/` als projektbezogener Speicher: STATE, REQUIREMENTS, DECISIONS (append-only), TASKS, TOOLS, history
- Qwen Managed Auto-Memory bleibt aus; MCP-Tools `memory_load` / `memory_update`
- PDF-Pack auf bestehendem `local-tools`: `pdf_read` `pdf_inspect` `pdf_create` `pdf_edit` `pdf_merge` `pdf_split` `pdf_ocr` `pdf_render` plus QA/Render
- Skills `agent-memory` und `document-tools`; Doku `docs/AGENT_MEMORY.md`, `docs/PDF_TOOLS.md`
- Kein sudo-dnf: Python-Libs user-site, tesseract/qpdf aus Fedora-RPMs nach `~/.local/bin`
- Smoke-Tests: `tests/test_agent_memory.py`, `tests/test_pdf_tools.py`
- Live-MCP-Deploy nach `/srv/ai` nicht in diesem Schritt ausgeführt

## MCP live deploy + Update-Analyse — 15.09.2026 Abend

- Deploy `local-tools` 1.1.0, Backup `/mnt/ai-archive/backups/local-tools-mcp/20260915-183907`
- `trust: false`, `approvalMode: default`; Health + `live_mcp_smoke` PASS
- Live Memory/PDF über MCP-Client; Qwen-FAST-Baseline 16262 prompt_tokens, VRAM 9212 MiB
- Ollama bleibt 0.32.14 (sudo), Qwen Code bleibt 0.21.15 (0.21.15-Patches). Stables: Ollama 0.34.0, Qwen Code 0.23.4
- Nächster Schritt: Model-Benchmark, bestehende Aliase nicht ersetzen

## Ollama 0.34.0 + Qwen 0.23.4 + Fable-Benchmark — 15.09.2026 Abend

- Ollama **0.34.0**, Override-SHA unverändert; Rollback `/mnt/ai-archive/backups/ollama-0.32.14-20260915-185652`
- Qwen Code **0.23.4**; Patches unter `patches/qwen-code/0.23.4/` (ToolSearch-Kurzname, Registry, Git-omit in `chunk-NXUZFW3G.js`)
- Additive Modelle `qwen3.8:27b` und `qwen3.6:27b-coding` plus 8K-Aliase `bench-qwen38-27b-8k` / `bench-qwen36-coding-8k`
- `local-fast` **unverändert**; Parents und Bench-Aliase **behalten**
- Fable-Benchmark: Gewinner QUALITY/Agent/Coding **Qwen3.8 27B 8K**; FAST bleibt 9B. Rohdaten `benchmarks/fable-agent-20260915/`
- `trust: false`, kein Push, kein YOLO

## QUALITY-Cutover Qwen3.8 — 15.09.2026 19:56

- Alias `local-quality` umgestellt: `FROM qwen3.8:27b`, `num_ctx 8192`. ID `993995e538ad` = `bench-qwen38-27b-8k`
- Backup `/mnt/ai-archive/backups/local-quality-20260915-194453/`; Rollback `scripts/rollback-local-quality-qwen36.sh`
- Smoke PASS: ctx 8192, ~14.2 GB VRAM, 38 % CPU-Offload, Tool-Call ~25 tok/s
- Interaktiver Qwen-Web Memory/PDF-E2E **FAIL**: 90 s Thought-Chunks, 0 MCP-Calls (Modell behauptet fälschlich MCP disconnected)
- Nächste Phase nur geplant: Vision-QA auf `pdf_render`-PNG

## QUALITY Tool-Call Debug — 15.09.2026 21:16

- Ursache nachgewiesen: Qwen Serve schickt ACP-System (~26k Zeichen) plus viele Tool-Schemas an Ollama `/v1`. Bei `num_ctx 8192` überläuft der Prompt; Ollama setzt `prompt_eval` auf **4098**. MCP `memory_load` lag im Wire-Array, das Modell sah es nach Truncation nicht mehr.
- `think=false`/`enable_thinking=false` erreichen Ollama, `/v1` ignoriert sie für Qwen3.8. Wirksam ist `reasoning_effort=none` in `extra_body`.
- FAST 32k: derselbe 44-Tool-Request mit 29653 Tokens ruft `memory_load` auf. Replay des Serve-Bodies gegen Ollama reproduziert den QUALITY-Fehler — nicht Serve-spezifisch.
- 12 Tools (11 MCP + `tool_search`) + voller Prompt + Thinking aus: **7689** Tokens, strukturierter `memory_load`. 15+ Tools: wieder 4098, kein Tool-Call.
- Config-Fix in `~/.qwen/settings.json` (kein 0.23.4-Patch): `tools.eager=[]`, ungenutzte Builtins `disabled`, `skills.disabledLevels=["user","bundled"]`, Quality `extra_body.reasoning_effort=none`. `trust: false`, `approvalMode: default`.
- Kurzprompt über Serve: `memory_load` + Permission `proceed_once` PASS. Voller Memory→PDF-E2E: **PASS** in 68 s über isolierte Sessions (`memory_load` → `pdf_create` → `pdf_read` → `pdf_render` → `memory_update`, je `proceed_once`). PDF `.agent/tmp/quality-cutover-e2e.pdf`, PNG 1158×1638. FAST Serve-Regression `memory_load` PASS (`local-fast` 32768).
- unittest 56 OK. Default-Modell wieder `local-fast`. `trust: false`, `approvalMode: default`.
- Proxy `benchmarks/ollama_wire_proxy.py` nur für den Wire-Nachweis, produktiv aus. Quality wieder `http://127.0.0.1:11434/v1`.
- Rohdaten: `benchmarks/toolcall-debug-20260915/`, `benchmarks/quality-cutover-20260915/e2e-multiturn.json`
- Nächste Phase: PDF Vision-QA **planen**, nicht implementieren.

## PDF Vision-QA — 15.09.2026 21:40

- Preflight: `local-quality` hat Ollama-Capability `vision` (CLIP 460.73M). `/api/chat` mit PNG las „QUALITY Cutover E2E“, 16.7 s, VRAM 14480 MiB, Thinking aus.
- Neues MCP-Tool `pdf_vision_qa` auf `local-tools` 1.2.0. Direkt Ollama `/api/chat`, Structured Output, Seiten einzeln. Optional nach technischer `qa_pdf`.
- Live-Fixtures PASS. Direct bad→clean: clip+overlap high, danach `ok`. Serve: 2× `pdf_vision_qa` + `proceed_once`. Serve-`pdf_create`/`pdf_render` in 8k weiter unzuverlässig.
- Doku: `docs/PDF_VISION_QA.md`. Skill `document-tools` mit max. 2 Korrekturzyklen.
- Kein neues Modell, kein YOLO, `trust: false`.

## QUALITY 16K/32K Context-Probe — 16.09.2026 18:00

- `local-quality` **unverändert** 8192 / ID `993995e538ad`. `local-fast` unverändert 32768. Override unangetastet.
- Additive Aliase `bench-qwen38-27b-16k` (`ad1736a075f0`, Runtime 16384) und `bench-qwen38-27b-32k` (`d4bf257f520d`, Runtime 32768) FROM `qwen3.8:27b`. Kein Pull.
- Text 8k vs 16k: 13.2 vs 12.1 tok/s, VRAM beide ~14.3 GB. 32k lädt, ~10 tok/s, Offload 41/59.
- 44-Tool-Dump: 8k → prompt_eval **4098**, kein Tool. 16k → 8194 Tokens, falsches `update_plan`. 32k → 29653 Tokens, korrektes `memory_load`.
- 16k Serve-E2E **eine Session PASS** (352 s): memory_load → pdf_create → pdf_read → pdf_render → pdf_vision_qa → memory_update, 7× `proceed_once`, kein YOLO. Context-Kompression 15691→11396 nach Essay. Vision-FP `empty_page` auf Mini-PDF.
- Default-Modell war kurz Bench-16k (Serve-Persistenz); zurück auf `local-fast`.
- unittest 66 OK, live_mcp_smoke 1.2.0, FAST Serve `memory_load` PASS.
- Backup `/mnt/ai-archive/backups/bench-qwen38-16k-20260916-1738/`. Rohdaten `benchmarks/ctx16k-20260916/`.
- Empfehlung: 8k behalten; 16k als nächster **expliziter** Cutover. Kein automatisches Umschalten.

## QUALITY 16K produktiv — 16.09.2026 21:10

- Expliziter Cutover: `local-quality` `num_ctx` 8192 → **16384**, Qwen `contextWindowSize` 8192 → **16384**. ID `ad1736a075f0` = Bench-16k. Parent, FAST, Override, Bench-Aliase unangetastet.
- Apply `scripts/apply-local-quality-16k.sh`, Rollback `scripts/rollback-local-quality-16k.sh` (3.8/8k + Default `local-fast`). Backup `/mnt/ai-archive/backups/local-quality-16k-20260916-205745/`.
- Smoke PASS: Runtime CONTEXT 16384, Offload 38/62, VRAM ~14.1 GB, Tool-Call `memory_load`, tok/s ~10 (Load) / ~23 (Coding).
- Serve-E2E eine Session PASS (565 s, 7× `proceed_once`): Memory+PDF+Vision+Update. Essay zwischen Tools, Context 16034→11461, Leftover nach Update abgebrochen.
- Default wieder `local-fast`. FAST Serve `memory_load` PASS. unittest 66 OK. live_mcp_smoke OK.
- 32K nicht produktiv.

## QUALITY Essay-Control — 16.09.2026 22:45

- Sichtbarer Zwischentext ist kurz (`general.outputStyle=Concise`, `skipStartupContext=true`). `memory_load` liefert DECISIONS kompakt (letzte 4 voll, Rest Überschriften) und TASKS ohne lange Done-Liste. Requirements unverändert.
- 3-Tool D: keine Kompression, kein doppeltes `pdf_create`, 226 s. Trotzdem ~1839 versteckte Tokens / 2m15s nach `pdf_create` (Ollama `n_gen`, nicht im Chat).
- 6-Tool-E2E: alle MCP-Calls, PDF+PNG, 7× `proceed_once`, 287 s statt 565 s. Danach weiter Compact 14710→10935 und zweites `pdf_create`. Streng FAIL, funktional die Kette.
- Variante B (nur Prompt) wirkungslos. Variante E `max_tokens=768` hat `pdf_create` abgeschnitten — zurückgerollt. Kein 0.23.4-Patch.
- Backup `/mnt/ai-archive/backups/qwen-essay-control-20260916-222500/`. unittest 69 OK. Default `local-fast`, `trust: false`.
- Offen: die versteckte QUALITY-Generierung selbst.

## QUALITY Hidden-Gen — 16.09.2026 23:10

- Wire: nach `pdf_create` war die unsichtbare 2-Minuten-Generierung **Qwen-Auto-Compact** (`<analysis>` + `<state_snapshot>` als `delta.content`, 2713 Tokens, `reasoning_content=0`). ACP zeigt Compact nicht. Orphan-Repair markierte den erfolgreichen `pdf_create` als fehlgeschlagen → Duplikat.
- Ursache der frühen Kompression: Turn-2-Prompt **14447 / 16384** über der 85%-Schwelle **13926** (Systemprompt + 13 Tools + `memory_load` JSON).
- Fix ohne Patch: `context.autoCompactThreshold=0.95`, `compactionModel=local-fast`. Kein globales `max_tokens`. Memory nicht weiter gekürzt.
- 3-Tool QUALITY **41 s** (vorher 275 s), kein Compact, kein Duplikat. 6-Tool-E2E **PASS 156 s** (vorher 287 s), 6× `proceed_once`.
- Backup `/mnt/ai-archive/backups/qwen-hidden-gen-20260916-224945/`. Rohdaten `benchmarks/quality-hidden-gen-20260916/`.
- unittest 73 OK. live_mcp_smoke OK. Default `local-fast`, `trust: false`.

## QUALITY Hidden-Gen Re-Verify — 21.09.2026 10:18

- Settings unverändert: `autoCompactThreshold=0.95`, `compactionModel=local-fast`, kein globales `max_tokens`.
- Nach Boot: MCP `:8765` und Qwen Serve `:4170` inaktiv (systemd-Zyklus mit KI-Arbeitsplatz). Manuell gestartet.
- Erster E2E-Versuch FAIL nach 14 s: Harness-Abort während Prefill, nicht Compact-Regression.
- Zweiter E2E **PASS 158 s**, 6 Tools, 6× `proceed_once`, kein Duplikat, keine 2-Minuten-Pause nach `pdf_create`.
- Backup `/mnt/ai-archive/backups/qwen-hidden-gen-verify-20260921-101154/`.

## A01–A14-Abnahme — 21.09.2026 11:20

- Keine kanonische A01–A14-Matrix gefunden. Neu: `docs/ACCEPTANCE_A01_A14.md`.
- systemd-Zyklus nachgewiesen (`Job local-tools-mcp.service/start deleted`). Kleinster Fix: MCP unabhängig, Workplace `After=network.target`. Qwen/ComfyUI bleiben disabled. Härtung unverändert. Apply `scripts/apply-mcp-independent-boot.sh`, Rollback `scripts/rollback-mcp-independent-boot.sh`. `systemd-analyze --user verify` Exit 0. Kein Reboot.
- Unittest **75 OK**, live_mcp_smoke OK, Patches `--check` OK.
- A10 PDF-Kette live PASS. A11 Live-Vision 5/5 PASS. A12 T2I 512 Seed 42 PASS (64,9 s), Archiv `b8d57bc6dd22`, Cleanup VRAM 1795 MiB.
- QUALITY-E2E 10:14 **PASS 158 s**. Nachmittag 196 s: Kette komplett, FAST-Compact 15821→9392, doppeltes `pdf_read` (Memory über 95 %-Schwelle). Kein 27B-Hidden-Gen nach `pdf_create`.
- Gesamt: **PASS WITH LIMITATIONS**. Reboot-Beweis offen. Kein 32k-Cutover. `trust: false`, `approvalMode: default`.

## Runtime-Update Ollama 0.34.2 + Qwen 0.24.2 — 21.09.2026 12:35

- Offizielle Stables: Ollama **v0.34.2** (nicht RC 0.34.3-rc1), Qwen Code **0.24.2** (nicht 0.24.1). Override SHA `7fb44d5f…` unverändert.
- Ollama-Update über Konsole-TTY (kdialog-Askpass leerte das Passwort). Regression PASS. FAST generate ohne `think: false` kann leer bleiben — bekannt, kein 0.34.2-Produktfehler.
- Qwen 0.24.2: drei Host-Patches portiert (`tool-search-ANXFKRMW.js`, `chunk-VQUX7GWP.js`, `chunk-IOISNXQ2.js`). `--check` OK. Keep `lib/qwen-code.0.23.4`. Rollback `scripts/rollback-qwen-0.23.4.sh` (Ollama bleibt 0.34.2).
- QUALITY-E2E: Versuch 2 **176 s**, 6 Tools, 7× `proceed_once`, Compact + doppeltes `pdf_render`. Harness streng FAIL, funktional wie A14. Kein extra Compact-Patch. Kein YOLO.
- Nächste Phase nur Empfehlung: Qwen-Image-2.1 als Image-Editing-Kandidat. **Nicht heruntergeladen.** ComfyUI 0.33.0 zu alt für Native-Nodes; 16 GB nur mit int8/w4a8, nicht bf16-Encoder 17,5 GB.

## Qwen-Image-2.1 Analyse — 21.09.2026 12:50

- Nur Plan. Kanonisch: `docs/QWEN_IMAGE_2_1_ANALYSIS.md`. Kein Download, kein Comfy-Upgrade, kein `edit_image`.
- Live ComfyUI bleibt **0.33.0** `cc0fc21`. Native 2.1-Nodes erst in **ComfyUI v0.37.0** (PR #16400).
- Empfehlung: int8-DiT + w4a8-Encoder + VAE (14,25 GB). bf16-Encoder 17,53 GB ungeeignet. PE-9,47-GB-Dateien nicht ziehen.
- Lizenz Qwen Research (nicht-kommerziell). FLUX.2-[klein] T2I bleibt. GPU weiter sequentiell.
- Nächste Bau-Phase nur: isoliertes ComfyUI 0.37.0 + FLUX-Regression. Keine 2.1-Gewichte in jener Phase.

## ComfyUI 0.37.0 — 21.09.2026 14:10

- Offizielles Stable **v0.37.0** (kein 0.37.1, kein RC). Commit `73c9bad`. Qwen-Image-2.1-Nodes drin. Bericht: `docs/COMFYUI_0_37_UPGRADE.md`.
- Isoliert :8189 FLUX 512/42 **35 s** PASS, dann Cutover. Keep 0.33.0-Tree+Venv. Torch **2.13.0+cu130**. Autostart bleibt disabled. Output-Dir unverändert für den Arbeitsplatz.
- Produktiv: Workplace **61,7 s** Job `5dd9fb157e52`; MCP `generate_image` **22,6 s** Job `68ae328f6c49`; Cleanup VRAM ~1,8 GiB. `live_mcp_smoke` PASS.
- Keine Qwen-Image-2.1-Gewichte. Kein `edit_image`. Rollback `scripts/rollback-comfyui-0.33.0.sh /mnt/ai-archive/backups/comfyui-0.33.0-20260921-140000`.
- Nächste Phase nur: Download int8-DiT + w4a8-Encoder + VAE und isolierter Edit-Smoke.

## Qwen-Image-2.1 isolierter Edit-Smoke — 21.09.2026 14:28

- Drei offizielle Dateien von `Comfy-Org/Qwen-Image-2.1` Rev `ace0edeb`, SHA alle OK. Lizenz Qwen Research, nur privater lokaler Test.
- Isoliert :8189: 512 kalt **37,86 s** Peak 15509 MiB; 1024 warm **15,22 s** Peak 15618 MiB. Apfel rot→grün sichtbar. Kein OOM.
- FLUX-Regression: Workplace `9fbab1ed7eaa` 42,31 s; MCP `7fb6b408ab1b`; Workflow-/Modell-Hashes unverändert. `live_mcp_smoke` PASS.
- Bericht: `docs/QWEN_IMAGE_2_1_SMOKE.md`. Kein `edit_image`, keine Editing-UI, kein Git-Push.

## Qwen-Image-2.1 Edit Backend + MCP — 21.09.2026 14:56

- Frozen Workflow `qwen-image-21-edit-v1` SHA `78a0d0f445b08557d5e69139ce7f2d2ad547658bcaf90a10cfe154121b65bbe8`. Endpoint `POST /api/images/edit`. MCP `edit_image` auf `local-tools` **1.3.0** (12→13 Tools).
- Live: EDIT-1024 Job `cd3220e9efaa` 81,9 s Peak 15250 MiB; MULTI `faacb571fbd1`; MCP `93d02c1bffad`. FLUX `bf5df1a30c27` Workflow-/Modell-Hashes unverändert.
- `trust: false`, `approvalMode: default`, kein YOLO. Keine Editing-UI. Bericht: `docs/QWEN_IMAGE_2_1_EDIT.md`. Backup `/mnt/ai-archive/backups/qwen-image-21-edit-20260921-144943`.
- Nächste Phase nur: sichtbare KI-Arbeitsplatz-Editing-UI.

## Qwen-Image-2.1 Editing-UI — 21.09.2026 15:17

- Bilder-Subnav **Erzeugen | Bearbeiten | Workflow (Experte)**. FLUX-Formular unverändert. Experte/Agent/System erreichbar.
- Dateiübergabe: `POST /api/images/stage` nach `/srv/ai/workspaces/ki-workplace-stage` (`ui_stage_{uuid}`), dann bestehendes `POST /api/images/edit`. Ergebnis `GET /api/images/jobs/{id}/output`. MCP 1.3.0 / 13 Tools unangetastet.
- Live UI-Edit Job `37fa72860c19` 78,681 s Peak 15598 MiB, 1024×1024 PNG. FLUX 512/42 Job `e8e02a01005d` 59,425 s, Workflow-SHA und Modell-Hashes unverändert.
- Unit 50 OK. `trust: false`, `approvalMode: default`, kein YOLO. Bericht: `docs/QWEN_IMAGE_2_1_EDIT_UI.md`. Backup `/mnt/ai-archive/backups/qwen-image-21-edit-ui-20260921-150824`.
- Nächste Phase nur: Open-WebUI als MCP-Client für `generate_image` / `edit_image`.

## Open-WebUI Bild-Tools — 21.09.2026 19:20

- Open WebUI **0.11.0**. Kein MCP, kein Comfy-Client. Python-Tool `local_images` (`generate_image` / `edit_image`) → bestehender KI-Arbeitsplatz `:8790`. MCP 1.3.0 / 13 Tools unangetastet.
- Upload: Container-Datei → `POST /api/images/stage` → Edit. Originalupload ist Default-Input. KI-Ergebnis nur nach ausdrücklichem Second-Edit. Größe 512/768/1024 aus Original bzw. Nutzerzahl, nie >1024.
- Live: GENERATE `148297e9d23b`; EDIT-ORIGINAL 512 `527b0e73279c`; Second-Edit `a1a1fb7103b1` (Input = voriges Ergebnis); SIZE-EXPLICIT 1024 `e317ab836680`; Workplace FLUX `d54456bb448e`. Unit 16 OK, e2e 13/13 PASS.
- `trust: false`, `approvalMode: default`, kein YOLO. Bericht: `docs/OPEN_WEBUI_IMAGE_TOOLS.md`. Backup `/mnt/ai-archive/backups/open-webui-image-tools-20260921-164833`.
- Nächste Phase nur: Browser-/Desktop-Agent.

## Lokaler Browser-Agent — 21.09.2026 19:40

- Brave **153** (schon da) + Playwright **1.55.0** (neu, kein extra Chromium). Eigenes Profil `/srv/ai/cache/browser-agent`. Kein Selenium, kein Qwen-Computer-Use, kein öffentlicher Debug-Port.
- MCP `local-tools` **1.3.0/13 → 1.4.0/21**. Acht `browser_*`-Tools. `trust: false`, Votes `proceed_once`. ToolSearch-Patch unverändert.
- Live: example.com, Klick auf den Link, zurück, PNG, Typen, Scroll, `file`/`javascript`/`127.0.0.1` gesperrt. Qwen-E2E Session `8a6243d4-b169-438f-968e-409251afee9f`: `browser_open` → `browser_click`, Ziel IANA.
- FLUX- und Edit-SHA unverändert. Open-WebUI-Bild-Tools unverändert. Bericht: `docs/BROWSER_AGENT.md`. Backup `/mnt/ai-archive/backups/local-tools-mcp/20260921-192942`.
- Nächste Phase nur: Desktop-Agent. 2K/4K und Compact-Prompt bleiben vorgemerkt, nicht gebaut.

## Lokaler Desktop-Agent — 21.09.2026 20:30

- Wayland, KDE Plasma 6.7.4. Steuerung über KWin-DBus und AT-SPI. Kein `ydotool`, kein Root, kein Eingabe-Daemon.
- MCP `local-tools` **1.4.0/21 → 1.5.0/29**. Acht `desktop_*`-Tools. `trust: false`, Votes `proceed_once`. ToolSearch-Patch unverändert.
- Live: Kate-Text, Ctrl+A/C, Scroll, KCalc `Eins`, Löschen/Passwort/Konsole blockiert. Qwen-E2E Session `7276c1fe-221e-4e87-b73f-0289683b8af9`: `desktop_snapshot` → `desktop_type` → `desktop_snapshot`.
- Browser sperrt weiter `file`, `javascript` und `127.0.0.1`. FLUX- und Edit-SHA unverändert. Bericht: `docs/DESKTOP_AGENT.md`. Backup `/mnt/ai-archive/backups/local-tools-mcp/20260921-202347`.
- Nächste Phase nur: 1536-Benchmark. 2K/4K und Compact-Prompt bleiben vorgemerkt, nicht gebaut.

## Qwen-Compact — 21.09.2026 21:30

- **FAIL – prompt-only insufficient.** Schwelle 0.95 und `compactionModel=local-fast` bleiben. Kein 32K-QUALITY.
- Nach `memory_load` entweder Ollama `no user query found in messages` (Schätzung noch unter 95 %) oder FAST-Compact und danach Abbruch bei 17216 Tokens gegen Limit 16384.
- Prompt-Patch nicht installiert. ToolSearch, Registry und Git-Snapshot unverändert. Browser und Desktop unverändert. MCP bleibt 1.5.0 / 29 Tools.
- Bericht: `docs/QWEN_COMPACT_CONTINUITY.md`. Beleg: `benchmarks/compact-continuity-20260921/summary.json`.

## Qwen Compact State Ledger — 22.09.2026

- **PASS.** Marker `linux-lokales-ki-compact-state-ledger` in `chunk-VQUX7GWP.js`. Lazy Tools unverändert. MCP 1.5.0 / 29. QUALITY 16384. Stock-Compact-Prompt.
- Nach Compact: maschinelle `<tool_continuity>`-Liste + Shrink großer erfolgreicher Results (auch doppeltes JSON von `memory_load`).
- QUALITY-E2E `667d9bc2` / `ledger4.json`: Compact 1× über `local-fast`, Tools je 1×, Folgeprompt **9318**, max 12901, kein Hard-Overflow, kein `no user query`.
- Retry: fail dann success (`retry5.json`, MCP `retry-mcp.json`). Repeat: `pdf_read` erneut (`repeat.json`). Unit 35 OK inkl. Ledger.
- Backup: `/mnt/ai-archive/backups/qwen-code/compact-state-ledger-20260922-111628`.
- Nächste Phase nur: Knowledge Base v2. Kein 32K. Kein 1536.

## Knowledge Base v2 — 22.09.2026

- **PASS.** MCP `local-tools` **1.5.0/29 → 1.6.0/32**. Tools `knowledge_search` / `knowledge_get` / `knowledge_record`, lazy.
- Store: `.agent/knowledge/entries.jsonl` + Index. 18 Seed-Einträge aus Repo-Docs. Keyword-Retrieval, avg ~325 Tokens, max 448 in der Suite.
- FAST E2E `0716174d…`, QUALITY E2E `4f20170c…`: zuerst Knowledge. Compact+KB Kern `90ce6e13…`: Ledger sichtbar, Folge max **13231**, kein sofortiger 2. Compact; `memory_update` in der Vollkette einmal ausgelassen (Limitation).
- Skill `knowledge-base`. Continuity-Prompt-Patch bleibt nicht installiert. Kein 32K. Kein 1536. Kein YOLO.
- Bericht: `docs/KNOWLEDGE_BASE_V2.md`. Backup `/mnt/ai-archive/backups/knowledge-base-v2-20260922-121004` und MCP `/mnt/ai-archive/backups/local-tools-mcp/20260922-121004`.
- Nächste Phase nur: Supervisor / Multi-Agent.

## Supervisor / Multi-Agent — 22.09.2026

- **PASS.** Native Qwen-0.24.2 Named Subagents: `researcher` / `architect` / `reviewer`. MCP bleibt **1.6.0 / 32**. Kein neuer Runtime-Patch.
- Settings: `agent` / `list_agents` / `send_message` freigeschaltet; `model.maxSubagentDepth=1`; Agent Team aus; Writer SKIP.
- Serve-Symlink `/srv/ai/workspaces/.qwen/agents`. Model-Routing: Research `local-fast`, Architecture/Review `local-quality`.
- E2E `benchmarks/supervisor-multi-agent-20260922/summary.json` alle Kern-Tests true. KB `KB-20260922-SUPERVISOR-MULTI-A-001`.
- Backup `/mnt/ai-archive/backups/supervisor-multi-agent-20260922-125913`. Bericht: `docs/SUPERVISOR_MULTI_AGENT.md`.
- Master-Plan: Ziel plattformneutral; nächster Schritt Context 24K/32K Benchmark (kein Auto-Cutover). Autonomer Software-Development-Workflow später.

## Runtime-Update — 02.10.2026

- **PASS.** Ollama **0.34.4 → 0.35.0**. Qwen Code **0.24.6 → 0.24.7** (Patches neu portiert nach `patches/qwen-code/0.24.7/`). ComfyUI **0.37.0 → 0.38.0** mit `--disable-comfy-compiler` (sonst Qwen-Image-2.1 Edit: aimdo compile error).
- Override/Ollama-Settings unverändert. Modelle und Aliase `local-fast` / `local-quality` unverändert. MCP 1.7.0 / 33.
- Workplace `COMFY_INPUT` auf `ComfyUI-0.38.0/input`.
- Additive Context-Probe 16K/24K/32K ohne schwere Artefakte; **kein QUALITY-Cutover**.
- Backup `/mnt/ai-archive/backups/runtime-update-20261002-084919`. Bericht: `docs/RUNTIME_UPDATE_2026-10-02.md`.

## QUALITY Context Serve-E2E-Leiter — 02.10.2026 ~16:10

- Serve Memory+PDF+Vision (`quality_context_ladder_serve_e2e.py`, proceed_once): **24K/32K PASS**; **16K FAIL** (zu eng); **40K FAIL** (Agent-Drift = zu hoch); 48K einmal PASS.
- Kein VRAM/RAM-OOM. Cutover höchstens **32K** — nur mit Freigabe. `local-quality` bleibt **16384**.
- Belege: `benchmarks/quality-context-ladder-20261002/`. Plan: `docs/QUALITY_CONTEXT_CUTOVER_PLAN_2026-10-02.md`. Handoff aktualisiert.

## Context Boundary Discovery — 02.–03.10.2026 (Abschluss ~07:05)

- Multi-Run Suites A–E (tool_chain/compact/knowledge/supervisor/coding), proceed_once, kein YOLO.
- **QUALITY** 163 Runs: Produktiv-Kandidat **64K** (Tool 10/10, Coding 10/10, …); 40K tote Drift-Zone; kein Cutover — `local-quality` bleibt **16384**.
- **FAST** 61 Runs: Tool bis 96K oft PASS; KB/Supervisor schwach — `local-fast` bleibt **32768**, kein Cutover.
- Bericht: `docs/CONTEXT_BOUNDARY_DISCOVERY_2026-10-02.md`. Belege `benchmarks/context-boundary-20261002/`, `…-fast-20261003/`. Handoff/Master-Plan/Cutover-Plan aktualisiert.

## QUALITY 64K Cutover — 03.10.2026 ~09:55

- **PASS.** Produktiv `local-quality` **16384 → 65536**. `local-fast` bleibt **32768**. Smoke PASS.
- Backup `/mnt/ai-archive/backups/local-quality-64k-20261003-095519/`. Apply/Rollback: `scripts/apply-local-quality-64k.sh`, `scripts/rollback-local-quality-64k.sh`.
- Kein FAST-Cutover. Kein YOLO. `trust: false`.

## Post-64K Boundary — 03.10.2026 15:16

- Bench-only 80/88/96 + multi_hop / härteres Coding. **88 Runs**, 78 Pass / 10 Fail.
- 80K stark, 88/96 mehr Drift (KB/MultiHop). **Kein Cutover über 64K.**
- Bericht: `docs/POST64K_BOUNDARY_2026-10-03.md`. Belege `benchmarks/context-boundary-post64k-20261003/`.

## Fair 64K vs 80K — 03.10.2026 19:07

- Gleicher aktueller Fixture, 5 Läufe × 6 Suites × 2 Kontexte. **60 Runs**, 52 Pass / 8 Fail.
- 80K etwas stärker, beide nicht „alle Suites zuverlässig“. Viele Fails = leerer Session-Start; echt: 64K Coding-Drift, 80K doppelter Supervisor-Agent.
- **Kein 80K-Cutover.** Produktiv bleibt **65536** / FAST **32768** (live verifiziert).
- Bericht: `docs/FAIR_64_VS_80_2026-10-03.md`. Belege `benchmarks/context-boundary-fair-64vs80-20261003/`. Master-Plan: Context Boundary bleibt aktiv.

## Scoped Shell + Leiter 80/88/96 — 04.10.2026 04:03

- Isoliertes `QWEN_HOME` + Serve :4171, Allow nur pytest/unittest, fail-closed Voter. Proben PASS. Produktionsshell blieb aus.
- Mit Shell: Coding 64K **3/5**, 80K **5/5**. Ohne Shell: 80K Tool/Coding **4/5**, Rest 5/5; 88K Coding **3/5** MultiHop **4/5**; 96K Tool/Coding **4/5**, Rest 5/5.
- 102 Versuche / 100 gültig. Shell hilft 80K-Coding sichtbar, nicht allgemein (64K mit Shell 3/5). Fair-Bar nicht erfüllt.
- **Kein Cutover.** Produktiv bleibt **65536** / FAST **32768**, `model.name=local-fast` (live). :4171 down.
- Bericht: `docs/NIGHT_SCOPED_SHELL_LADDER_2026-10-04.md`. Belege `benchmarks/context-boundary-night-20261003/`.

## Realistic 80K Coding — 04.10.2026 09:57

- Nur **80K**, drei Multi-File-Tasks (order_service, config_merge, ledger_repair), je 3 Runs, scoped Shell :4171. Grading: FAIL→PASS + PASS→PASS + hidden MUSTs (SWE-lite).
- Harness-Fix: Task-Workspaces unter `/srv/ai/workspaces/realistic-80k-20261004/runs/` (Session-CWD `/srv/ai/workspaces`).
- Ergebnis: config_merge **3/3** resolved; ledger_repair **2/3**; order_service **0/3** (Run 1 echter MUST-Fail; Runs 2–3 Tool-Abort, nicht MUST-Muster).
- Nachklassifikation: `must_pattern.order_service` → false; `DECISION_CORRECTION.json`.
- Nightly-Diagnose (isoliert `0.24.7-nightly.20261003`, order_service r2–3): tool_runtime 0; r2 resolved, r3 must_loss wie r1. PR #12987 (cross-directory shell) passt nicht zu `file_path`-Schema-Fehler. Prod-Qwen unverändert.
- Bericht: `docs/REALISTIC_80K_QWEN_NIGHTLY_DIAG_20261004.md`.
- **`cutover: false`.** Produktiv bleibt **65536** / FAST **32768**.
- Bericht: `docs/REALISTIC_80K_CODING_2026-10-04.md`. Belege `benchmarks/realistic-80k-20261004/`.

## Retry leere Starts — 03.10.2026 21:47

- Harness: 45s-Abort während 27B-Load. Warmup + 150s-Fenster + ein verlinkter Retry nur bei Empty.
- 32 Versuche / 30 gültig. Compact 64K 5/5. Coding 4/5 auf 64K **und** 80K (liest, editiert nicht). MultiHop 80K 5/5, 64K 4/5. Supervisor 80K 5/5 (Doppel-Agent nicht reproduziert).
- **Kein 80K-Cutover.** Produktiv bleibt **65536** / FAST **32768** (live).
- Bericht: `docs/RETRY_EMPTY_START_2026-10-03.md`. Belege `benchmarks/context-boundary-retry-empty-20261003/`. Fair-Rohdaten unberührt.

## Bewusst offen

High-Resolution Image Pipeline (1536, 2K, 4K) bleibt deferred. QUALITY über 64K erst nach erfüllten Fair-Kriterien. Optional Shell mit Einzelfreigabe (kein YOLO). Autonomous Software Development (Master-Plan 5) noch nicht gestartet.
