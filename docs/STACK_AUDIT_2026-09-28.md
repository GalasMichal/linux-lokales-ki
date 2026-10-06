# Stack Audit — 2026-09-28

Erstellt: 2026-09-28T11:55+02:00. **Nur Ist-Zustand. Keine Änderungen in dieser Datei-Phase.**

Projekt: `/home/mike/Projects/Linux Lokales KI`  
Handoff-SoT (vor diesem Audit): `docs/CHATGPT_HANDOFF.md` (Stand 22.09.2026, Supervisor/Multi-Agent PASS).

Runtime-Update 28.09.: Ollama **0.34.4** PASS, Qwen **0.24.6** PASS, llama.cpp **v0.5.0/b11146** CPU, GGUF Q4_K_S **SHA-verified**, CPU-Smoke/Bench/Parallel/8K **PASS**. On-demand MoE MCP `moe_consult` → MCP **1.7.0 / 33 Tools** PASS. PDF Agent E2E **PASS** (`docs/PDF_AGENT_E2E_2026-09-28.md`). Open WebUI weiter 0.11.0 `:main` (Prepare only). Backup: `/mnt/ai-archive/backups/runtime-moe-20260928-20260928-125042/`. Results: `benchmarks/moe_cpu_2026-09-28/RESULTS.md`, `benchmarks/moe_ondemand_2026-09-28/`, `benchmarks/pdf_agent_e2e_2026-09-28/`.

---

## 1. Git

| Feld | Wert |
|------|------|
| Repo | `/home/mike/Projects/Linux Lokales KI` |
| Branch | `codex/ki-arbeitsplatz` (ahead of `origin` by 5) |
| HEAD | `abd0282f0939a321d4735b1579b68a86c1c7e61d` |
| Letzte Commits | FAST 32K context; image tool MCP size/seed; local tools MCP; Qwen skills; KI-Arbeitsplatz |

**Working tree:** sehr viele uncommitted Änderungen (Modified + Untracked) seit den Phasen Memory/PDF/Browser/Desktop/Lazy/Ledger/KB/Supervisor/Image-2.1. Kein Push empfohlen ohne explizite Freigabe. Diff-Stat grob: ~29 tracked files geändert (+2867/−231) plus große untracked Bäume (`.agent/`, `benchmarks/`, `docs/`, `patches/`, `apps/local-tools/*`, …).

---

## 2. System

| Feld | Wert |
|------|------|
| CPU | Intel Core i9-14900KF — 24 Cores / 32 Threads (P+E), max 6000 MHz |
| RAM | 31 Gi total; ~11 Gi used / ~19 Gi available (Audit-Zeitpunkt); Swap 52 Gi (0 used) |
| GPU | NVIDIA GeForce RTX 5080, 16303 MiB VRAM |
| Treiber | 595.99.02 |
| CUDA (nvidia-smi) | 13.2 |
| CUDA Toolkit (nvcc/rpm) | nicht installiert / n/a |
| Compute Cap | 12.0 |
| OS | Nobara Linux (Kernel aus User-Info zuvor: fedora/nobara) |

**Speicher:**

| Mount | Größe | Belegt | Frei |
|-------|-------|--------|------|
| `/` und `/srv/ai` (`/dev/sda3` btrfs unter `/home`) | 921 G | ~818 G (90 %) | ~101 G |
| `/mnt/ai-archive` (`/dev/sdc1` NTFS) | 1,4 T | ~1,1 T | ~308 G |
| NVMe `nvme0n1` | 954 G | Windows/NTFS-Partitionen, **nicht** als Linux-AI-Root gemountet |

Hinweis: Schneller AI-Workspace liegt auf der Crucial-SATA-SSD unter `/srv/ai` (gleicher FS wie `/home`), nicht auf dem NVMe. Für große GGUF-Downloads: Platz auf `/` (~101 G frei) und Archiv (~308 G) prüfen.

---

## 3. KI-Stack (Versionen)

| Komponente | Installiert | Pfad / Hinweis |
|------------|-------------|----------------|
| **Qwen Code** | **0.24.6** | `/srv/ai/apps/qwen-code` (`bin/qwen`, `lib/qwen-code`; Keep `qwen-code.0.24.2`) |
| Qwen-Patches | aktiv | ToolSearch MCP-Alias, Registry Kurzname, Git-Snapshot-Omit, Compact State Ledger (`--check` OK) |
| **Ollama** | **0.34.4** | `/usr/local/bin/ollama`, Models env `/srv/ai/models/ollama` (nur Service-User lesbar) |
| Ollama-Override | unverändert | localhost, `MAX_LOADED_MODELS=1`, Flash Attention, KV `q8_0`, Keep-Alive 5m, `NUM_PARALLEL=1` |
| **Open WebUI** | **0.11.0** | Podman Container `open-webui`, Image `ghcr.io/open-webui/open-webui:main`, Port `127.0.0.1:3000→8080` |
| **llama.cpp** | **v0.5.0 / b11146 CPU** | `/srv/ai/apps/llama.cpp-0.5.0/` (kein systemd) |
| MCP local-tools | **1.7.0 / 33 Tools** | User-Unit, venv `local-tools-20260922-121004`, `127.0.0.1:8765`, inkl. `moe_consult` |
| KI-Arbeitsplatz | aktiv | `/srv/ai/apps/ki-workplace`, Ports **8790/8791** (nicht 8787) |
| ComfyUI | **0.37.0** Tree `73c9bad` unter `/srv/ai/apps/ComfyUI-0.37.0`; älteres `ComfyUI` `cc0fc21` | Service aktuell **nicht** listening auf 8188 |
| Python | 3.14.7 (Host); MCP-venv 3.14 | mehrere `/srv/ai/venvs/*` |
| Podman | 5.8.4 | Open WebUI darüber |
| Docker | nicht als Default genutzt | — |

