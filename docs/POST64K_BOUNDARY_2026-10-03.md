# Post-64K Context Boundary — 2026-10-03

Nach produktivem QUALITY-Cutover auf **65536**. Bench-only höher (80/88/96). Kein weiterer Cutover.

## Ergebnis

| Context | Tool | Compact | KB | Supervisor | Coding | MultiHop | Drift |
|--------:|:----:|:-------:|:--:|:----------:|:------:|:--------:|------:|
| 81920 | 3/3 | 5/5 | 4/5 | 5/5 | 5/5 | 5/5 | 1 |
| 90112 | 5/5 | 4/5 | 5/5 | 4/5 | 4/5 | 3/5 | 5 |
| 98304 | 5/5 | 5/5 | 3/5 | 5/5 | 4/5 | 4/5 | 4 |

- **88 Runs** · 78 Pass / 10 Fail  
- Fertig: 2026-10-03 15:16:38 +0200  
- Härter: multi-file Coding-Fixture + Suite `multi_hop`

## Empfehlung

- Produktiv **64K behalten**
- 80K technisch stark, aber kein Cutover ohne Freigabe
- 88/96 mehr Drift (besonders KB / MultiHop) — nicht produktiv

## Belege

- `benchmarks/post64k/DONE.md`
- `benchmarks/post64k/results.jsonl`
- `benchmarks/post64k/runs/*.json`
