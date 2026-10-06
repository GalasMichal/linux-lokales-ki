# MoE CPU Benchmark Results — 2026-09-28

Host: Intel Core i9-14900KF (24C/32T), 32 GB RAM, RTX 5080 16 GB, Nobara.  
No subjective winner ranking. Metrics + technical observations only.

## Artifacts

- Prompts: `prompts/`
- Responses: `responses/` (+ `*.raw` / `*.full.txt` where applicable)
- Metrics JSON: `metrics/`
- Resource CSV samples: `metrics/*-resources.csv`
- Runtime settings: `SETTINGS.md`

## Model / Runtime

| Side | Stack |
|------|--------|
| **A** | `Qwen3-Coder-30B-A3B-Instruct-Q4_K_S.gguf` via llama.cpp b11146, `-ngl 0 -t 16 -c 4096`, `--jinja --reasoning off -st` |
| **B** | Ollama `local-fast` (Qwen3.5 9B Q4_K_M, 32K ctx config), GPU, `think:false`, `num_predict=256` |

SHA256 A-file: `56a7d00783419bcb0ae566253c371bcb3678261bb79881a553539f5679864db4` (verified).

## Thread tuning (short smoke)

| threads | prompt t/s | gen t/s | wall_s | ram_peak_mb | swap_peak_mb |
|---------|------------|---------|--------|-------------|--------------|
| 16 | 32.7 | 23.1 | 45.4 | 21746 | 10099 |
| 24 | 40.1 | 18.8 | 63.5 | 22325 | 8930 |
| 32 | 9.1 | 9.4 | 69.4 | 20547 | 15378 |

Chosen: **16 threads**.

## Suite A vs B (n_predict=256, five identical prompts)

| Test | A wall_s | A prompt t/s | A gen t/s | A RAM peak | A VRAM peak | B wall_s | B prompt t/s | B gen t/s | B RAM peak | B VRAM peak | B GPU util peak |
|------|----------|--------------|-----------|------------|-------------|----------|--------------|-----------|------------|-------------|-----------------|
| 01 code review | 72.8 | 40.2 | 21.3 | 21627 | 1749 | 18.8 | 1498 | 117.5 | 6685 | 8909 | 90 |
| 02 implementation | 58.3 | 55.9 | 22.3 | 21244 | 1726 | 2.9 | 1561 | 116.6 | 6760 | 8909 | 34 |
| 03 architecture | 63.5 | 49.4 | 22.0 | 21554 | 1718 | 4.4 | 1553 | 117.2 | 6830 | 8909 | 88 |
| 04 debugging | 67.1 | 70.2 | 22.6 | 21614 | 1714 | 4.1 | 1916 | 119.5 | 6873 | 8917 | 89 |
| 05 supervisor | 80.9 | 16.5 | 19.5 | 20119 | 1722 | 4.1 | 1580 | 119.5 | 6924 | 8919 | 89 |
| **Average** | **68.5** | **46.4** | **21.5** | **21232** | **1726** | **6.9** | **1622** | **118.1** | **6814** | **8913** | **78** |

Swap during A often **~11–16 GB**. B after unload leaves GPU idle again.

## CPU-only smoke / GPU independence

Solo A (4K): VRAM stayed **~1.6–2.1 GB**, GPU util peak mostly **≤9%** (desktop noise). No MoE weights on CUDA package (`NO_CUDA_LIBS`). `-ngl 0` enforced.

## Parallel CPU + GPU

Concurrent: A architecture (CPU MoE) + B implementation (`local-fast` GPU).

| Metric | Value |
|--------|--------|
| cpu_rc / gpu_rc | 0 / 0 |
| CPU wall / gen t/s | 67.2 s / **21.8** |
| GPU wall / gen t/s | 4.2 s (job) / **124.4** |
| Combined RAM peak | 21528 MB |
| Combined swap peak | 10029 MB |
| Combined VRAM peak | **8917 MB** (local-fast on GPU) |
| GPU util peak | **87%** |

Observation: Ollama/local-fast continued normal GPU inference while MoE ran on CPU/RAM. Host remained usable; swap elevated.

## 8K context (CPU only, same smoke prompt, t=16, n=64)

| ctx | wall_s | prompt t/s | gen t/s | ram_peak_mb | swap_peak_mb | vram_peak_mb |
|-----|--------|------------|---------|-------------|--------------|--------------|
| 4096 (tune-t16) | 45.4 | 32.7 | 23.1 | 21746 | 10099 | 2057 |
| 8192 | 81.6 | 7.0 | 16.0 | 20456 | **18339** | 1690 |

8K: slower generation, much higher swap. No OOM. Still GPU-idle during solo.

## Technical observations (not a winner pick)

1. **Throughput gap:** B ~5–6× gen tokens/s vs A under these limits; wall time gap larger due to MoE load + swap.
2. **Memory:** A needs ~20–22 GB RAM peak and routinely uses multi‑GB swap on 32 GB host. Parallel works but is RAM-stressed.
3. **GPU role split works technically:** CPU MoE does not occupy the RTX 5080; GPU agent can run concurrently.
4. **Answer quality:** Both produced structured, on-topic answers for all five tasks (see `responses/`). No automated quality score.
5. **Q4_K_M (~18.56 GB file):** Not downloaded. Given Q4_K_S already swaps heavily, Q4_K_M would reduce RAM reserve further; Q4_K_S is the more practical first quant on 32 GB for parallel CPU+GPU.

## Supervisor-role technical fitness (measurements-based)

| Role | Fit on this host with Q4_K_S CPU | Notes |
|------|----------------------------------|-------|
| Planner / Architecture | Technically usable | ~20 t/s, high latency vs GPU; OK for offline planning |
| Reviewer / second opinion | Technically usable | Same; parallel with GPU coder demonstrated |
| Supervisor decompose | Technically usable | Test 05 produced structured breakdown |
| Fast implementation / interactive coding | Poor fit vs local-fast | Prefer GPU `local-fast` (~118 t/s here) |

No productive Supervisor cutover performed.
