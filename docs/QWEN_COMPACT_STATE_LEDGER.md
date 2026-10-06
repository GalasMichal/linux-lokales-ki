# Qwen Compact State Ledger

Stand: 22.09.2026. Ergebnis: **PASS**.

Nach Lazy Tool Loading blieb der harte Overflow bei 17216 weg. Der verbleibende Fehler war: nach Compact hing das große `memory_load`-Ergebnis wieder voll am Folgeprompt (gemessen bis 16231), und erfolgreiche Tool-Calls hingen nur am FAST-Summary. Diese Phase setzt einen **deterministischen Runtime-Ledger** und kürzt große erfolgreiche Tool-Results nach dem Compact.

## Live

- Qwen Code **0.24.2**, Ollama **0.34.2**
- Lazy Tools unverändert: `alwaysLoadTools=false`, `tools.visible=[]`, `includeTools` = alle MCP-Namen (seit KB v2: **32**)
- MCP **1.6.0 / 32 Tools** (Ledger-Phase war 1.5.0 / 29; Ledger-Patch unverändert)
- Compact: Schwelle `0.95`, Modell `local-fast`
- Stock-Compact-Prompt (kein Continuity-Prompt-Patch)
- Marker: `linux-lokales-ki-compact-state-ledger`
- Datei: `chunk-VQUX7GWP.js` (Registry-Datei, SHA nach Patch `76adef42…`)
- Apply: `scripts/apply-qwen-compact-state-ledger-patch.sh`
- Patcher: `patches/qwen-code/0.24.2/patch_compact_state_ledger.py`
- Snippet: `patches/qwen-code/0.24.2/compact-state-ledger.js`

ToolSearch, Registry und Git-Snapshot bleiben. Rollback entfernt nur diesen Ledger.

## Root Cause (vor dem Fix)

1. Compact ersetzt die Historie durch Summary + ACK.
2. Das ausstehende Tool-Ergebnis (`pendingUserMessage`) wird danach wieder an den Prompt gehängt.
3. `memory_load` liefert oft **zwei JSON-Objekte hintereinander**. Ein naiver `JSON.parse` scheitert. Status blieb `unknown`. Shrink griff nicht.
4. Folgeprompt bis **16231** (unter 16384, über 15565) → sofort zweiter Compact.
5. Erfolgreiches `pdf_create` hing nur am FAST-Text und ging verloren.

## Was die Runtime jetzt macht

Nach echtem Compact (`compressionStatus === COMPRESSED`):

1. Liest Call/Result-Paare aus der Historie vor dem Compact (IDs, `ok`/`error`).
2. Baut `<tool_continuity marker="linux-lokales-ki-compact-state-ledger">` mit kurzen Namen und optionalem Artefaktpfad.
3. Hängt den Block an die Compact-Summary.
4. Kürzt große erfolgreiche Results auf ein Excerpt (~400 Zeichen) statt ~21 000 Zeichen.
5. Übernimmt prior Ledger-Einträge über mehrere Compacts (max. 30).

Nicht vom LLM erzeugt. Kein `next_step`. Keine Tool-Sperre. Unklare Results werden nicht als success markiert. Das erste JSON-Objekt wird per Brace-Scan gelesen, damit doppeltes JSON von `memory_load` zählt.

## Token-Tabelle (gemessen)

Methode: Ollama `local-fast`, `prompt_eval_count`, `num_predict=1`. Live-Prompts aus Session `667d9bc2`.

| Komponente | Tokens |
|---|---|
| Erster Prompt (System/Core + tool_search) | 9896 |
| Nach `memory_load`-Call | 11061 |
| Compact-Summary + Ledger (nach Compact, erster Folgeprompt) | **9318** |
| Machine Ledger allein | **65** |
| Retained `memory_load` nach Shrink (Excerpt) | **~78** (vorher ~4246) |
| Geladene MCP-Schemata nach PDF-Kette | wachsend, Session-Ende max **12901** |
| Alter Folgeprompt (vorher) | bis **16231** |

Reserve bis Schwelle 15565: nach Compact **~6247** Tokens. Kein sofortiger zweiter Compact.

## Belege

- Haupttest: `benchmarks/compact-state-20260922/ledger4.json` **PASS**
  - Compact 1×, Modell `local-fast`
  - Tools je 1×: memory_load, pdf_create, pdf_read, pdf_render, pdf_vision_qa, memory_update
  - Prompt-Tokens: 9896 → 11061 → **9318** … max 12901
  - Ledger in der Compact-Summary sichtbar
- Baseline vorher: `baseline.json` (16231, doppeltes pdf_create)
- Frühere Patch-Fails ohne JSON-Fix: `ledger2.json`, `ledger3.json` (Hard-Overflow ~16738)
- Repeat: `repeat.json` — `pdf_read` nach explizitem „Lies die PDF noch einmal“
- Retry: siehe `retry2.json` (nachgesteuert)
- Unit: `tests/test_compact_state_ledger.py`

## Security / Regression

`trust: false`, `approvalMode: default`, kein YOLO, kein Shell. Browser/Desktop-Policy-Unit-Tests grün. `select:`-Kurznamen unverändert. Bildworkflows und Open-WebUI in dieser Phase nicht angefasst. Größen 512/768/1024.

## Einschränkungen

- Einmal geladene Fachtools bleiben für die Session im Prompt (Qwen 0.24.2).
- Ein zweiter Compact später in einer sehr langen Session ist erlaubt; sofort nach dem ersten bei >15565 nicht.
- Der Continuity-Prompt-Patch bleibt absichtlich nicht installiert.

## Nächste Phase

**Knowledge Base v2 – Failure → Fix → Fallback → Replan + Retrieval.** Nicht in dieser Phase starten.
