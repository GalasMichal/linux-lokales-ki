# Tools

MCP server `local-tools` at `http://127.0.0.1:8765/mcp` (`trust: false`).

| Tool | Role |
|------|------|
| `generate_image` | FLUX.2-klein T2I via KI-Arbeitsplatz |
| `edit_image` | Qwen-Image-2.1 edit via KI-Arbeitsplatz `POST /api/images/edit` |
| `memory_load` | Compact `.agent/` load before a task |
| `memory_update` | STATE/TASKS replace; DECISIONS append; history snapshot |
| `knowledge_search` | Compact long-term knowledge package (lazy) |
| `knowledge_get` | One knowledge entry by id |
| `knowledge_record` | Record decision/failure/fix/fallback/replan/research/success |
| `pdf_read` | Extract text |
| `pdf_inspect` | Pages, sizes, metadata, has_text |
| `pdf_create` | Text or `.txt`/`.md` → PDF + QA |
| `pdf_edit` | Small replace or recreate via text/LibreOffice |
| `pdf_merge` | Concatenate PDFs |
| `pdf_split` | Extract pages |
| `pdf_ocr` | OCRmyPDF + Tesseract |
| `pdf_render` | Page → PNG, vision-ready |
| `moe_consult` | On-demand CPU-MoE Zweitmeinung |
| `pdf_vision_qa` | Optional visual layout QA via Ollama `local-quality` `/api/chat` |
| `browser_open` | Open one public http(s) page in the isolated Brave window |
| `browser_snapshot` | URL, title, visible text, element ids |
| `browser_click` | Click one id from the latest snapshot |
| `browser_type` | Type into an input or textarea id |
| `browser_scroll` | Scroll the page, then snapshot |
| `browser_back` | One page back |
| `browser_screenshot` | PNG of the browser page only |
| `browser_close` | Close that browser session |
| `desktop_snapshot` | Monitors, windows `[w1]`, focus, elements, PNG |
| `desktop_focus` | Raise one window id from the latest snapshot |
| `desktop_click` | Element id, or a point inside that window only |
| `desktop_type` | Text into a field of that window. No passwords or terminals |
| `desktop_scroll` | Scroll up or down in that window |
| `desktop_key` | Escape, Enter, Tab, Shift+Tab, Ctrl+A, Ctrl+C, Ctrl+V only |
| `desktop_screenshot` | PNG of the local desktop |
| `desktop_close` | Drop window ids. Does not quit applications |

Qwen names: `mcp__local-tools__<tool>`. After the 8k overflow fix, unused builtins (`run_shell_command`, `web_fetch`, `skill`, plan/cron) stay **disabled** in `~/.qwen/settings.json`. Native `agent` / `list_agents` / `send_message` are **enabled** for Supervisor/Multi-Agent (22.09.2026); Shell/YOLO remain off. File builtins (`read_file`, `edit`, `glob`, `grep_search`, `write_file`) stay loadable via ToolSearch. Named project agents: `.qwen/agents/{researcher,architect,reviewer}.md` (see `docs/SUPERVISOR_MULTI_AGENT.md`). Since 22.09.2026 MCP schemas are deferred: `alwaysLoadTools: false`, `tools.visible` empty. All tool names stay in `includeTools` (**33**) and are found with `tool_search` `select:<shortname>`. Do not use Shell as a substitute for these MCP tools when they apply. Long-term lessons: `knowledge_*` (see `docs/KNOWLEDGE_BASE_V2.md`); current state stays on `memory_*`.
