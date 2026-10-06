# Decisions

Append-only. To change a decision, add a new dated entry that supersedes the old one.

## 2026-09-15 — Persistent memory is `.agent/`, not Qwen auto-memory

Qwen `enableManagedAutoMemory` stays false. Managed files under `~/.qwen/projects/` are not the project source of truth. Compact markdown under `.agent/` is loaded via `memory_load` / `read_file` and updated via `memory_update`. DECISIONS.md is append-only; replacements snapshot the previous file into `.agent/history/`.

## 2026-09-15 — PDF tools extend existing local-tools MCP

No second MCP server. Tools are registered on `apps/local-tools` next to `generate_image`. Path access is limited to `/home/mike/Projects`, `/srv/ai/workspaces`, `/mnt/ai-archive`, and temp dirs.

## 2026-09-15 — Large PDF text edits recreate the document

In-place replace is only for small search/replace. Large rewrites go text → new PDF (ReportLab) or text → LibreOffice headless → PDF. Original layout is not reconstructed.

## 2026-09-15 — PDF Python libs via user site, CLIs via extracted Fedora RPMs

sudo was not available. PyMuPDF, pikepdf, reportlab, ocrmypdf installed with `pip install --user`. `tesseract` and `qpdf` binaries extracted from Fedora RPMs into `~/.local/bin` because `libtesseract` and `qpdf-libs` were already on the system. Poppler and LibreOffice were already installed.

## 2026-09-15 — Live MCP keeps trust:false; non-interactive agent cannot confirm MCP

Deployed `local-tools` 1.1.0. `trust: false` and `approvalMode: default` stay. Qwen `-p` correctly selected `memory_load`/`pdf_create` then got permission declined. Live proof is the MCP Python client. Do not set `--yolo` or `trust: true` to force headless MCP.

## 2026-09-15 — MCP PrivateTmp and PYTHONPATH

systemd `PrivateTmp=true` hides host `/tmp` from the service. PDF outputs go under the workspace (`.agent/tmp/`) or `/srv/ai/workspaces`. `PYTHONPATH` must include user-site and Fedora system site-packages so pikepdf/ocrmypdf import in the MCP venv.

## 2026-09-15 — No Ollama/Qwen runtime bump in this phase

Ollama stays 0.32.14: `/usr/local/bin/ollama` is root-owned; sudo password required. Qwen Code stays 0.21.15: ToolSearch/Git-omit patches are version-pinned. Latest stables verified 2026-09-15: Ollama v0.34.0, Qwen Code v0.23.4. Existing models are not replaced before the model benchmark.

## 2026-09-15 evening — Ollama 0.34.0 and Qwen 0.23.4 after KDE sudo

Ollama updated 0.32.14 → 0.34.0 without changing the systemd drop-in. Cursor cannot show a sudo password prompt; KDE `kdialog` via `SUDO_ASKPASS` is the local path. Qwen Code updated 0.21.15 → 0.23.4. Stock 0.23.4 still needs ToolSearch MCP short-name, registry resolver, and git-snapshot omit (now in `chunk-NXUZFW3G.js`). `trust: false` and `approvalMode: default` stay.

## 2026-09-15 evening — Do not auto-replace FAST/QUALITY after Fable bench

Additive tags `qwen3.8:27b` and `qwen3.6:27b-coding` plus 8K aliases `bench-qwen38-27b-8k` / `bench-qwen36-coding-8k`. Benchmark winner for QUALITY/coding/agent is Qwen3.8 27B 8K. FAST stays `local-fast` (9B, 32K, 100% GPU). `local-quality` is not retargeted until an explicit go-ahead.

## 2026-09-15 evening — QUALITY alias is qwen3.8:27b / 8192

Explicit go-ahead. `local-quality` rebuilt FROM `qwen3.8:27b` with `num_ctx 8192`. Same sampling parameters as before. FAST stays `local-fast`. Parents and bench aliases kept. Rollback: `scripts/rollback-local-quality-qwen36.sh`. Interactive Qwen-serve Memory/PDF E2E did not complete: 90 s of thought chunks, zero MCP tool calls. Smoke via Ollama `/api/chat` did emit `memory_load`.

## 2026-09-15 evening — QUALITY tool-call failure is 8k overflow, not missing MCP

