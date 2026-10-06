# Qwen Lazy Tool Loading

Stand: 22.09.2026. Lazy Tool Loading bleibt produktiv. Der damalige Ketten-FAIL ist durch den Compact State Ledger behoben: [`docs/QWEN_COMPACT_STATE_LEDGER.md`](QWEN_COMPACT_STATE_LEDGER.md) (**PASS**). Knowledge Base v2 ergänzt drei lazy Tools: [`docs/KNOWLEDGE_BASE_V2.md`](KNOWLEDGE_BASE_V2.md).

Die MCP-Tools bleiben registriert (jetzt **32**, inkl. `knowledge_*`). Ihre JSON-Schemata stehen nicht mehr alle gleichzeitig im ersten Modellprompt. Der harte Abbruch bei 17216 Tokens ist weg.

## Was live bleibt

- `~/.qwen/settings.json`: `mcpServers.local-tools.alwaysLoadTools` ist `false`. `includeTools` listet alle MCP-Namen (**32**). `trust` ist `false`. `tools.approvalMode` ist `default`. `tools.eager` ist `[]`. `model.name` ist `local-fast`. `compactionModel` ist `local-fast`. `context.autoCompactThreshold` ist `0.95`.
- Projekt-`.qwen/settings.json`: `tools.visible` ist `[]`, damit volle MCP-Namen die Zurückstellung nicht über `getVisibleTools` aushebeln.
- `apps/local-tools/config/qwen-mcp.json`: dieselbe `alwaysLoadTools: false`, damit ein späteres Einspielen die Schemata nicht wieder eager macht.
- MCP **1.6.0 / 32 Tools** (Lazy-Phase war 1.5.0 / 29). Kein Tool gelöscht; Knowledge additiv und lazy.
- Qwen Code **0.24.2**, Ollama **0.34.2**. QUALITY bleibt 16384. FAST bleibt 32768. `bench-qwen38-27b-32k` unangetastet.
- ToolSearch-, Registry-, Git-Snapshot- und Compact-State-Ledger-Patches bleiben. Prompt-Datei Stock.
`alwaysLoadTools` entscheidet, ob ein MCP-Schema von Anfang an im Modell-Tools-Array steht. `includeTools` entscheidet nur, welche Tools der Server überhaupt meldet. `tools.eager` gilt für eingebaute Tools, nicht für schon zurückgestellte MCP-Tools. `tools.visible` hebt die Zurückstellung auf und würde die Schemata wieder in den Prompt ziehen. `tool_search` mit `select:<kurzname>` findet das Tool in der Registry. `tool_call` führt es aus. Danach bleibt das Schema für den Rest der Session sichtbar. Das ist in der installierten 0.24.2 so, nicht aus einer älteren Version geschlossen.

## Tokenmessung

Methode: Ollama `POST /api/generate`, Modell `local-fast`, `raw: true`, `num_predict: 1`, Feld `prompt_eval_count`. Das ist der Tokenizer, keine Zeichenschätzung. Schema-Text ist kompaktes JSON mit Name `mcp__local-tools__<tool>`, Beschreibung und Parametern. Beleg: `benchmarks/lazy-tool-budget-20260922/budget.json`.

| Komponente | Tokens |
|---|---|
| Systemprompt ohne MCP | nicht isoliert. Erster Live-Prompt mit nur `tool_search`: **6342** (Session `a7e2c3bd`) |
| ToolSearch allein | in diesen 6342 enthalten |
| Memory-Tools | 304 |
| PDF-Tools | 1034 |
| Image-Tools | 551 |
| Browser-Tools | 568 |
| Desktop-Tools | 645 |
| alle 29 Schemata | **3102** |
| `memory_load`-Ergebnis | **4246** |
| Compact-Summary | FAST-Ausgabe 782–919 Tokens. Der Folge-Prompt ist die belastbare Zahl |
| alter Folge-Prompt, 29 Schemata eager | **17216** |
| Folge-Prompt nach Compact, Schemata zurückgestellt | **9843**, **9793**, **9686**. Ein Lauf danach **16231** |

Vorheriger erster Prompt mit allen 29 Schemata: 9845. Differenz zum zurückgestellten ersten Prompt: etwa 3500 Tokens.

## Läufe

Discovery auf `local-fast`, nur `proceed_once`:

- `a7e2c3bd`: `select:memory_load` → `memory_load`
- `95620bd8`: `select:pdf_create` und `pdf_render`
- `8cfb0feb`: `browser_open` auf `https://example.com`
- `2ac0e81e`: `desktop_snapshot`

