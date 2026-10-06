# Retry leere Starts + echte Fails — 2026-10-03

Nach `docs/FAIR_64_VS_80_2026-10-03.md`. Alte Fair-Rohdaten unberührt. Neuer Ordner:

`benchmarks/context-boundary-retry-empty-20261003/`

Fertig: **21:47 +0200**. 32 Versuche · 30 gültig.  
Live danach (verifiziert): `local-quality` **65536**, `local-fast` **32768**. Kein Cutover.

## Methode

- Dieselben Fixtures wie Fair (multi-file Coding, `multi_hop`). Prompts/Erfolgskriterien unverändert.
- Harness: Modell-Warmup vor dem Serve-Prompt; Cold-Load-Abbruch 45 s → 150 s; **ein** Retry nur bei eindeutig leerem Start (0 Tools, 0 Votes, ~20–80 s, kein `prompt_error`).
- Erstversuch und Retry als getrennte, verknüpfte Datensätze (`*-a1.json` / `*-a2.json`, `retry_of`, `error_class`).
- Suites: 64K Compact/Coding/MultiHop ×5; 80K Coding/MultiHop/Supervisor ×5.

## Ursache leere Starts

`wait_for_turn` brach nach 45 s ab, während das 27B-Modell noch lud (`n_gen=0`, VRAM &lt; 4 GB). Das ist Harness, kein Context-Overflow.

Nach Warmup selten: 2 leere Erstversuche (64K MultiHop r2, 80K MultiHop r3). 80K-Retry PASS. 64K-Retry = Agent-Fail (kein zweites Empty).

## Gültige Matrix (letzter Versuch, keine Empty-Counts)

| Context | Compact | Coding | MultiHop | Supervisor |
|--------:|:-------:|:------:|:--------:|:----------:|
| 65536 | 5/5 | 4/5 | 4/5 | — |
| 81920 | — | 4/5 | 5/5 | 5/5 |

## Klassifikation

| Klasse | Was | Beispiele |
|--------|-----|-----------|
| `harness_session` | leerer Start | MultiHop 64K r2 a1; MultiHop 80K r3 a1 |
| `agent` | Inhalt | Coding 64K r3; Coding 80K r5; MultiHop 64K r2 a2 |
| `pass` | gültig grün | Rest |

**Coding:** Fixture lösbar (4/5 beide Stufen). Fail = liest Bugs, editiert nicht (sucht Shell/pytest/`ask_user`, `votes=0`). Unabhängig von 64 vs 80. Shell ist im Arbeitsplatz deaktiviert.

**Supervisor 80K:** doppelter `agent` aus dem Fair-Lauf **nicht reproduziert** (5/5).

## Entscheidung

Kein 80K-Cutover. 80K bei MultiHop/Supervisor stark, Coding **gleich** schwach wie 64K. Kriterien „alle Suites zuverlässig“ nicht erfüllt.

Rollback 64K→16K: `scripts/rollback-local-quality-64k.sh`  
80K-Skripte liegen bereit, unbenutzt: `scripts/apply-local-quality-80k.sh`, `scripts/rollback-local-quality-80k-to-64k.sh`

## Nächster Schritt

Context Boundary bleibt aktiv. Optional: Shell nur mit Einzelfreigabe (kein YOLO) — Nutzungsmodell ist Sitzung, kein Dauerbetrieb. Danach erst Leiter 88/96 als Bench.

## Belege

- `benchmarks/context-boundary-retry-empty-20261003/STATUS.md`
- `benchmarks/context-boundary-retry-empty-20261003/DONE.md`
- `benchmarks/context-boundary-retry-empty-20261003/results.jsonl`
- `benchmarks/context-boundary-retry-empty-20261003/*-a1.json` / `*-a2.json`
