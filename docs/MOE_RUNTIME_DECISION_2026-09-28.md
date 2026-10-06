# MoE Runtime Decision — 2026-09-28

Ziel: **Qwen3-Coder-30B-A3B** (GGUF) **CPU-only** benchmarken, ohne die RTX 5080 für diese Inferenz zu belegen.

## Optionen

| Runtime | CPU-only Kontrolle | MoE-Support | Konflikt mit GPU-Agent | Aufwand |
|---------|--------------------|-------------|------------------------|---------|
| **llama.cpp** (v0.5.0 / b11146) | Hoch (`-ngl 0`) | Gut | Gering (eigener Prozess) | Installiert |
| **Ollama** | Mittel | Vorhanden, `MAX_LOADED_MODELS=1` | Hoch | Fallback |

## Entscheidung

**llama.cpp CPU-only** — umgesetzt und gemessen.

## Installiert (28.09.2026)

llama.cpp **v0.5.0 / b11146** CPU-only: `/srv/ai/apps/llama.cpp-0.5.0/` — siehe [`LLAMA_CPP_CPU_RUNTIME_2026-09-28.md`](LLAMA_CPP_CPU_RUNTIME_2026-09-28.md). Kein systemd.

## Quantisierung (32 GB RAM) — reale HF-Dateien

Quelle: `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF` (Apache-2.0).

| Quant | Datei | Größe | SHA256 | Status |
|-------|-------|-------|--------|--------|
| **Q4_K_S** | `…-Q4_K_S.gguf` | **17.46 GB** | `56a7d007…864db4` | **Downloaded + verified** |
| Q4_K_M | `…-Q4_K_M.gguf` | 18.56 GB | `fadc3e5f…088ad` | Nicht geladen |

Zielpfad: `/srv/ai/models/gguf/qwen3-coder-30b-a3b/`

## Messergebnisse (Kurz)

Details: [`benchmarks/moe_cpu_2026-09-28/RESULTS.md`](../benchmarks/moe_cpu_2026-09-28/RESULTS.md).

| Szenario | Gen t/s | RAM peak | Swap peak | VRAM |
|----------|---------|----------|-----------|------|
| CPU solo 4K t=16 | ~23 | ~22 GB | ~10 GB | ~1.6–2 GB (idle) |
| CPU Suite avg | ~21.5 | ~21 GB | hoch | ~1.7 GB |
| GPU local-fast Suite avg | ~118 | ~6.8 GB | — | ~8.9 GB |
| Parallel CPU+GPU | 21.8 / 124 | ~21.5 GB | ~10 GB | ~8.9 GB |
| CPU 8K smoke | 16 | ~20 GB | **~18 GB** | ~1.7 GB |

## Schlussfolgerung

- CPU-MoE + GPU-Agent **technisch realistisch** auf diesem Host.
- 32 GB RAM → **Swap-Druck**; Q4_K_S besser als Q4_K_M für Reserve.
- MoE geeignet für Planner/Review/Architecture/Zweitmeinung; Coding-Hauptpfad bleibt **`local-fast` GPU**.
- **Kein** produktiver Supervisor-Cutover in dieser Phase.