Wire capture of `qwen serve` → Ollama `/v1/chat/completions` showed 44 tools including `mcp__local-tools__memory_load`. `think=false` reached Ollama but `/v1` ignores it for this model; `reasoning_effort=none` is the flag that disables thinking. When the tokenized request exceeds 8192, Ollama snaps `prompt_eval` to 4098 and the model emits thoughts/text instead of MCP calls. FAST 32k holds the same 44-tool prompt. Config-only fix: empty eager list, disable unused builtins (kills the ToolSearch catalog), disable user/bundled skills in Serve, Quality extra_body `reasoning_effort=none`. No 0.23.4 patch. `trust: false` and `approvalMode: default` stay. Do not raise QUALITY context in this phase. Do not implement Vision-QA yet.

## 2026-09-15 evening — Permission vote option is proceed_once

Qwen Serve ACP permission options use `proceed_once`, not `allow`. Voting `allow` returns 400. Interactive E2E must vote `{outcome:{outcome:"selected",optionId:"proceed_once"}}`.

## 2026-09-15 evening — QUALITY MCP E2E uses isolated short sessions

A single mega-prompt or long same-session history overflows 8k again even after the config fix. The passing E2E is five isolated `qwen serve` sessions with one MCP call each, votes `proceed_once`, cancel leftover essay only after tool status `completed`. Default model stays `local-fast`. Vision-QA is the next phase and is not implemented here.

## 2026-09-15 evening — PDF Vision-QA uses local-quality over Ollama /api/chat

No extra model pull. `pdf_vision_qa` on existing `local-tools` talks to `127.0.0.1:11434/api/chat` with `local-quality`, structured JSON, `think: false`. It does not go through Qwen Serve. Technical `qa_pdf` stays; vision is optional after final/layout-critical PDFs. Max two automatic correction loops. `trust: false`, no YOLO. Serve-side `pdf_create`/`pdf_render` remain 8k-sensitive; vision itself is a compact image+schema call.

## 2026-09-15T21:04:55.930562+02:00 — QUALITY MCP E2E short sessions

2026-09-15 — QUALITY E2E used short isolated sessions so 8k still sees MCP tools.

## 2026-09-15T21:06:02.199539+02:00 — QUALITY MCP E2E short sessions

2026-09-15 — QUALITY E2E used short isolated sessions so 8k still sees MCP tools.

## 2026-09-16T17:54:16.406108+02:00 — 16k QUALITY agent E2E

2026-09-16 — 16k agent E2E used bench-qwen38-27b-16k; local-quality stayed 8192.

## 2026-09-16 — QUALITY stays 8k; 16k is the next explicit cutover

Additive aliases `bench-qwen38-27b-16k` and `bench-qwen38-27b-32k` from `qwen3.8:27b`. Productive `local-quality` remains 8192. 16k single-session Serve E2E passed (Memory+PDF+Vision, `proceed_once`). 32k loads and holds the historic 44-tool dump (29653 tokens) but is slower (~10 tok/s, 41% CPU offload). Do not auto-switch. Next go-ahead should be a 16k `local-quality` cutover, not 32k and not prompt-shrink-only. Default model stays `local-fast`. `trust: false`.

## 2026-09-16T21:04:57.932864+02:00 — QUALITY 16k productive cutover

2026-09-16 — local-quality is qwen3.8:27b / 16384 after explicit cutover. FAST stays 32k. 32k QUALITY not productive.

## 2026-09-16 evening — Productive QUALITY context is 16384

Explicit go-ahead. `local-quality` rebuilt FROM `qwen3.8:27b` with `num_ctx 16384`. Qwen `contextWindowSize` 16384. FAST stays `local-fast` 32768 and remains the default. Apply `scripts/apply-local-quality-16k.sh`. Rollback `scripts/rollback-local-quality-16k.sh` restores 8k and forces `model.name=local-fast`. Single-session Serve E2E PASS with `proceed_once`. 32k stays bench-only. `trust: false`. No YOLO.

## 2026-09-16T22:22:58.642831+02:00 — QUALITY 16k A/B-Kontrolltest Variante B erfolgreich

2026-09-16: QUALITY 16k A/B-Kontrolltest (Variante B) nach Cutover erfolgreich abgelegt. memory_load, pdf_create und pdf_read liefen fehlerfrei; PDF-Erstellung, QA und Textausgabe stimmen überein.

## 2026-09-16T22:28:38.396240+02:00 — 2026-09-16 — Variante-D KONTROLLtest OK

