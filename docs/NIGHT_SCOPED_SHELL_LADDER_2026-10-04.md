# Scoped Shell + Leiter 80/88/96 — Nacht 03.–04.10.2026

Nach `docs/RETRY_EMPTY_START_2026-10-03.md`. Dieselben Fixtures, Prompts und Erfolgskriterien. Neuer Ordner:

`benchmarks/context-boundary-night-20261003/`

Fertig: **04.10.2026 04:03 +0200**. 102 Versuche · 100 gültig · 2 leere Erstversuche.  
Live danach (verifiziert): `local-quality` **65536**, `local-fast` **32768**, Default `model.name=local-fast`.  
`tools.approvalMode=default`, `run_shell_command` in `tools.disabled`, `trust: false`. Kein Cutover.

## Methode

- Phase A: isoliertes `QWEN_HOME` + zweites Serve **:4171** + fail-closed Voter. Allow nur `python3 -m pytest|unittest`. Deny sudo/rm/curl/`python3 -c`/bash. Kein YOLO, kein `trust: true`, kein Schreibzugriff auf `~/.qwen` außer dem bestehenden `model.name`-Restore.
- Proben zuerst: Allow = pytest completed; Deny = Tool failed + Sentinel fehlt + Produktionsshell weiter aus. Proben **PASS** 03.10. ~22:32.
- Isolation ist QWEN_HOME + Serve + Voter, **keine** OS-Sandbox. `tools.executionSandbox` lehnt `qwen serve` ab.
- Phase B: Produktions-Serve **:4170**, Shell weiter deaktiviert. Leiter 80K / 88K / 96K × 6 Suites × 5. Bench-Aliase `bench-qwen38-27b-80k/88k/96k`.
- Harness unverändert: Warmup + 150 s + ein verlinkter Retry nur bei Empty.
- Bestehender Git-Dirt unberührt. Keepawake blieb an.

## Gültige Matrix (letzter Versuch, keine Empty-Counts)

### Mit scoped Shell (Phase A)

| Context | Coding |
|--------:|:------:|
| 65536 | 3/5 |
| 81920 | 5/5 |

### Ohne Shell (Phase B)

| Context | Tool | Compact | KB | Supervisor | Coding | MultiHop |
|--------:|:----:|:-------:|:--:|:----------:|:------:|:--------:|
| 81920 | 4/5 | 5/5 | 5/5 | 5/5 | 4/5 | 5/5 |
| 90112 | 5/5 | 5/5 | 5/5 | 5/5 | 3/5 | 4/5 |
| 98304 | 4/5 | 5/5 | 5/5 | 5/5 | 4/5 | 5/5 |

## Coding mit vs ohne Shell — ohne Überclaim

| Bedingung | 64K | 80K |
|-----------|:---:|:---:|
| Diese Nacht, scoped Shell | 3/5 | **5/5** |
| Diese Nacht, keine Shell | — | 4/5 |
| Retry-Empty 03.10., keine Shell | 4/5 | 4/5 |

80K mit Shell ist **5/5**, ohne Shell **4/5**. Das ist sichtbar, aber kein Fair-Cutover. 64K mit Shell ist **3/5** — schlechter als der letzte No-Shell-Lauf (4/5). Shell erklärt die Coding-Fails nicht allgemein.

Ohne Shell sucht Coding oft 10–15 min nach pytest/`run_shell_command`/`moe_consult`. Manche Läufe patchen trotzdem und bestehen. Fail-Muster: Agent-Drift, Timeout ~900 s, oder kein Edit.

## Klassifikation (Auswahl)

| Klasse | Was | Beispiele |
|--------|-----|-----------|
| `harness_session` | leerer Start | Compact 80K r? a1; MultiHop 88K a1 |
| `agent` | Inhalt | Tool 80K r2; Tool 96K r4 (`duplicate_tools: pdf_render`); Coding 88K r3 (~904 s); Coding 96K r1 |
| `pass` | gültig grün | Rest |

## Entscheidung

Kein Cutover über 64K. Fair-Bar „alle sechs Suites zuverlässig“ auf 80/88/96 **nicht** erfüllt (Tool und/oder Coding nicht 5/5). Compact/KB/Supervisor auf allen drei Stufen 5/5. MultiHop 96K 5/5, 88K 4/5.

Produktiv bleibt `local-quality` **65536**, `local-fast` **32768**. Shell bleibt im Arbeitsplatz aus.

Rollback 64K→16K: `scripts/rollback-local-quality-64k.sh`  
80K-Skripte liegen bereit, unbenutzt: `scripts/apply-local-quality-80k.sh`, `scripts/rollback-local-quality-80k-to-64k.sh`

## Nächster Schritt

Context Boundary bleibt aktiv. Optional Shell nur mit Einzelfreigabe (kein YOLO) — Sitzung, kein Dauerbetrieb. Master-Plan 5 erst, wenn die höchste stabile QUALITY-Stufe festliegt.

## Belege

- `benchmarks/context-boundary-night-20261003/STATUS.md`
- `benchmarks/context-boundary-night-20261003/DONE.md`
- `benchmarks/context-boundary-night-20261003/results.jsonl`
- `benchmarks/context-boundary-night-20261003/PROBES.json`
- `benchmarks/context-boundary-night-20261003/EFFECTIVE_PERMISSIONS.md`
- `benchmarks/context-boundary-night-20261003/ISOLATION.json`
