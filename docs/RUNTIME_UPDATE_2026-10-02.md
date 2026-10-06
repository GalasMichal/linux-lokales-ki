# Runtime-Update 2026-10-02

Backup: `/mnt/ai-archive/backups/runtime-update-20261002-084919/`  
Belege: `benchmarks/runtime-update-20261002-084919/`  
Kein Git-Push. Kein YOLO. `trust: false`. `approvalMode: default`.

## Ist → Soll (verifiziert)

| Komponente | Vorher (live) | Ziel (GitHub Stable) | Nachher |
|------------|---------------|----------------------|---------|
| Ollama | **0.34.4** | **0.35.0** (nicht 0.35.1-rc2) | **0.35.0** |
| Qwen Code | **0.24.6** + Patches | **0.24.7** | **0.24.7** + Patches `patches/qwen-code/0.24.7/` |
| ComfyUI | **0.37.0** | **0.38.0** | **0.38.0** + `--disable-comfy-compiler` |
| MCP | 1.7.0 / 33 | unverändert | 1.7.0 / 33 |
| local-fast | Qwen3.5 9B / 32K | unverändert | unverändert |
| local-quality | Qwen3.8 27B / 16K | unverändert | unverändert (kein Cutover) |

Quellen: GitHub Releases `ollama/ollama` `v0.35.0`, `QwenLM/qwen-code` `v0.24.7`, `comfyanonymous/ComfyUI` `v0.38.0` (alle `prerelease=false`).

## Overrides / Sicherheit (unverändert)

- Ollama Override-SHA `7fb44d5f…` — localhost, `MAX_LOADED_MODELS=1`, Flash Attention, KV `q8_0`, Keep-Alive 5m, Parallel 1
- Default-Modell `local-fast`, QUALITY Context Settings 16384
- Lazy Tool Loading (`alwaysLoadTools: false`), Compact State Ledger, Knowledge Base, Supervisor `maxSubagentDepth=1`
- Agent Team aus, Computer Use aus

## Phase C — Ollama 0.35.0

- Binary SHA `0b0650a962dda61ec0598141ea11e3b688d225e926c9c00bc2c299d0ed34c4f8`
- Backup unter `…/ollama/`
- Regression: Mini-Generate FAST/QUALITY OK; Tool-Calls `/api/chat` + `/v1` beide Modelle PASS; MCP memory/PDF/render PASS; Vision-QA lief (sparse-PDF „empty_page“ erwartet); live_mcp_smoke PASS

## Phase D — Qwen Code 0.24.7

- Tarball SHA `5f1953eac22a413348c36a6eba542f93915f90d3c61ecbeff1ee32bbacfb640a`
- Keep-Tree: `/srv/ai/apps/qwen-code/lib/qwen-code.0.24.6`
- Patches portiert (nicht blind):
  - ToolSearch MCP-Kurzname (`tool-search-AO4V2HFN.js`) — neu: `collectCandidates(bindings)`
  - Registry `resolveMcpShortToolName` (`chunk-AN36BHDM.js`)
  - Git-Snapshot-Omit (`chunk-L3A6AVZE.js`)
  - Compact State Ledger (gleicher Registry-Chunk)
- `--check` OK; Settings unverändert
- Rollback: `scripts/rollback-qwen-0.24.7.sh`

## Phase E — ComfyUI 0.38.0

- Isoliert FLUX 512 PASS (~35 s, Peak ~13600 MiB)
- Edit 512 **ohne** Compiler-Flag: FAIL `aimdo memory compile error` (Release: Qwen-Image-2.1 KV/Compile)
- Edit 512 **mit** `--disable-comfy-compiler`: PASS (~35 s)
- Produktiv-Unit mit diesem Flag; Output-Pfad unverändert
- Workplace `COMFY_INPUT` → `/srv/ai/apps/ComfyUI-0.38.0/input` (sonst staged Edit-Dateien unsichtbar)
- MCP `generate_image` PASS; `edit_image` PASS nach Input-Fix
- Rollback: `scripts/rollback-comfyui-0.38.0.sh`

## Context-Probe local-quality (additive, kein Cutover)

Skript: `benchmarks/quality_context_probe_20261002.py`  
Ergebnis: `benchmarks/quality-context-probe-20261002/summary.json`

| Alias | Context | Cold/Tool/Filled | Artefakte |
|-------|---------|------------------|-----------|
| bench-qwen38-27b-16k | 16384 | PASS | keine |
| bench-qwen38-27b-24k | 24576 | PASS | keine |
| bench-qwen38-27b-32k | 32768 | PASS | keine |

**highest_ok_ctx = 32768** in diesem Probe (Mini-OK, Tool-Call, ~55 % Filler + Marker).  
**Produktives `local-quality` bleibt 16384.** Kein automatischer Cutover.

## Serve-E2E Context-Leiter (danach, 02.10. ~15:44–16:09)

Skript: `benchmarks/quality_context_ladder_serve_e2e.py`  
Ergebnis: `benchmarks/quality-context-ladder-20261002/summary.json`  
Plan: [`QUALITY_CONTEXT_CUTOVER_PLAN_2026-10-02.md`](QUALITY_CONTEXT_CUTOVER_PLAN_2026-10-02.md)

| Context | Serve-E2E | Kurz |
|---------|-----------|------|
| 16K | FAIL | zu eng / flaky (Doppel-Tools / Compact-Overflow) |
| 24K | PASS | volle Kette, je 1× |
| 32K | PASS | zuverlässiges Maximum |
| 40K | FAIL | Agent-Drift — Grenze „zu hoch“ |
| 48K | einmal PASS | nicht als stabile Grenze |

Ressourcen: VRAM ~14 GB, Swap ~4.2–4.5 GB — kein OOM.  
Frühe Leiter: Cutover höchstens 32K (vor Multi-Run Boundary).

## Context Boundary Discovery (02.–03.10.2026) — ABGESCHLOSSEN

Vollbericht: [`CONTEXT_BOUNDARY_DISCOVERY_2026-10-02.md`](CONTEXT_BOUNDARY_DISCOVERY_2026-10-02.md)

| Familie | Runs | Produktiv-Kandidat | Produktiv jetzt |
|---------|-----:|--------------------|-----------------|
| QUALITY 27B | 163 | **64K** | bleibt **16384** |
| FAST 9B | 61 | keiner (>32K) | bleibt **32768** |

Belege: `benchmarks/context-boundary-20261002/`, `benchmarks/context-boundary-fast-20261003/`.  
**Kein Cutover.**

## Rollback-Kurzpfade

1. Ollama: Binary+lib aus Backup `…/ollama/` zurückkopieren (sudo), Override unverändert lassen
2. Qwen: `scripts/rollback-qwen-0.24.7.sh` → Keep 0.24.6
3. ComfyUI: `scripts/rollback-comfyui-0.38.0.sh`

## Bekannte Einschränkungen

- ComfyUI 0.38 braucht `--disable-comfy-compiler` für Qwen-Image-2.1 Edit auf diesem Host (RTX 5080)
- Boundary: QUALITY 40K tot; Produktiv-Kandidat 64K — Cutover nur mit Freigabe; FAST bleibt 32K
- Open WebUI unverändert 0.11.0
