# PDF / Document Tools

Lokales Tool-Pack auf dem bestehenden MCP-Server `local-tools`. Kein zweiter Server, keine Cloud.

## Tools

| Tool | Funktion | Backend |
|------|----------|---------|
| `pdf_inspect` | Seiten, Metadaten, has_text | PyMuPDF |
| `pdf_read` | Text extrahieren | PyMuPDF |
| `pdf_create` | Text/`.txt`/`.md` → PDF | ReportLab, danach QA |
| `pdf_edit` | klein: Suche/Ersetzen; groß: neu erzeugen | PyMuPDF / ReportLab / LibreOffice |
| `pdf_merge` | PDFs zusammenführen | pikepdf |
| `pdf_split` | Seiten extrahieren | pikepdf |
| `pdf_ocr` | Texterkennung | OCRmyPDF + Tesseract |
| `pdf_render` | Seite → PNG | PyMuPDF |
| `pdf_vision_qa` | optionale visuelle Layout-QA | Ollama `local-quality` `/api/chat` |

Qwen-Namen: `mcp__local-tools__<tool>`.

## Qualitätskontrolle

Nach Create, Edit, Merge, Split, OCR:

- PDF erneut öffnen
- Seitenzahl
- Textprobe
- mindestens eine gerenderte Seite (`*.qa-p1.png`)
- strukturiertes `qa`-Objekt

Das ist die **technische** QA. `pdf_vision_qa` ist optional und prüft Layout auf dem Render (Clip, Overlap, leere Seite, kaputte Tabelle). Nicht bei jedem Mini-Test-PDF. Details: `docs/PDF_VISION_QA.md`.

Große Textänderungen: Zwischenformat Text (oder LibreOffice `mode=soffice`), dann neues PDF. Kein PDF-Reflow.

## Host-Zustand 2026-09-15

Bereits vorhanden: Poppler (`pdftoppm`, `pdfunite`, …), LibreOffice 26.2, Ghostscript, Pillow, `libtesseract`, `qpdf-libs`, `tesseract-langpack-eng`.

Neu (ohne sudo):

- `pip install --user` pymupdf 1.28.2, pikepdf 10.8.0, reportlab 4.5.1, ocrmypdf 16.13.0
- RPM-Extrakt nach `~/.local/bin`: `tesseract` 5.5.3, `qpdf` 12.3.2
- Tessdata `deu`/`osd` unter `~/.local/share/tessdata`

## Grenzen

- Pfade nur in erlaubten Roots
- MCP-Request-Body 64 KiB — große Texte lieber als `source_path`
- OCR-Default `deu+eng`; `--skip-text` überspringt Seiten mit Text
- Live-Deploy der MCP-Unit ist ein eigener, freizugebender Schritt
