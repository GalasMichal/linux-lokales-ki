# Qwen Compact Continuity

Stand: 22.09.2026. Der Prompt-Patch bleibt **nicht installiert**. Der Continuity-Engpass ist über den Runtime-Ledger gelöst: [`docs/QWEN_COMPACT_STATE_LEDGER.md`](QWEN_COMPACT_STATE_LEDGER.md) (**PASS**). Lazy Schemata: [`docs/QWEN_LAZY_TOOL_LOADING.md`](QWEN_LAZY_TOOL_LOADING.md).

## 22.09.2026 Abend — State Ledger PASS

Nach Lazy Tools lag der Folgeprompt noch bis 16231. Ursache: volles `memory_load`-Result und fehlende maschinelle Erfolgsliste. Fix: `linux-lokales-ki-compact-state-ledger` in `chunk-VQUX7GWP.js`. QUALITY-E2E `667d9bc2`: Compact 1×, Fortsetzung **9318**, sechs Tools je 1×.

## 22.09.2026 Morgen — Lazy Tools

`alwaysLoadTools` ist `false`. Alle 29 Tools bleiben in `includeTools`. Stock-Lauf nach Compact maß **9843** Tokens statt 17216. `pdf_create` lief danach trotzdem erneut. Prompt-Patch geprüft und entfernt.

Der Compact-Prompt ist nicht installiert. Qwen Code bleibt 0.24.2 mit den drei vorhandenen Patches (ToolSearch, Registry, Git-Snapshot). Schwelle `0.95` und `compactionModel=local-fast` bleiben.

## Root Cause

Zwei Funktionen in der installierten 0.24.2:

- Compact startet `ChatCompressionService.compress` in `chunk-VQUX7GWP.js`.
- Der Prompt an `compactionModel` ist `getCompressionPrompt()` in `chunk-CXXHL3XJ.js`.
- Stock-SHA dieser Prompt-Datei: `859c4a89149f02e271f73039bf4aa4d31eead0e08dd333d3a17f790bd754986c`.
- Die Registry-Datei, die Compact und den MCP-Kurznamen enthält, hat die gepatchte SHA `2433fc7ca45bc5afc22efc91be0da87ba1f420b213d5d9e61a180e9525924035`.

`hasStateSnapshot` prüft nur, dass `<state_snapshot>…</state_snapshot>` Text enthält. Einzelne XML-Abschnitte werden nicht ausgewertet. `postProcessSummary` streicht nur `<analysis>` und hängt danach diesen Satz an: „Continue from the last in-flight step“.

Die komprimierte Session ersetzt die alte Historie durch die Zusammenfassung. Erfolgreiche Tool-Aufrufe bleiben nur erhalten, wenn das FAST-Modell sie in den Text schreibt. `repairOrphanedToolUseTurns` baut fehlende Tool-Antworten mit dem Text „Treat as failure and retry if needed“. Das erklärt das ältere doppelte `pdf_read` aus A14, wenn die Zusammenfassung den erfolgreichen Aufruf nicht als erledigt führt.

Mit MCP 1.5.0 und 29 Tools reicht ein Prompt-Satz nicht mehr.

Gemessen am 21.09.2026:

1. Kurzer QUALITY-Lauf, Session `631ff44e-c5b4-419c-b735-79288f1164f3`. Erster Prompt 9845 Tokens. Nach `memory_load` schätzt Qwen den Folge-Prompt noch unter `0.95 × 16384`. Es gibt keinen Compact. Ollama 0.34.2 antwortet `no user query found in messages`. Dieselbe Meldung lässt sich ohne Qwen nachbauen: langes System, langes Tool-Ergebnis und das Tools-Array, Modell `local-quality`, Kontext 16384. `local-fast` mit 32768 nimmt dieselbe Größe an.
2. Größerer Prompt, damit Compact sicher startet. FAST schreibt etwa 345 Tokens, VRAM dabei rund 9 GB. Danach bricht Qwen ab: `Estimated prompt tokens: 17216; hard limit: 16384; compression status: COMPRESSED`. Die Zusammenfassung passt. System-Prompt, alle 29 Tool-Schemata und das letzte Tool-Ergebnis zusammen nicht.

Ein zusätzlicher Abschnitt `<completed_tool_calls>` im Compact-Prompt ändert die 17216 Tokens nicht. Die Fortsetzung erreicht das Modell nicht. Deshalb kein produktiver Patch.

## Was nicht geändert wurde

Schwelle, QUALITY-Kontext, FAST als Compact-Modell, Memory, PDF, Browser, Desktop, Bilder, ToolSearch, Git-Snapshot, `trust`, `approvalMode`. Kein YOLO. Kein 32K-QUALITY.

Der isolierte Prompt-Text liegt in `patches/qwen-code/0.24.2/patch_compact_continuity.py`. `scripts/apply-qwen-compact-continuity-patch.sh` ohne Argument bricht ab und schreibt nichts in die Installation. Die Patch-Tests prüfen den Text nur an Kopien.

Beleg: `benchmarks/compact-continuity-20260921/`.
