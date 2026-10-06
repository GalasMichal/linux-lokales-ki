# Update Check — 2026-09-28

Quellen: GitHub Releases (stable), npm `@qwen-code/qwen-code`, Firecrawl-Scrapes unter `.firecrawl/20260928-*`.  
**Kein Cutover in dieser Datei.** Installation nur nach ausdrücklicher Freigabe (sudo / Container-Pull / große Downloads).

| Komponente | Installiert | Stabil verfügbar | Delta | Empfehlung |
|------------|-------------|------------------|-------|------------|
| Ollama | 0.34.2 | **0.34.4** | +2 Patch | **Sinnvoll**, Cache+Skript bereits da. Braucht **sudo**. Nach Install: volle Regression. |
| Qwen Code | 0.24.2 | **0.24.6** (npm latest; 0.24.5 Cache vom 25.09. veraltet) | +4 Patch | **Sinnvoll nach Ollama-PASS**. Isoliert analysieren (Patches portieren). Kein Nightly. |
| Open WebUI | 0.11.0 (Container `…:main`) | **0.11.4** | +0.0.4 | **Vorsichtig**. Image-Tag `:main` ist floating. Pin empfohlen. Skills/AGENTS erst nach Release-Notes lesen. |
| llama.cpp | fehlt | **v0.5.0** | neu | **Für CPU-MoE empfohlen**, noch nicht installiert. Build/Binary braucht Freigabe. |
| local-tools MCP | 1.6.0 / 32 | — | — | Kein Versionsbump nötig für MoE-Phase. |

## Breaking / Hinweise

### Ollama 0.34.4
- Structured outputs / thinking models schneller; Fix „model not found“; llama.cpp/XGrammar Update.
- Host-Override unverändert lassen (`MAX_LOADED_MODELS=1`, localhost).

### Qwen Code 0.24.6
- Gegenüber 0.24.2: mehrere Stable-Schritte (0.24.3–0.24.6). Host-Patches (ToolSearch, Registry, Git-Omit, Compact Ledger) waren in **0.24.5 Stock** noch nötig; Anchors passten. **0.24.6 muss neu isoliert geprüft werden** (nicht blind 0.24.5-Port).
- Cache 0.24.5 reicht nicht mehr als Ziel-Release.

### Open WebUI 0.11.4
- Container läuft auf Tag `:main` → unkontrollierte Drifts möglich.
- Vor Update: Image-Digest pinnen, Backup von `/srv/ai/apps/open-webui/data`, Skills/AGENTS.md Features gegen aktuelle Docs prüfen.
- **Heute nicht updaten**, bis Freigabe + Pin-Strategie.

### llama.cpp v0.5.0
- MoE-Optimierungen in Release Notes (CUDA/Metal/Vulkan/OpenCL u.a.).
- Für **CPU-only** MoE: neuer Build/Binary mit CPU-Backend; `n-gpu-layers 0` / kein CUDA-Gerät für den Benchmark-Prozess.

## Durchführung 28.09.2026

| Update | Status |
|--------|--------|
| Ollama → 0.34.4 | **DONE / PASS** (Regression local-fast/quality) |
| Qwen → 0.24.6 | **DONE / PASS** (Patches neu portiert, nicht blind) |
| Open WebUI → 0.11.4 | **NICHT** — nur Prepare [`OPEN_WEBUI_PREPARE_2026-09-28.md`](OPEN_WEBUI_PREPARE_2026-09-28.md) |
| llama.cpp v0.5.0 CPU | **DONE** (prebuilt b11146 ubuntu-x64) [`LLAMA_CPP_CPU_RUNTIME_2026-09-28.md`](LLAMA_CPP_CPU_RUNTIME_2026-09-28.md) |
| GGUF Qwen3-Coder-30B-A3B | **BLOCKED: Freigabe Download** |
