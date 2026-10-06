# Chosen llama.cpp settings — 2026-09-28

Host: i9-14900KF (8P+16E, 32 threads), 32 GB RAM, RTX 5080 16 GB

Smoke matrix (ctx=4096, n=64, -ngl 0, Q4_K_S):

| threads | prompt t/s | gen t/s | wall_s | ram_peak_mb | swap_peak_mb | vram_peak_mb |
|---------|------------|---------|--------|-------------|--------------|--------------|
| 16 | 32.7 | **23.1** | 45.4 | 21746 | 10099 | ~2 GB idle |
| 24 | 40.1 | 18.8 | 63.5 | 22325 | 8930 | ~1.6 GB |
| 32 | 9.1 | 9.4 | 69.4 | 20547 | 15378 | ~1.8 GB |

**Chosen for benchmarks: `-t 16 -c 4096 -ngl 0 --jinja --reasoning off -st`**

Reason: best generation tokens/s and shortest wall among tested; 32 threads regress hard (contention + swap). Leave hyperthreads/E-core headroom for host responsiveness.
