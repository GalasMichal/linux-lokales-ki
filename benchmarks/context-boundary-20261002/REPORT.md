# QUALITY Context Boundary — FINAL REPORT

Total runs: 163

| Context | Tool | Compact | KB | Supervisor | Coding | Drift |
|---|---|---|---|---|---|---|
| 32768 | 4/5 | 3/3 | 2/3 | 3/3 | 3/3 | 2 |
| 40960 | 0/10 | — | — | — | — | 10 |
| 49152 | 5/10 | 7/10 | 3/3 | 3/3 | 3/3 | 5 |
| 57344 | 5/5 | 7/10 | 3/3 | 3/3 | 3/3 | 3 |
| 65536 | 10/10 | 9/10 | 5/5 | 5/5 | 10/10 | 1 |
| 73728 | 8/10 | 3/3 | 2/3 | 3/3 | 3/3 | 3 |
| 81920 | 5/5 | 5/5 | 2/3 | 2/3 | 5/5 | 2 |

## Boundary
- Highest Technically Working: **81920** (Tool/Coding/Compact oft stark)
- Highest Stable / Productive candidate: **65536 (64K)** — Tool 10/10, Coding 10/10, KB/Sup 5/5, Compact 9/10
- 40K: tote Zone (0/10 Tool Drift)
- 48K/56K Compact: gemischt — nicht Prefer gegenüber 64K
- 72K/80K: brauchbar, mehr Drift bei KB/Sup/Tool

**Kein Cutover.** `local-quality` bleibt **16384** bis Freigabe.
Ended chain: 2026-10-03T06:25:08 (phase3) / full chain 07:05:38.