QUALITY, Kontext 16384, Compact über `local-fast`. Beleg unter `benchmarks/compact-continuity-20260921/`.

- `8e5c5cf5` (Stock-Prompt, Schemata zurückgestellt): Compact bei 16010 → geschätzt 6356, nächster gemessener Prompt **9843**. Kein Abbruch, kein `no user query`. `pdf_create` lief vor dem Compact erfolgreich und danach noch viermal, davon mit falschem Pfad `pdf_test/page.pdf`. Kette unvollständig.
- `cd99ce7f` (Prompt-Patch, breite Tool-Suche): Compact, geschätzt 10946. Ollama danach `500 no user query found in messages`. Die Zusammenfassung hatte `memory_load` korrekt als erledigt und `pdf_create` als nächsten Schritt. Die Fortsetzung erreichte das Modell nicht.
- `ce425336` (Prompt-Patch, ein Tool): Fortsetzung **9793**. `memory_load` wurde nicht wiederholt. `pdf_read` und `pdf_vision_qa` fehlten. Ein `pdf_render` schlug fehl (Pfad außerhalb), der zweite gelang.
- `ac14aa20` (Prompt-Patch, Checkliste am Prompt-Ende): erster Compact nach `memory_load`, Schätzung 10705, echter nächster Prompt **16231**. Zweiter Compact nach erfolgreichem `pdf_create`. Die neue Zusammenfassung führte weiter nur `memory_load` als erledigt und verlangte `pdf_create` erneut. Danach noch einmal erfolgreiches `pdf_create`, dann je einmal `pdf_read`, `pdf_render`, `pdf_vision_qa`, `memory_update`. Folgeprompts danach 9686 bis 12824. Kein harter Überlauf über 16384.

`select:`-Regression auf `local-fast`, Session `73a5e1fb`: `memory_load`, `pdf_create`, `generate_image`, `edit_image`, `browser_open`, `desktop_snapshot` lösen jeweils auf `mcp__local-tools__…` auf. Kein `tool_call`, kein Bildlauf.

Policy-Unit-Tests für Browser (`file`, `javascript`, localhost) und Desktop (Terminal, Passwort, kritische Aktionen) sind grün. Der MCP-Code dieser Phase ist unverändert. Ein erneuter Live-Aufruf von `file://` war nicht Teil der Läufe.

Ein eigener Retry-Test und ein eigener Auftrag „Lies die PDF noch einmal“ wurden nicht gefahren. Der eine fehlgeschlagene `pdf_render` wurde mit korrigiertem Pfad wiederholt. Das ist kein Ersatz für diese beiden Tests.

## Warum kein PASS

Mindestziel war ein Folge-Prompt unter 15565 (`0.95 × 16384`) und die sechs Tools je einmal, ohne erneutes Compact direkt danach.

Der Folge-Prompt kann darunter liegen (9843, 9793, 9686). In der Kette, die alle sechs Namen erreicht hat, lag der erste Folge-Prompt bei **16231**. Qwen schätzt nach dem Compact zu niedrig, weil das große `memory_load`-Ergebnis wieder an die Historie gehängt wird. 16231 ist unter dem harten Limit 16384 und über der Compact-Schwelle. Es kam sofort ein zweiter Compact.

Der Prompt-Patch hat FAST nicht dazu gebracht, das gerade erfolgreiche `pdf_create` in `<completed_tool_calls>` zu schreiben. Der zweite Compact hat denselben nächsten Schritt wiederholt. Deshalb bleibt der Patch draußen. `scripts/apply-qwen-compact-continuity-patch.sh` ohne Argument bricht ab.

## Backup und Rollback

Settings: `/mnt/ai-archive/backups/qwen-lazy-tools-20260922-093224/` mit `rollback.sh`. Der stellt `alwaysLoadTools: true` und die alte `tools.visible`-Liste wieder her. Das ist nicht ausgeführt. Die zurückgestellten Schemata bleiben live, weil sie den Abbruch bei 17216 beseitigen.

Prompt-Patch-Backup: `/mnt/ai-archive/backups/qwen-code/compact-continuity-20260922-094324`. Der Patch ist mit `--rollback` entfernt. ToolSearch, Registry und Git-Snapshot sind danach noch da.

## Nächster Schritt

Erledigt durch Compact State Ledger. Siehe `docs/QWEN_COMPACT_STATE_LEDGER.md`. Nächste Phase: Knowledge Base v2.
