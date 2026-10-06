# RETRY EMPTY-START FERTIG

Fertig: 2026-10-03 21:47:37 +0200
Attempts: 32 | gültig: 30
Productive: local-quality **65536**, local-fast **32768** — unverändert.
Kein 80K-Cutover.

| Context | Compact | Coding | MultiHop | Supervisor |
|---|---|---|---|---|
| 65536 | 5/5 | 4/5 | 4/5 | — |
| 81920 | — | 4/5 | 5/5 | 5/5 |

Leere Starts: Harness (45s-Abort beim Load), danach selten.
Echt: Coding 4/5 beide Stufen (kein Edit). Supervisor-Doppel-80K nicht reproduziert.

Bericht: `docs/RETRY_EMPTY_START_2026-10-03.md`