QUALITY 16k A/B-Kontrolltest Variante D erfolgreich

## 2026-09-16T22:36:56.354764+02:00 — QUALITY essay-control fix

2026-09-16 — QUALITY agent tool-chain uses compact memory_load, Concise output style, and skipStartupContext. max_tokens output cap was tested and reverted because it truncated pdf_create. FAST stays 32k default.

## 2026-09-16T22:42:24.440158+02:00 — QUALITY essay-control fix

Compact memory_load plus Concise style and skipStartupContext. max_tokens cap reverted. FAST stays default.

## 2026-09-16T23:04:22.737207+02:00 — QUALITY hidden-gen compact fix

Hidden post-tool tokens were Qwen auto-compact analysis, not a bug in the tool chain. context.autoCompactThreshold=0.95 with compactionModel=local-fast absorbs them; no global max_tokens cap is set (which would truncate pdf_create). FAST stays the default model; QUALITY runs vision via local-quality without pulling extra weights. E2E sequence validated: all 6 tools in order succeed, memory_update terminates the chain.

## 2026-09-21T10:16:41.186915+02:00 — QUALITY hidden-gen compact fix

Hidden post-tool tokens were Qwen auto-compact analysis. context.autoCompactThreshold=0.95 and compactionModel=local-fast. No global max_tokens. FAST stays default.

## 2026-09-21T11:00:37.367373+02:00 — A01-A14 acceptance 2026-09-21

Acceptance matrix A01-A14 executed against live stack. No new features.

## 2026-09-21T11:02:12.967782+02:00 — A01-A14 acceptance 2026-09-21

Acceptance matrix A01-A14 executed against live stack. No new features.

## 2026-09-21T11:07:54.532900+02:00 — A01-A14 QUALITY E2E 2026-09-21

A01-A14 acceptance ran a full QUALITY agent chain after the MCP boot-cycle fix. No YOLO. FAST stays default.

## 2026-09-21 — MCP starts independently of KI-Arbeitsplatz

`ki-workplace After=default.target` plus `local-tools-mcp After/Wants=ki-workplace` created a systemd ordering cycle. Boot deleted the MCP start job. Fix: both units `After=network.target`, MCP no longer Wants the workplace. Qwen Serve and ComfyUI stay disabled/demand. Hardening directives unchanged. Apply `scripts/apply-mcp-independent-boot.sh`. Rollback from `/mnt/ai-archive/backups/mcp-boot-cycle/20260921-105949`. Reboot proof still manual.

## 2026-09-21T12:28:49.734457+02:00 — Qwen 0.24.2 QUALITY E2E 2026-09-21

Runtime update installed Qwen Code 0.24.2 with the three host patches. Ollama stays 0.34.2. No YOLO. FAST stays default.

## 2026-09-21T12:32:34.689674+02:00 — decision

Runtime update installed Qwen Code 0.24.2 with the three host patches. Ollama stays 0.34.2. No YOLO. FAST stays default.

## 2026-09-21 — Runtime-Update Ollama 0.34.2 and Qwen 0.24.2

Official stables only: Ollama v0.34.2 (skip v0.34.3-rc1), Qwen Code v0.24.2 (skip treating 0.24.1 as current). systemd drop-in unchanged. Stock 0.24.2 still needs ToolSearch MCP short-name, registry resolver, and git-snapshot omit under `patches/qwen-code/0.24.2/`. Keep `/srv/ai/apps/qwen-code/lib/qwen-code.0.23.4`. Qwen rollback does not revert Ollama. `trust: false`, `approvalMode: default`, FAST default, QUALITY 16384. Compact stays 0.95 / local-fast; no extra compact patch.

## 2026-09-21 — Next image-editing candidate is Qwen-Image-2.1, plan only

Do not download weights in this phase. Official Day-0 ComfyUI support exists (20.09.2026) via Comfy-Org/Qwen-Image-2.1 and docs.comfy.org. This host still runs ComfyUI 0.33.0, which is too old for those native nodes. 16 GB VRAM cannot load the template bf16 text encoder (17.53 GB); a later build would use int8 UNet (7.26 GB) plus w4a8 or int8 encoder. License is Qwen Research License. FLUX.2 [klein] T2I stays. No FAST/QUALITY alias retarget.

