# Context Boundary Discovery — Abschlussbericht (GPT-Handoff)

Stand: **2026-10-03 ~07:05** (Kette beendet). **Kein Cutover ausgeführt.**

Produktiv unverändert:

| Alias | Modell | `num_ctx` |
|-------|--------|-----------|
| `local-quality` | Qwen3.8 27B | **16384** |
| `local-fast` | Qwen3.5 9B | **32768** |

Security unverändert: `trust: false`, `approvalMode: default`, kein YOLO.  
Runtime: Ollama **0.35.0**, Qwen Code **0.24.7**, ComfyUI **0.38.0**, MCP **1.7.0 / 33**.

---

## 1. Ziel

Höchste Kontextgröße, bei der das jeweilige Modell **reproduzierbar, stabil und agentisch korrekt** arbeitet — nicht nur technisch lädt.

Zustände: A technisch unmöglich · B agentisch instabil · C stabil (mehrere Runs) · D produktiv belastbar (lange Tool-/Coding-Ketten).

---

## 2. Harness

| | QUALITY (27B) | FAST (9B) |
|--|---------------|-----------|
| Skript | `benchmarks/context_boundary_discovery.py` | gleiches Skript, `CBD_FAMILY=fast` |
| Belege | `benchmarks/context-boundary-20261002/` | `benchmarks/context-boundary-fast-20261003/` |
| Runs | **163** | **61** |
| Votes | `proceed_once` only | gleich |
| Cutover | nein | nein |

Suites: **tool_chain · compact · knowledge · supervisor · coding**.

Additive Bench-Aliase: `bench-qwen38-27b-{32..80}k`, `bench-qwen35-9b-{32,48,64,80,96}k`.

---

## 3. QUALITY-Matrix (Pass/N)

| Context | Tool | Compact | KB | Supervisor | Coding | Drift Σ |
|--------:|------|---------|----|------------|--------|--------:|
| 32K | 4/5 | 3/3 | 2/3 | 3/3 | 3/3 | 2 |
| 40K | **0/10** | — | — | — | — | **10** |
| 48K | 5/10 | 7/10 | 3/3 | 3/3 | 3/3 | 5 |
| 56K | 5/5 | 7/10 | 3/3 | 3/3 | 3/3 | 3 |
| **64K** | **10/10** | **9/10** | **5/5** | **5/5** | **10/10** | **1** |
| 72K | 8/10 | 3/3 | 2/3 | 3/3 | 3/3 | 3 |
| 80K | 5/5 | 5/5 | 2/3 | 2/3 | 5/5 | 2 |

### QUALITY — Boundary

| Größe | Wert |
|-------|------|
| Highest Technically Working | **80K** (Tool/Coding/Compact oft stark) |
| Highest Stable / Productive candidate | **64K** |
| Nicht empfohlen | **40K** (tote Drift-Zone), **48K** (Tool/Compact wackelig) |

**Warum 40K schlechter als 64K?** Nach großem `memory_load` greift Compact zu früh (wenig Headroom) → leere/schlechte Summary → Doppel-`memory_load` / Abbruch. Höheres Limit = mehr Luft für dieselbe Workload. Kein OOM-Beweis gegen 64K.

**Cutover-Empfehlung QUALITY:** bei Freigabe **64K** (`num_ctx` + Settings `contextWindowSize`). Bis dahin **16384**.

---

## 4. FAST-Matrix (Pass/N)

| Context | Tool | Compact | KB | Supervisor | Coding | Drift Σ |
|--------:|------|---------|----|------------|--------|--------:|
| 32K (produktiv) | 4/5 | 3/3 | **0/3** | 2/3 | 3/3 | 5 |
| 48K | **0/5** | — | — | — | — | 5 |
| 64K | 5/5 | 2/3 | 1/3 | 2/3 | 3/3 | 4 |
| 80K | 5/5 | 2/3 | — | — | 3/3 | 1 |
| 96K | 5/5 | 3/3 | — | — | 3/3 | 0 |

### FAST — Boundary

| Größe | Wert |
|-------|------|
| Highest Technically Working (Tool) | **96K** |
| Productive candidate für Cutover | **keiner** — KB/Supervisor schwach; 48K Tool tot |
| Empfehlung | **`local-fast` bei 32K belassen** |

---

## 5. Abschlussfragen (QUALITY)

> Bis zu welchem Context Window können wir `local-quality` betreiben, ohne dass Agentic-Verhalten gegenüber der niedrigeren stabilen Stufe relevant schlechter wird?

**Antwort aus den Daten: 64K** ist der beste belegte Kandidat (Zustand D-nah). 56K nahe dran, aber Compact schwächer. 72K/80K mehr Drift.

Context Boundary Discovery für QUALITY: **Datenlage ausreichend für Freigabe-Entscheidung.**  
FAST: **kein Cutover**; Discovery für FAST abgeschlossen ohne Produktiv-Empfehlung >32K.

---

## 6. Nächste Schritte (nur nach Freigabe)

1. Explizite Freigabe für QUALITY **64K** Cutover (oder bewusst bei 16K bleiben)
2. Apply/Rollback-Skripte analog `apply-local-quality-16k.sh` / `rollback-local-quality-16k.sh` für 64K
3. `local-quality` Modelfile `num_ctx` + Qwen Settings `contextWindowSize` umbiegen
4. Default-Agent bleibt `local-fast` / 32K
5. **Nicht** Master-Plan „Autonomous Software Development“ starten, bevor Cutover entschieden ist — oder bewusst Discovery schließen und weiter

## 7. Nicht tun

- Kein automatischer Cutover
- Kein YOLO / `trust: true`
- Keine Capability entfernen „nur für weniger Tokens“
- 40K/48K nicht als QUALITY-Ziel

## 8. Belege

Komplettpaket für GPT (Docs+Benchmarks kopiert): [`docs/gpt-handoff-2026-10-03/`](gpt-handoff-2026-10-03/).


- QUALITY: `benchmarks/context-boundary-20261002/{results.jsonl,summary.json,REPORT.md}`
- FAST: `benchmarks/context-boundary-fast-20261003/{results.jsonl,summary.json,REPORT.md}`
- Frühere Leiter: `benchmarks/quality-context-ladder-20261002/`
- API-Probe: `benchmarks/quality-context-probe-20261002/`
