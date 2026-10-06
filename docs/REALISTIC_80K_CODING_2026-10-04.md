# Realistic 80K Coding — 04.10.2026

Praxisnahe Multi-File-Aufgaben (SWE-bench-lite / Aider-Stil) **nur 80K** (`bench-qwen38-27b-80k`, `num_ctx=81920`). Produktiv `local-quality` während des Tests **65536**; Cutover nur bei `DECISION.json` → `cutover: true`.

Belege: `benchmarks/realistic-80k-20261004/`  
Tasks: `benchmarks/realistic_80k_tasks/` (order_service, config_merge, ledger_repair)  
Harness: `benchmarks/realistic_80k_coding.py`, Orchestrator `benchmarks/run_realistic_80k.sh`

Fertig: **04.10.2026 09:57 +0200**. 9 Läufe (3 Tasks × 3 Runs), 9 gültig, keine Empty-Starts.  
**Kein 80K-Cutover.** `DECISION.json`: `cutover: false`.

## Methode

- **Resolved** (wie SWE-bench): sichtbare Tests (FAIL→PASS) **und** versteckte PASS→PASS **und** versteckte MUST-Spezifikationen.
- Isoliertes `QWEN_HOME` + Serve **:4171** + fail-closed Voter (nur `python3 -m pytest|unittest`). Kein YOLO, `trust: false`, `approvalMode: default`. `~/.qwen/settings.json` nur `model.name=local-fast` am Ende.
- Warmup 80K-Bench-Alias vor jedem Run. Scoped Shell wie Nachtleiter (`docs/NIGHT_SCOPED_SHELL_LADDER_2026-10-04.md`).

### Harness-Fix (Workspace)

Erster Start scheiterte mit `workspace_mismatch`: Serve `--workspace /srv/ai/workspaces`, Sessions verlangten `.agent/tmp/realistic-80k/…`.

Anpassung: Session-CWD `/srv/ai/workspaces`; Task-Arbeitskopien unter  
`/srv/ai/workspaces/realistic-80k-20261004/runs/<task>-r<N>`.  
Danach normale Tool-Nutzung (pytest, read/edit).

## Ergebnis je Task (resolved = alle drei Test-Stufen grün)

| Task | resolved | must_loss | agent / regression | Anmerkung |
|------|:--------:|:---------:|:-------------------:|-----------|
| **config_merge** | **3/3** | 0 | 0 | stabil (~2–4 min/Run) |
| **ledger_repair** | **2/3** | 0 | 1× sichtliche Tests rot (Run 2, Parser nicht gefixt) | Run 1+3 ok |
| **order_service** | **0/3** | **3** | 0 | Run 1: sichtlich grün, **MUST** rot (Mitgliedspreis); Run 2–3 sichtlich rot / Tool-Fehler |

### order_service (Kernproblem)

**Run 1 — echter MUST-Verstoß (Modell/Logik):** Sichtliche Tests grün. Katalog wird **nicht** mutiert (`catalog._prices` unverändert; `apply_member_price` schreibt nur in `Checkout._member`). `total()` berücksichtigt `_member` jedoch nicht → `119` statt `59` in `test_member_price_this_cart_only` (`hidden/test_musts.py`). Das ist fehlende Mitgliedspreis-Logik, nicht „Katalog dauerhaft geändert“ (der ursprüngliche Fixture-Bug).

**Run 2–3 — ungültig für MUST-Bewertung (Tool-Runtime):** Modell sendete `read_file` mit JSON-Key **`path`** statt **`file_path`** (Telemetrie: `invalid_tool_params`, `execution_status: not_started`). Qwen 0.24.7 stable: `LOOP_DETECTED` / `invalid_tool_params_stagnation` → Turn-Ende. **Kein** Verzeichnisgrenzen-Problem (absolute Pfade unter `/srv/ai/workspaces/...` wie Run 1). MUST-rot am unveränderten Fixture — **nicht** als MUST-Muster zählen.  
→ Isolierte Nightly-Diagnose: `docs/REALISTIC_80K_QWEN_NIGHTLY_DIAG_20261004.md`, Belege `benchmarks/realistic-80k-nightly-diag-20261004/`.

**Auswertungskorrektur (04.10. Nachmittag):** `classify_error` prüft jetzt `fail_to_pass` vor `must_loss`; abgebrochene Turns → `tool_runtime`. Roh-`results.jsonl` unverändert; neu: `DECISION_CORRECTION.json`, `DECISION.json` neu berechnet → `must_pattern.order_service: false` (nur 1× echter MUST-Fail).

### ledger_repair Run 2

Agent ließ `entries.py` mit Komma-Split-Bug; sichtliche pytest rot. Kein MUST-Verlust, aber kein resolved.

## Entscheidung

`benchmarks/realistic-80k-20261004/DECISION.json`:

- `task_ok`: config_merge ✓, ledger_repair ✓ (≥2/3 resolved), order_service ✗  
- `must_pattern.order_service`: **false** nach Reklassifikation (nur Run 1 echter MUST-Fail; Runs 2–3 `tool_runtime`)  
- **`cutover: false`** — Produktiv bleibt **65536** (auch ohne MUST-Muster: `order_service` 0/3 resolved)

Kriterium aus Harness: alle Kern-Tasks wiederholt grün **und** kein MUST-Muster. order_service ist `core: true` und fiel durch.

## Abgrenzung zur einfachen Coding-Fixture

Nachtleiter (eine calc-Fixture, scoped Shell): 80K **5/5**, 64K **3/5** (`docs/NIGHT_SCOPED_SHELL_LADDER_2026-10-04.md`).  
Realistische Tasks (mehr Dateien, MUST-Hidden-Tests): 80K schlägt an **order_service** fehl — längerer Kontext allein reicht nicht für zuverlässige Muss-Treue.

## Nachlauf

- Orchestrator: `=== R80 END 09:57:40 ===`, `local-fast` restored, :4171 gestoppt.
- `local-quality` live: **65536** (verifiziert nach Lauf).
- Optional `pc-keepawake` manuell beenden, wenn noch aktiv.

## Rollback (unverändert)

- QUALITY Context 64K→16K: `scripts/rollback-local-quality-64k.sh`  
- 80K-Cutover (nicht angewendet): `scripts/apply-local-quality-80k.sh` nur nach Freigabe + `cutover: true`

## Nächste Schritte (optional)

1. order_service analysieren (Prompt/MUST-Sichtbarkeit vs. Agent-Verhalten).  
2. Kein Produktions-Cutover auf 80K ohne neues PASS-Muster auf allen Kern-Tasks.  
3. Context Boundary bleibt aktiv; Master-Plan Punkt 5 weiter gesperrt.
