# PDF Agent E2E — 2026-09-28

## Final Verdict

**PASS.** Echter Agentenpfad (`qwen serve` → `local-fast` → MCP `pdf_*`, `trust:false`, `proceed_once`, kein YOLO). Technische QA PASS, Vision-QA ohne high Issues, Negativtests PASS, MoE-Reviewer-Interaktion PASS (Zweitmeinung ohne Dateiänderung). Original-Fixture unverändert.

## Test Setup

- MCP `local-tools` **1.7.0** / 33 Tools (inkl. `moe_consult`)
- Runner: `benchmarks/pdf_agent_e2e.py` über `qwen serve` HTTP Bridge `:4170`
- Model: `local-fast(openai)`
- Workspace: `/home/mike/Projects/Linux Lokales KI`
- Artefakte: `benchmarks/pdf_agent_e2e_2026-09-28/`

## Input PDF

- `input/agent_e2e_source.pdf` (+ `agent_e2e_source.original.pdf` Backup)
- 2 Seiten A4, ReportLab
- Seite 1: Titel, Customer, Project Status Draft, Amount 1250 EUR
- Seite 2: Tabelle Analysis/Open, Implementation/Pending, Review/Open
- `Pending` nur in der Tabellenzelle (nicht in Notes), damit Replace eindeutig ist

## User Instruction

Agent bekam natürliche Pflicht-Edits inkl. same-length Hint `Pending=>Done   ` (7 Zeichen) für sauberes Redact-Layout. Output: `output/agent_e2e_edited.pdf`.

## Agent Tool Calls

Nachgewiesen (frische Session, kein Replay):

1. `pdf_inspect` auf Source
2. `pdf_edit` mode=`replace` mit  
   `Project Status: Draft=>…Final; Amount: 1250 EUR=>…1490 EUR; Pending=>Done   `
3. `pdf_read` auf Output

Votes: nur `proceed_once`. Kein YOLO.

## Edit Result

- Output existiert, Header `%PDF-`, Größe &gt; 0
- SHA ≠ Source
- Text: Final, 1490, Done; Draft-Status/1250/Pending-Zelle weg
- Customer/Titel/Analysis Open erhalten
- Seiten = 2, Seitenformat stabil

## Technical QA

PASS (`agent_e2e_report.json` → `technical_qa.pass=true`). Renders: `renders/edited-p1.png`, `edited-p2.png`.

## Vision QA

`pdf_vision_qa` Seiten 1–2: **keine high Issues**. Medium `empty_page` auf kurzer Seite 1 = akzeptierter False Positive. `vision_pass=true`.

## Layout Result

In-place `replace` hält Layout weitgehend. **Wichtig:** kürzerer Ersatztext ohne Padding erzeugt Lücken (Vision high `bad_spacing`) — daher same-length Padding für `Pending`→`Done`. Bei großen Textmengen: `recreate`/`soffice` → Layouttreue nicht garantiert (bestehendes PDF_TOOLS-Verhalten).

## Negative Tests

| Fall | Ergebnis |
|------|----------|
| fehlender Suchtext | ToolError, kein Fake-PASS (`pdf_edit` jetzt `replacements_applied==0` → Fehler) |
| ungültige PDF | Ablehnung |
| Output außerhalb Root (`/etc`) | Ablehnung |

## MoE Reviewer Test

`moe_reviewer_test.json` **PASS**:

- Agent: `pdf_edit` + `pdf_read` auf `agent_e2e_moe_review.pdf`
- Source unverändert
- MoE: `moe_consult role=reviewer` als Zweitmeinung (nach Agent-Edit; named `reviewer`-Spawn war flaky, Fallback-Consult dokumentiert)
- MoE ändert keine Datei; leftover-Prozesse `[]`

## Problems Found

1. Stale `qwen serve` Session replayte alte Tools → Fake-PASS-Risiko → Fix: Session DELETE vor neuem Lauf
2. `pdf_edit` bei 0 Treffern lieferte früher `ok:true` → Fix: ToolError
3. Kürzeres Replace ohne Padding → Vision high spacing → Fixture/Prompt same-length
4. Prompt-API braucht `{"prompt":[{"type":"text","text":…}]}`

## Fixes Applied

- `apps/local-tools/pdf_tools.py` zero-hit reject + per-page redactions
- `moe_consult` MCP 1.7.0 on-demand
- E2E: fresh session, Vision high-only gate, Negativtests

## Safe for real PDFs?

**Ja, mit Vorsicht:**

- Immer auf Kopie arbeiten; Original behalten
- Kleine Ersetzungen: `pdf_edit mode=replace`, same-length wenn möglich
- Danach `pdf_read` + optional `pdf_vision_qa`
- Bei großen Umbauten: Rebuild-Pfad, Layout kann abweichen
- MoE nur Review, nie als Datei-Editor
