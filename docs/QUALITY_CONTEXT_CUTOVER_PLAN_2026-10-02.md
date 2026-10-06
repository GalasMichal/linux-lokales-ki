# QUALITY Context Cutover — Planungs-Handoff

Stand: **2026-10-03** nach Context Boundary Discovery. **Kein Cutover ausgeführt.**

Vollständiger Boundary-Bericht: [`CONTEXT_BOUNDARY_DISCOVERY_2026-10-02.md`](CONTEXT_BOUNDARY_DISCOVERY_2026-10-02.md)

## Ausgangslage (produktiv)

- `local-quality` = Qwen3.8 27B / **16384**
- Default `local-fast` / **32768**
- Additive Bench-Aliase bis 80K (QUALITY) bzw. 96K (FAST)

## Boundary-Ergebnis (Serve Multi-Run, 163 Runs)

| Context | Bewertung |
|--------:|-----------|
| 16K (produktiv) | zu eng für schwere Agentic-Ketten (historisch flaky) |
| 32K | brauchbar, nicht bestes Gesamtbild |
| 40K | **tote Zone** — Agent-Drift |
| 48K | gemischt — nicht stabil |
| 56K | stark, Compact schwächer als 64K |
| **64K** | **Highest Productive candidate** |
| 72K/80K | technisch oft ok, mehr Drift |

**Cutover-Empfehlung:** **64K** — nur nach expliziter Freigabe.  
Bis dahin `local-quality` **16384**.

## Was vor Cutover noch fehlt

1. ~~Multi-Run Serve Suites A–E~~ — **erledigt** (siehe Boundary-Doc)
2. Apply/Rollback-Skripte für **64K** (analog 16k-Skripte)
3. Explizite Freigabe
4. Default-Modell bleibt `local-fast`

## Vorgeschlagene Reihenfolge nach Freigabe

1. Skripte `apply-local-quality-64k.sh` / `rollback-…` (oder Äquivalent)
2. `local-quality` Modelfile `num_ctx 65536` + Settings `contextWindowSize` 65536
3. Smoke Serve Memory+PDF+Vision + Coding einmal
4. Bei Problemen Rollback auf 16384

## Nicht tun

- Kein automatischer Cutover  
- Kein YOLO / `trust: true`  
- Kein Cutover auf 40K/48K  
- Kein FAST-Context-Cutover (Discovery: nicht empfohlen)
