# PDF Vision-QA

Stand: 16.09.2026. Optionale visuelle Layout-Prüfung auf dem bestehenden MCP `local-tools`. Kein zweites Modell, kein Qwen Serve im Vision-Pfad.

## Architektur

`pdf_create` / Edit → technische `qa_pdf` (öffnet, Seiten, Text, Render) → optional `pdf_vision_qa`.

`pdf_vision_qa` spricht direkt `http://127.0.0.1:11434/api/chat` mit Modell `local-quality` (`qwen3.8:27b` / **16384**, CLIP-Projektor 460.73M). Kein ACP-Systemprompt, keine Tool-Schemas, `stream: false`, `think: false`, `temperature: 0.1`, Structured Output via Ollama `format` JSON Schema. Seiten einzeln, max. 8.

Pfad: PDF (intern `pdf_render`) oder bereits erzeugtes PNG. Dieselben Roots wie die anderen PDF-Tools.

## Schema

Aggregat: `ok`, `needs_regeneration`, `pages_checked`, `summary`, `issues`.

Issue: `page`, `type`, `severity`, `confidence`, `description`.

Typen: `clipped_text`, `overlap`, `text_too_small`, `empty_page`, `broken_table`, `image_error`, `bad_alignment`, `bad_spacing`, `overflow`, `other`.

Severity: `low` / `medium` / `high`. Eine `high`-Issue setzt `ok=false` und `needs_regeneration=true`. `strict=true` wertet auch `medium` so. Ungültiges Modell-JSON ist kein PASS. `confidence` 0–100 wird auf 0–1 skaliert. Fast leere PNGs bekommen lokal `empty_page`, falls das Modell die Issue-Liste leer lässt.

## Performance (Preflight + Direct QA, 15.09.2026)

| Messung | Wert |
|---------|------|
| Preflight PNG `/api/chat` | 16.7 s inkl. Load 6.4 s |
| Titel gelesen | „QUALITY Cutover E2E“ |
| Thinking | aus (`think: false`) |
| VRAM danach | 14480 MiB (Text-QUALITY ~14.2 GB; Projektor sichtbar) |
| RAM used | 10433 MiB / 31864 |
| Offload | 38 % CPU / 62 % GPU, ctx 8192 |
| Bad page | 14.2 s, `clipped_text`+`overlap` high |
| Clean page | 8.5 s, `ok=true` |
| Prompt-Tokens Vision | ~1890–1940 |

## False Positives / Negatives

- Sehr spärliche aber gültige Seiten können `bad_spacing` low bekommen; `high` war auf der Clean-Fixture nicht gesetzt.
- Leere Seite: Modell beschrieb „blank“, ließ `issues` leer — lokal nachgezogen.
- `confidence: 95` statt `0.95` kam vor; wird normalisiert.
- Grammatik/Inhalt wird absichtlich nicht bewertet.

## Rollback

Datei `apps/local-tools/pdf_vision.py` entfernen, `server.py` auf 1.1.0 ohne `pdf_vision_qa` zurück, MCP-Unit neu starten, `includeTools` ohne `pdf_vision_qa`. Quality-Alias unverändert.

Vision-Pfad bleibt `local-quality` über Ollama `/api/chat` (jetzt 16384). Unter `MAX_LOADED_MODELS=1` teilt Vision denselben Slot wie der QUALITY-Agent.

Nächste Phase (nicht implementiert): Image Editing, Browser-Agent, oder optionaler Compact-Prompt-Patch. A01–A14: `docs/ACCEPTANCE_A01_A14.md`.
