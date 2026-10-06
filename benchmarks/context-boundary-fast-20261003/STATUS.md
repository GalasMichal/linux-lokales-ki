# FAST Context Boundary — FINAL REPORT

Total runs: 61

| Context | Tool | Compact | KB | Supervisor | Coding | Drift |
|---|---|---|---|---|---|---|
| 32768 | 4/5 | 3/3 | 0/3 | 2/3 | 3/3 | 5 |
| 49152 | 0/5 | — | — | — | — | 5 |
| 65536 | 5/5 | 2/3 | 1/3 | 2/3 | 3/3 | 4 |
| 81920 | 5/5 | 2/3 | — | — | 3/3 | 1 |
| 98304 | 5/5 | 3/3 | — | — | 3/3 | 0 |

## Boundary
- Productive `local-fast` bleibt **32768**
- Tool-Chain technisch bis **96K** (5/5); Coding oft PASS
- KB/Supervisor und **48K Tool 0/5** schwach — kein FAST-Cutover empfohlen
- 32K Baseline gemischt (KB 0/3)

**Kein Cutover.** Ended: 2026-10-03T07:05:38.
