# Qwen Code Nightly-Diagnose — order_service Runs 2–3

Stand: **04.10.2026 ~13:53**. Ziel: klären, ob neuere Qwen-Code-Builds die `read_file`-Abbrüche aus dem 80K-Realistic-Lauf beheben. **Kein Produktiv-Cutover, kein globaler Qwen-Wechsel.**

## Ausgangslage (stable 0.24.7, Bench 09:57)

| Run | Klasse | Ursache (belegt) |
|-----|--------|------------------|
| 1 | **must_loss** | Sichtlich grün; `total()` ignoriert Mitgliedspreis → MUST `119≠59`. Katalog **nicht** mutiert. |
| 2 | **tool_runtime** | Modell: parallele `read_file` mit Arg **`path`**, Schema verlangt **`file_path`** → `invalid_tool_params`; Qwen: `LOOP_DETECTED` / `invalid_tool_params_stagnation`, Turn abgebrochen. Kein Edit. |
| 3 | **tool_runtime** | Wie Run 2 (`tool_call` + `path`). |

Chat-Telemetrie: `benchmarks/realistic-80k-20261004/qwen-home/projects/.../ab35cf9c-*.jsonl`, `f72e1780-*.jsonl`.  
Erfolgreicher Run 1 nutzte **`tool_search`** und danach `file_path` — gleiche absolute Pfade unter `/srv/ai/workspaces/...`.

**Nicht** die Ursache: Workspace-Mismatch, Permission-Deny, Verzeichnisgrenze. Der dokumentierte Nightly-Fix [#12987](https://github.com/QwenLM/qwen-code/pull/12987) (*honor approved cross-directory shell/monitor*) betrifft **Shell/Git außerhalb Session-CWD** — passt **nicht** zu `read_file` + Schema `file_path`.

## Isolierter Nightly-Test

| Parameter | Wert |
|-----------|------|
| Qwen | `0.24.7-nightly.20261003.2c591ecc08` (extrahiert unter `.agent/tmp/qwen-code-nightly-20261003/`) |
| Prod Qwen | **unverändert** `0.24.7` unter `/srv/ai/apps/qwen-code` |
| Serve | `:4172`, eigenes `QWEN_HOME` |
| Modell | `bench-qwen38-27b-80k` / `959b4a6094a9`, ctx 81920 |
| Ollama | 0.35.0 |
| Aufgabe | `order_service` Runs **2–3** nur, gleiche Prompts/Fixtures/MUSTs |
| Host-Patches auf Nightly | **nein** (stable prod hat toolsearch + ledger) |

Belege: `benchmarks/realistic-80k-nightly-diag-20261004/` (`results.jsonl`, `MANIFEST.json`, `SCOREBOARD.json`, Chat-JSONL).

### Ergebnis Nightly-Diag

| Run | resolved | Klasse | Kurz |
|-----|:--------:|--------|------|
| 2 | **ja** | pass | `tool_search` → parallele `read_file` mit **`file_path`** → Edits → sichtlich + MUST grün |
| 3 | nein | **must_loss** | Voller Tool-Pfad; sichtlich grün; MUST wieder `119≠59` (wie Original Run 1) |

**tool_runtime: 0** in dieser Diagnose-Serie.

## Interpretation

1. **Runs 2–3 (stable)** scheiterten primär an **Modell-Toolschema** (`path` statt `file_path`) plus **Qwen Loop-Guard** — nicht am Harness-Workspace.
2. **Nightly verhindert das nicht deterministisch.** Im Diagnose-Lauf wählte das Modell **`tool_search` zuerst** (wie erfolgreicher Run 1); dadurch korrektes `file_path`. Das kann an Sampling, Kontext oder Nightly-Prompt-Tweaks (#12990 Code Mode / #13006 Hook-Kontext) liegen — **kein Logbeleg für einen dedizierten `path`→`file_path`-Alias-Fix.**
3. **PR #12987** ist für diese Fehler **nicht relevant** (kein post-approval Shell-Guard in den Logs).
4. **MUST-Problem bleibt:** Nightly Run 3 reproduziert den echten **must_loss** (Mitgliedspreis in `total()`). Das ist **Modell/Logik**, kein Tool-Abbruch.

## Getrennte Zähler (80K order_service gesamt)

| Kategorie | Original 09:57 (stable) | + Nightly-Diag 2–3 |
|-----------|-------------------------|---------------------|
| resolved | 0/3 | +1 (nur Diagnose r2; **kein** Ersatz für Original-Serie) |
| must_loss | 1 (r1) + 0 fälschlich als MUST (r2–3 reklass.) | +1 (nightly r3) |
| tool_runtime | 2 (r2–3) | 0 in Diagnose |

Original-`results.jsonl` **unverändert**. Reklassifikation: `DECISION_CORRECTION.json`.

## Empfehlung

- **Produktiv bei 64K bleiben.** Kein 80K-Cutover.
- **Qwen-Nightly global installieren** lohnt sich **nicht** allein wegen Runs 2–3: kein belegter Schema-Alias-Fix; MUST-Fehler bleibt; ein Diagnose-Lauf grün, einer must_loss.
- Optional später: erneute **stable**-Serie mit gleicher Statistik — oder Bench-Hinweis „zuerst `tool_search`“ (wäre Prompt-Protokoll-Änderung, bewusst nicht gemacht).

Orchestrator: `benchmarks/run_realistic_80k_nightly_diag.sh`