## 2026-09-21 — Qwen-Image-2.1 analysis: isolated Comfy 0.37.0 first

Full plan in `docs/QWEN_IMAGE_2_1_ANALYSIS.md`. Product T2I stays `flux2-klein-t2i-v1`. Later edit path is frozen workflow `qwen-image-21-edit-v1` plus MCP `edit_image` on existing `local-tools` (not built). Recommended weights: int8 DiT + w4a8 encoder + VAE (14.25 GB). Cap v1 at 3 references and 1024 px. Do not pull bf16 encoder or 9.47 GB PE files. Next build phase is only an isolated ComfyUI v0.37.0 checkout on port 8189 plus FLUX regression. No 2.1 download in that phase. `trust: false`. No YOLO. No alias retarget.

## 2026-09-21 — ComfyUI 0.37.0 cutover after isolated FLUX PASS

Official stable v0.37.0 (`73c9bad`). Isolated :8189 FLUX 512/42 passed, then systemd cutover to `/srv/ai/apps/ComfyUI-0.37.0` + `/srv/ai/venvs/comfyui-0.37`. Torch stays 2.13.0+cu130. Autostart stays disabled. `--output-directory` keeps workplace `COMFY_OUTPUT` at `/srv/ai/apps/ComfyUI/output`. Keep 0.33.0 tree and venv. Rollback `scripts/rollback-comfyui-0.33.0.sh` from `/mnt/ai-archive/backups/comfyui-0.33.0-20260921-140000`. No Qwen-Image-2.1 weights. No `edit_image`. `trust: false`. No YOLO.

## 2026-09-21 — Qwen-Image-2.1 isolated edit smoke PASS

Exactly three official files from Comfy-Org/Qwen-Image-2.1 revision `ace0edeb` (int8 DiT, w4a8 encoder, bf16 VAE). All SHA-256 match. Isolated official-template-derived edit on :8189: 512 cold 37.86s, 1024 warm 15.22s, apple red→green, no OOM. FLUX T2I hashes unchanged. License is Qwen Research; private local test only, not commercial. Do not add `edit_image` or editing UI in this phase. Next phase is frozen workflow + workplace backend + MCP `edit_image` only. `trust: false`. No YOLO. No git push.

## 2026-09-21 — Qwen-Image-2.1 edit backend + MCP PASS

Frozen workflow `qwen-image-21-edit-v1` (SHA `78a0d0f4…`) under `apps/ki-workplace/workflows/`. Workplace `POST /api/images/edit` server-controls the graph. MCP `edit_image` on existing `local-tools` 1.3.0 (13 tools). Live 1024 edit 81.9s peak 15250 MiB; MCP 43.5s peak 15525 MiB. FLUX hashes unchanged. `trust: false`, `approvalMode: default`, no YOLO. No visible UI. Backup `/mnt/ai-archive/backups/qwen-image-21-edit-20260921-144943`. Next phase is only the workplace editing UI. No git push.

## 2026-09-22 — Compact State Ledger PASS

Runtime-built `<tool_continuity>` after auto-compact. Large successful tool results shrink to an excerpt. Double-JSON `memory_load` outputs are parsed by first-object scan. Stock compact prompt stays. Marker `linux-lokales-ki-compact-state-ledger`. QUALITY E2E session `667d9bc2`: one FAST compact, continuation 9318 tokens, six tools once each. No 32K, no YOLO, `trust: false`. Next phase is Knowledge Base v2 only. Beleg: `docs/QWEN_COMPACT_STATE_LEDGER.md`.

## 2026-09-22T11:20:04.911730+02:00 — Compact continuity ledger4

Lazy tool loading kept every MCP tool discoverable. No YOLO. FAST stays default.

## 2026-09-22T12:32:32.909734+02:00 — KB compact compact-kb

Knowledge search before compact chain. No YOLO.

## 2026-09-22T12:33:26.351250+02:00 — KB compact compact-kb

Knowledge search before compact chain. No YOLO.

## 2026-09-22T12:35:54.968520+02:00 — decision

true

## 2026-09-22 — Knowledge Base v2 PASS

Long-term knowledge lives in `.agent/knowledge/entries.jsonl` with MCP `knowledge_search` / `knowledge_get` / `knowledge_record` on local-tools **1.6.0** (32 tools, lazy). Memory stays for current state. Seeded compact/lazy/ledger/boot/roadmap facts from existing docs only. Retrieval stays compact. Continuity ledger and lazy loading remain. No 32K, no 1536, no YOLO, `trust: false`. Next phase is Supervisor/Multi-Agent only. Beleg: `docs/KNOWLEDGE_BASE_V2.md`.