**Vorbereitet, nicht live (Cache 25.09.):**

- Ollama 0.34.4 Extract: `/srv/ai/cache/ollama-0.34.4/extract/`
- Qwen 0.24.5 Tarball + isoliertes Inspect: `/srv/ai/cache/qwen-code-0.24.5/`

---

## 4. Modelle

### Ollama (produktiv)

| Alias / Tag | ID (kurz) | Größe | Rolle |
|-------------|-----------|-------|-------|
| **local-fast** | cf8bd43c0e1c | 6.6 GB | **Default / Haupt-Coding-Agent (Qwen Serve Default)** — Qwen3.5 9B, `num_ctx` **32768** |
| **local-quality** | ad1736a075f0 | 17 GB | Architektur/Review/Vision-QA — Qwen3.8 27B, `num_ctx` **16384** |
| qwen3.5:9b | 6488c96fa5fa | 6.6 GB | Basis FAST |
| qwen3.8:27b | 22130167c4c2 | 17 GB | Basis QUALITY |
| qwen3.6:27b / coding | … | 17 GB | Bench/Alt |
| bench-qwen38-27b-{8k,16k,32k} | … | 17 GB | Context-Benchmarks (32k unangetastet produktiv) |
| bench-qwen36-coding-8k | … | 17 GB | Bench |

### GGUF

**0 Dateien** gefunden unter `/srv/ai`, `/mnt/ai-archive`, Projektbaum. Kein CPU-MoE-Modell lokal vorhanden.

### Bild

ComfyUI-Modelle unter `/srv/ai/models/comfyui` (~25 G). FLUX T2I + Qwen-Image-2.1 Edit (frozen Workflow) laut Handoff; Comfy-Port 8188 derzeit down.

---

## 5. Services / Ports / Autostart

| Dienst | Status | Bind | Autostart |
|--------|--------|------|-----------|
| `ollama.service` (system) | active | `127.0.0.1:11434` | enabled |
| `local-tools-mcp.service` (user) | active | `127.0.0.1:8765` | enabled |
| `ki-workplace.service` (user) | active | `127.0.0.1:8790` / `8791` | enabled |
| `qwen-code-web.service` (user) | **inactive** | würde `127.0.0.1:4170` | disabled |
| Podman `open-webui` | Up | `127.0.0.1:3000` | (Container; Image-Tag `:main`) |
| ComfyUI :8188 | **down** | — | kein `comfyui.service` gefunden |

**Health (Audit):**

- Ollama tags: 200  
- MCP `/health`: 200, version 1.7.0, 33 tools (inkl. `moe_consult`)  
- Qwen Serve / Workplace 8787 / Comfy / OWUI-Root 8080: nicht erreichbar wie erwartet (andere Ports / offline)  
- Open WebUI API: `http://127.0.0.1:3000/api/version` → `0.11.0`

### Relevante Configs

- `~/.qwen/settings.json` — Default `local-fast`, `trust:false`, `approvalMode:default`, Lazy MCP, Compact 0.95 / `local-fast`, `maxSubagentDepth:1`
- `/etc/systemd/system/ollama.service.d/override.conf`
- `~/.config/systemd/user/{qwen-code-web,ki-workplace,local-tools-mcp}.service`
- Repo: `.qwen/agents/{researcher,architect,reviewer}.md` + Symlink `/srv/ai/workspaces/.qwen/agents`
- MCP: `apps/local-tools/`, Deploy-Unit auf `/srv/ai`

---

## 6. Qwen-Einstellungen (Kurz)

| Setting | Wert |
|---------|------|
| Default model | `local-fast` |
| FAST context | 32768 |
| QUALITY context | 16384 |
| Compact threshold | 0.95 |
| Compaction model | `local-fast` |
| Lazy tools | `alwaysLoadTools: false`, visible leer, 32 includeTools |
| Security | `trust: false`, kein YOLO, Shell disabled |
| Supervisor agents | researcher / architect / reviewer |
| Agent Team | aus |

---

## 7. Risiken / Hinweise für Folgephasen

1. **Disk `/` bei 90 %** — große GGUF-Downloads nur nach Freigabe und Platzplanung.  
2. **Open WebUI Image-Tag `:main`** — floating Tag, kein Pin auf SemVer-Image; Updates können still ziehen.  
3. **Runtime-Update 0.34.4/0.24.5** vorbereitet, braucht sudo + Regression vor Cutover.  
4. **Kein llama.cpp** — CPU-MoE braucht neue Runtime oder Ollama-CPU-Pfad.  
5. **Qwen Serve oft aus** — für Agent-E2E bewusst starten.  
6. **ComfyUI nicht dauerhaft up** — Bild-Regression nur bei Bedarf starten.  
7. Viele **uncommitted** Änderungen — Update/MoE-Arbeit nicht mit unklarem Git-Commit vermischen.

---

## 8. Nächster Schritt (nach diesem Audit)

Phase 2: Update-Prüfung (Qwen / Ollama / Open WebUI / llama.cpp) gegen stabile Releases — **nur prüfen und dokumentieren**. Installation nur nach Freigabe (sudo / Container-Pull).

Danach Phase 3–4: MoE-Runtime-Entscheidung und **einmalige Freigabe** vor Download von Qwen3-Coder-30B-A3B GGUF.
