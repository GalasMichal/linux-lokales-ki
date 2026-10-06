---
name: document-tools
description: >
  Local PDF and document tools. Use for reading, inspecting, creating, editing,
  merging, splitting, OCR, rendering, or visual layout QA of PDFs. Completely local.
  For 1:1 layout templates (styles/tables/logos), MUST use pdf_edit mode=replace only.
---

# Document tools

MCP tools on `local-tools` (Qwen name `mcp__local-tools__<name>`):

| Tool | Use |
|------|-----|
| `pdf_inspect` | pages, metadata, has_text |
| `pdf_read` | extract text (`pages` like `1-3`) |
| `pdf_create` | text or `.txt`/`.md` → PDF (new simple layout only) |
| `pdf_edit` | `mode=replace` keeps layout; recreate/soffice rebuilds |
| `pdf_merge` | comma-separated PDF paths |
| `pdf_split` | one file per page, or a page range |
| `pdf_ocr` | OCRmyPDF/Tesseract, default `deu+eng` |
| `pdf_render` | page → PNG |
| `pdf_vision_qa` | optional visual layout QA via `local-quality` |

## 1:1 layout / Vorlage (CRITICAL)

When the user wants layout fidelity, template copy, styles/tables/alignment/logos kept,
or says 1:1 / Vorlage / nur Daten ändern / Felder leeren:

1. Copy the original PDF first (never overwrite the only original).
2. Use **only** `pdf_edit` with **`mode=replace`** and `replacements` like `alt=>neu;foo=>bar`.
3. Prefer **same-length** replacements when possible (pad with spaces) to avoid gaps.
4. **FORBIDDEN** for this case: `pdf_create`, `pdf_edit mode=recreate`, `mode=soffice`, `new_text`,
   rewriting the whole document as HTML/TXT, Shell, or inventing a new design.
5. Keep tool use tiny: `pdf_inspect` → `pdf_edit` → `pdf_read` → optional `pdf_render` /
   `pdf_vision_qa`. No long vision tours before the first replace.
6. Prefer model **`local-fast`** (32K) for these edit chains; Quality 16K overflows easily.

Blanking a field: replace the exact visible string with spaces of similar length, or a
placeholder the user named — do not rebuild the page.

## Rules

- Paths must stay under the workspace, `/srv/ai/workspaces`, `/home/mike/Projects`, or `/mnt/ai-archive`
- After create/edit/merge/OCR the tool already runs technical QA: reopen, page count, text extract, one rendered page
- Large text changes that intentionally abandon layout: only then `mode=recreate` or `mode=soffice`
- Do not use Shell/`qpdf`/`pdftotext` as a bypass when these tools apply
- Do not dump full multi-page PDF text into long essays; edit, then verify

## Visual layout QA (`pdf_vision_qa`)

Optional. Does not run on every tiny test PDF. Technical `qa_pdf` stays mandatory; vision only adds layout checks.

Use after:

- a final PDF for the user
- larger layout changes
- tables, images, or complex pages

Flow:

1. create/edit the PDF
2. technical QA (already included in create/edit)
3. `pdf_render` if you need the PNG yourself
4. `pdf_vision_qa` with the PDF path (it renders pages internally)
5. if any `high` issue or `needs_regeneration=true`: fix with **replace** again (not recreate), then vision again
6. at most **2** automatic correction loops, then report the remaining issues

Pass `pages` like `1` or `1-3`. `strict=true` also fails on medium issues. Do not dump every page into one huge prompt; the tool inspects pages one by one.

Vision looks at layout only (clip, overlap, empty, broken table). Not grammar.