## 2026-09-22 — Supervisor / Multi-Agent v1 PASS

Produktive Orchestrierung = native Qwen-0.24.2 Named Subagents, nicht Agent Team und nicht ein eigenes Framework. Supervisor `local-fast`; `researcher` `local-fast` (RO + optional Browser); `architect`/`reviewer` `local-quality` (RO). `model.maxSubagentDepth=1`. Writer SKIP (kein paralleles Schreiben auf dem Hauptworkspace). Agent Team / `/coordinate` aus. Serve braucht Symlink `/srv/ai/workspaces/.qwen/agents`. Named `subagent_type` ist Pflicht (sonst general-purpose ohne Allowlist). Agent-Call braucht non-empty `description` + `prompt`. Desktop/Images Supervisor-only. Browser Single-Owner = researcher. Plattformwahl bleibt projektabhängig (kein Android-Hardcoding). MCP bleibt 1.6.0/32. Backup `/mnt/ai-archive/backups/supervisor-multi-agent-20260922-125913`. KB `KB-20260922-SUPERVISOR-MULTI-A-001`. Beleg: `docs/SUPERVISOR_MULTI_AGENT.md`, `benchmarks/supervisor-multi-agent-20260922/`. Next: Context 24K/32K Benchmark only — no auto cutover.

## 2026-10-01 — Daily stack check: no runtime cutover

Live bleibt Ollama **0.34.4**, Qwen Code **0.24.6** (Patches), ComfyUI **0.37.0**, MCP **1.7.0**, Open WebUI **0.11.0**.

Upstream vorhanden, aber nicht eingespielt:
- Ollama **0.35.0** — Decision-Models API `/v1/systemone` (Nimble/Tev1); Linux-Fixes gering; Feature optional.
- Qwen Code **0.24.7** — keine Breaking Changes laut Notes; Managed-Runtime/ACP; unsere ToolSearch/Ledger-Patches sind chunk-gebunden → erst Port + `--check`.
- ComfyUI **0.38.0** — Qwen-Image-2.1 KV/Compile + Partner-Nodes; braucht isolierten Smoke wie bei 0.37 inkl. FLUX.2-[klein]-Regression.

**Calibri** (CVPR 2026, arXiv 2603.24800): DiT-Kalibrierung (~100 Parameter, CMA-ES) für FLUX.1-dev / SD3.5 / Qwen-Image. Offene Gates auf HF. **Nicht** für produktives FLUX.2-[klein] T2I ohne eigene Research-Phase. Kein ComfyUI-Port gefunden.

Kein sudo/Runtime-Install heute. `trust: false` bleibt.

## 2026-10-02 — Runtime-Update Ollama 0.35.0 / Qwen 0.24.7 / ComfyUI 0.38.0 PASS

Explizite Freigabe zum kontrollierten Runtime-Update. Live vorher: Ollama 0.34.4, Qwen 0.24.6, ComfyUI 0.37.0 (nicht die älteren Prompt-Annahmen 0.34.2/0.24.2).

- Ollama **0.35.0** Stable (nicht 0.35.1-rc). Override unverändert (SHA `7fb44d5f…`). Modelle/Aliase unangetastet.
- Qwen Code **0.24.7** Stable. Patches neu portiert nach `patches/qwen-code/0.24.7/` (ToolSearch inkl. `collectCandidates(bindings)`, Registry, Git-Omit, Compact State Ledger). Keep `/srv/ai/apps/qwen-code/lib/qwen-code.0.24.6`.
- ComfyUI **0.38.0** Stable. FLUX PASS. Qwen-Image-2.1 Edit braucht **`--disable-comfy-compiler`** (sonst `aimdo memory compile error`). Workplace `COMFY_INPUT` → `ComfyUI-0.38.0/input`.
- Additive Context-Probe 16/24/32K ohne schwere Artefakte; **`local-quality` bleibt 16384**. Kein Cutover.
- Backup `/mnt/ai-archive/backups/runtime-update-20261002-084919`. `trust: false`, kein YOLO.
- Next: Serve/Agent-E2E vor optionalem QUALITY-Context-Cutover.
