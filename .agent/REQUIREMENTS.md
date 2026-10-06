# Requirements

- Local-only stack. No cloud fallback. Bind `127.0.0.1` only.
- `trust: false`, no `--yolo`, no new model pulls in this phase.
- Persistent project memory lives in `.agent/`. Chat history is not the source of truth.
- Before a relevant agent task: load STATE, TASKS, DECISIONS, REQUIREMENTS, TOOLS.
- After a finished task: update STATE and TASKS; append DECISIONS when a choice was made.
- Do not dump `.agent/history/` into the model prompt. History is an audit trail.
- PDF/document work is fully local: read, inspect, create, edit, merge, split, OCR, render.
- After PDF create or a large edit: reopen, check page count, extract text, render at least one page, return structured QA.
- Large text changes on existing PDFs must recreate via an intermediate text/LibreOffice file. No blind PDF reflow.
- Vision models may later inspect rendered PNG pages. Do not install extra models in this phase.
- Optional visual layout QA uses existing `local-quality` over Ollama `/api/chat` (`pdf_vision_qa`). No extra vision pull. Technical `qa_pdf` stays mandatory; vision is not run on every tiny test PDF.
- Productive QUALITY context is 16384. FAST stays 32768 and remains the default model.
- Image Editing with Qwen-Image-2.1: isolated smoke PASS (int8 DiT + w4a8 encoder + VAE, 512 and 1024). Do not add `edit_image` or workplace editing UI until the next explicit go-ahead. FLUX.2-[klein] T2I stays the productive generator. License is Qwen Research (private local test only).
