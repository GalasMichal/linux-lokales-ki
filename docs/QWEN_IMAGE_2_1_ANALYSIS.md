# Qwen-Image-2.1 — Analyse und Implementierungsplan

Stand: 21.09.2026 15:17. **Stufen 1–7 plus sichtbare UI erledigt** (ComfyUI **0.37.0** live, drei 2.1-Gewichte, isolierter Smoke PASS, frozen Edit-Workflow, `POST /api/images/edit`, MCP `edit_image`, KI-Arbeitsplatz **Bearbeiten** **PASS**).

SoT: [`docs/CHATGPT_HANDOFF.md`](CHATGPT_HANDOFF.md) (21.09.2026 15:17).  
Edit-Bericht: [`docs/QWEN_IMAGE_2_1_EDIT.md`](QWEN_IMAGE_2_1_EDIT.md).  
UI-Bericht: [`docs/QWEN_IMAGE_2_1_EDIT_UI.md`](QWEN_IMAGE_2_1_EDIT_UI.md).  
Smoke-Bericht: [`docs/QWEN_IMAGE_2_1_SMOKE.md`](QWEN_IMAGE_2_1_SMOKE.md).  
Upgrade-Bericht: [`docs/COMFYUI_0_37_UPGRADE.md`](COMFYUI_0_37_UPGRADE.md).  
Nächste erlaubte Bau-Phase: **Open-WebUI als MCP-Client** für `generate_image` / `edit_image`. Kein neues Modell.

---

## 0. Empfehlung (kurz)

**Ja, als lokales Image Editing auf dieser Box sinnvoll** — aber nur mit Quantisierung, nur nach ComfyUI **0.37.0**, und nur nicht-kommerziell (Qwen Research License).

| Frage | Antwort |
|-------|---------|
| Einsetzbar auf RTX 5080 16 GB / 32 GB RAM? | **Ja, gemessen.** Kandidat 1: 512 kalt 37,86 s Peak 15509 MiB; 1024 warm 15,22 s Peak 15618 MiB. Eng, aber stabil. |
| bf16-DiT oder bf16-Encoder? | **Ungeeignet.** Encoder 17,53 GB allein größer als der VRAM. |
| ComfyUI | Live **0.37.0** (`73c9bad`, Tree `/srv/ai/apps/ComfyUI-0.37.0`). 0.33.0 `cc0fc21` bleibt als Keep. Native 2.1-Nodes vorhanden. |
| Download | **erledigt 14:22.** 14,25 GB, alle SHA offiziell. Keine PE-9,47-GB-Dateien. Frei danach **120 G**. |
| SSD zusätzlich | ~13 G unter `/srv/ai/models/comfyui`. Archiv 309 G. |
| Laufzeit/Bild | 512 kalt **37,86 s**; 1024 warm **15,22 s** (25 Schritte, Euler/simple, Cache cpu/int8). |
| Erster Schritt nach Smoke | **erledigt 14:56.** Frozen Workflow + Backend + `edit_image`. Sichtbare UI **PASS 15:17.** |

Produkt-T2I bleibt **FLUX.2 [klein] 4B** (`flux2-klein-t2i-v1`). Qwen-Image-2.1 ist ein **zweiter, fest verdrahteter Edit-Workflow**, kein Ersatz.

---

## 1. Aktueller Bild-Stack (unverändert erfasst)

Erfasst 21.09.2026 ~12:45. Nichts geändert.

| Größe | Ist |
|-------|-----|
| ComfyUI | `/srv/ai/apps/ComfyUI-0.37.0`, **0.37.0**, Git `73c9bad`. Keep `/srv/ai/apps/ComfyUI` 0.33.0 `cc0fc21` |
| Python | `/srv/ai/venvs/comfyui-0.37/bin/python` **3.13.15** (0.33-Venv unangetastet) |
| Torch | **2.13.0+cu130**, CUDA 13.0, `torch.cuda.is_available()=True` |
| Custom Nodes | **keine** produktiven. Nur `example_node.py.example`, `websocket_image_save.py` |
| `extra_model_paths.yaml` | `base_path=/srv/ai/models/comfyui` |
| Unit | `~/.config/systemd/user/comfyui.service`: `--listen 127.0.0.1 --port 8188 --output-directory /srv/ai/apps/ComfyUI/output`, **disabled**, **inactive** |
| NVIDIA | RTX 5080, Treiber aus Abnahme 595.99.02, 16303 MiB |
| RAM | 31 Gi + Swap 52 Gi |
| Frei `/` (`/srv/ai` gleiche Platte) | 145 G / 921 G |
| Frei `/mnt/ai-archive` | 309 G / 1,4 T |

### Vorhandene Gewichte (FLUX.2 [klein] only)

| Datei | Größe |
|-------|------:|
| `diffusion_models/flux-2-klein-4b-fp8.safetensors` | 4,07 GB |
| `text_encoders/qwen_3_4b.safetensors` | 8,04 GB |
| `vae/flux2-vae.safetensors` | 0,34 GB |
| Summe | **12 G** |

Qwen-Image-2.1 seit 21.09.2026 14:22 auf der Platte (int8-DiT + w4a8-Encoder + VAE). FLUX-Dateien unverändert.

### Workflows

| Pfad | Rolle |
|------|--------|
| `apps/ki-workplace/workflows/flux2-klein-t2i-api-v1.json` | **Produktiv.** API-Graph für Einfach-Ansicht + MCP `generate_image`. Nodes: `UNETLoader`, `CLIPLoader` type `flux2`, `VAELoader`, `EmptyFlux2LatentImage`, Euler 4 Schritte, CFG 1.0, max 1024. |
| `/srv/ai/workflows/comfyui/image_flux2_klein_text_to_image.json` | Offizielle T2I-Vorlage (Expertenmodus). |
| `/srv/ai/workflows/comfyui/image_flux2_klein_image_edit_4b_distilled.json` | Offizielle **FLUX**-Edit-Vorlage. **Nicht verdrahtet**, nicht MCP, nicht UI. |
| `/srv/ai/workflows/comfyui/blueprint_image_edit_flux2_klein_4b.json` | Blueprint, ungenutzt. |

FLUX-Edit-JSONs **nicht** für Qwen-Image-2.1 verwenden. Sie bleiben Archiv/Experten-Material.

### KI-Arbeitsplatz / GPU-Sequenz

1. Bildermodus: Ollama entladen, ComfyUI starten (`POST /api/mode/images`).
2. Generate: `POST /api/images/generate` → Comfy `/prompt` → History-Poll max **240 s** → Kopie nach `/mnt/ai-archive/images/inbox/JJJJ-MM-TT/JOB-ID/` + `manifest.json`.
3. Archiv-HDD nicht gemountet → Abbruch, kein Schreiben auf `/`.
4. Letztes KI-Fenster: wartet auf laufenden Job, stoppt Qwen+Comfy, entlädt Ollama.
5. Agent-Modus stoppt ComfyUI.

Bekannte A12-Einschränkung: Qwen Serve `:4170` kann während Generate noch laufen; GPU-Modelle sind dann schon entladen. Cleanup stoppt beides.

### MCP `generate_image`

`apps/local-tools/server.py` + `gateway.py`. Nur Workflow-ID `flux2-klein-t2i-v1`. Größen 512/768/1024. Prompt ≤ 4000 Zeichen. Timeout 300 s + Cleanup 300 s. Kein Graph aus dem Prompt. Pfade für andere Tools: `paths.py` Roots `/home/mike/Projects`, `/srv/ai/workspaces`, `/mnt/ai-archive`, `/tmp`, `/var/tmp`. `generate_image` selbst nimmt **keine Dateipfade**.

### Manifest (bestehend)

`manifest_version: 1`, `job_id`, Comfy `prompt_id`, `workflow_id`/`workflow_sha256`, Modellpfade + SHA-256, Prompt, Seed, Breite/Höhe, Batch/Steps/CFG/Sampler, Zeiten, `runtime_seconds`, Output-Kopien.

### T2I-Baseline (A12, 21.09.2026)

512×512 Seed 42: **64,857 s**, Job `b8d57bc6dd22`, Cleanup VRAM **1795 MiB**, Comfy danach inactive. Workflow-SHA `d9d752d5…`.

### Backups / Rollback (UI/Comfy, nicht Modelle)

- UI: `scripts/deploy-local-ui.sh` → `/mnt/ai-archive/backups/ki-ui/<stamp>/`; Rollback `scripts/rollback-local-ui.sh`.
- MCP-Boot: `scripts/rollback-mcp-independent-boot.sh`.
- **Kein** datiertes ComfyUI-Tree-Backup-Skript. Vor 0.37.0-Wechsel: `cp -a /srv/ai/apps/ComfyUI` und venv extra sichern.
- Runtime-Update-Backup: `/mnt/ai-archive/backups/runtime-update-20260921-120433` (Ollama/Qwen, nicht Comfy-Gewichte).

---

## 2. Offizielle Qwen-Image-2.1-Daten

Quellen (21.09.2026 gelesen, Firecrawl + GitHub/HF API):

- [QwenLM/Qwen-Image-2.1](https://github.com/QwenLM/Qwen-Image-2.1) README + LICENSE
- [qwen.ai Blog 20.09.2026](https://qwen.ai/blog?id=qwen-image-2.1)
- [Qwen/Qwen-Image-2.1](https://huggingface.co/Qwen/Qwen-Image-2.1)
- [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1) Dateigrößen per HF API
- [ComfyUI Docs Qwen-Image-2.1](https://docs.comfy.org/tutorials/image/qwen/qwen-image-2-1)
- [Comfy Blog 20.09.2026](https://blog.comfy.org/p/qwen-image-21-in-comfyui-open-weight)
- [Comfy-Org/ComfyUI v0.37.0](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.37.0), PR [#16400](https://github.com/Comfy-Org/ComfyUI/pull/16400)

Nicht als Tatsache werten: Foren, YouTube, Thundercompute, Reddit.

### Status

Open-Weight, Release **20.09.2026**. ComfyUI native Day-0. Diffusers `QwenImage21Pipeline` (GitHub: `transformers>=5.17`, `torch>=2.4`). **Dieser Plan nutzt ComfyUI, nicht Diffusers als Produktivpfad.**

### Architektur (Upstream)

- Visuelle Komponente: **7B**, 32 Single-Stream-DiT-Schichten.
- Text-Encoder: **Qwen3-VL-8B** (Comfy: `qwen3vl_8b_*`).
- VAE: 64-Kanal **RGBA**, 16× räumliche Kompression (PR #16400: Wan-2.2-Modul, neue Args defaulten auf alt).
- Mixed-granularity Attention + Prefix-KV-Cache für Edits (~1,7× laut PR, nicht auf dieser Box gemessen).

### Fähigkeiten (Qwen-Repo/Blog)

| Fähigkeit | Offiziell |
|-----------|-----------|
| Text-to-Image | ja, natives 2K (2048²) |
| Single-Image-Edit | ja, Instruction |
| Multi-Reference | **bis 10** Referenzbilder (Blog/README) |
| Comfy-Node-Slots | Docs: `image_1`…`image_16`; Prompt `<image1>`. Modell-Fähigkeit bleibt 10 — Produktlimit **enger** setzen. |
| RGBA | ja, Prompt steuert RGB vs. Transparent |
| Lokale Edits | Kreise, Paint, separate Maske |
| Formate | nicht als geschlossene Liste. Praxis: PNG (RGBA), JPEG über `LoadImage`. |
| Sampler in Comfy-Templates | 25 Schritte, CFG 1, Euler, Scheduler `simple` |

### Lizenz

**Qwen RESEARCH LICENSE AGREEMENT**, 20.09.2026, Hangzhou Tongyi Laboratory.

- Nutzung **nur Non-Commercial** (Research/Evaluation), ohne separate kommerzielle Lizenz (`model-business@notice.qwencloud.com`).
- Kein Apache/MIT.
- Outputs zum Trainieren anderer veröffentlichter Modelle: Hinweis „Built with Qwen“.
- Recht Hangzhou/China.

Für Michal: privates Lernen und lokale Tests auf diesem Rechner passen zur Research-Lizenz. **Verkauf, Kundenjobs, öffentliche Produkt-API damit: nicht ohne Extra-Lizenz.** FLUX.2-[klein] für T2I bleibt der andere, bereits installierte Weg.

### Comfy-Nodes (PR #16400, in v0.37.0)

- `TextEncodeQwenImage21` — Positiv/Negativ + leeres Latent auf dem Referenz-Raster (andere Größe verschiebt das Edit).
- `QwenImage21Cache` — KV-Cache `device`: auto/gpu/cpu/off; `dtype`: default/int8/int4.

0.33.0 enthält diese Nodes **nicht** (`rg` leer).

### Bekannte offizielle Einschränkungen / Divergenzen

- Comfy-Template lädt standard **int8-DiT + bf16-Encoder**. bf16-Encoder **17,53 GB** — auf 16 GB VRAM unbrauchbar. Unser Graph muss Encoder auf **w4a8 oder int8** festnageln.
- Comfy weicht bei Referenz-Grids um ein halbes Token ab, wenn die Parität vom Ziel abweicht (PR #16400).
- Docs: Image-Edit-Ausgabe folgt `image_1`-Seitenverhältnis, skaliert auf `resolution` (Default 1024), **nicht** die Originalpixelgröße, außer `resolution=0`.
- 2K (4 MP) auf 16 GB: offiziell nicht als 16-GB-Ziel genannt. **Nicht als Default.**
- Qualitätsverlust int8/w4a8 vs. bf16: **keine offizielle dB-/FID-Zahl** für genau dieses Paar. Erst Smoke bewerten.
- Prompt-Rewrite-Dateien auf HF (`qwen3.5_9b_*_pe_*.safetensors`, je 9,47 GB) stehen **nicht** in den Comfy-Templates. **Nicht ziehen.**

---

## 3. Varianten und Speicher

HF `Comfy-Org/Qwen-Image-2.1` (API 21.09.2026):

| Datei | Download | Rolle |
|-------|---------:|--------|
| `qwen_image_2.1_int8_convrot.safetensors` | 7,26 GB | DiT, Template-Default, „lower memory“ |
| `qwen_image_2.1_bf16.safetensors` | 14,23 GB | DiT voll |
| `qwen3vl_8b_bf16.safetensors` | 17,53 GB | Encoder, **Template-Default** |
| `qwen3vl_8b_int8_convrot.safetensors` | 9,35 GB | Encoder int8 |
| `qwen3vl_8b_w4a8.safetensors` | 6,31 GB | Encoder 4-bit weights |
| `qwen_image_2.1_vae_bf16.safetensors` | 0,68 GB | VAE RGBA |
| `qwen3.5_9b_*_pe_*.int8_convrot` (2×) | je 9,47 GB | Prompt-Enhance, **nicht Template** |

VRAM ≠ Dateigröße. Aktivierungen, KV-Cache und gleichzeitiges Encoder+DiT zählen extra. Auf 16 GB seriell + CPU-Prefix-Cache (`QwenImage21Cache` `device=cpu`): **gemessen** Peak 15509 MiB (512) / 15618 MiB (1024). RAM-Peak ~24 Gi, Swap-Peak ~7,6 Gi. Kein OOM.

### Kandidaten

| # | Kombo | SSD | Gleichzeitiges Gewicht | 16 GB | Urteil |
|---|--------|----:|-----------------------:|-------|--------|
| **1** | int8-DiT + **w4a8**-Encoder + VAE | 14,25 GB | ~14,3 GB Dateien; Peak ungemessen, Ziel mit CPU-Cache und 1024² / ≤3 Refs | eng, aber der einzige realistische | **Empfohlen** |
| 2 | int8-DiT + int8-Encoder + VAE | 17,29 GB | Encoder 9,35 + DiT 7,26 gleichzeitig riskant | schlechter als 1 | Reserve, falls w4a8 Artefakte |
| 3a | bf16-DiT + irgendein Encoder | ≥14,23 GB DiT | DiT allein fast volles VRAM | **ungeeignet** | |
| 3b | irgendein DiT + bf16-Encoder | 17,53 GB Encoder | Encoder größer als GPU | **ungeeignet** | |

RAM 32 GB: CPU-Offload/Prefix-Cache möglich. Diffusers-README nennt `enable_model_cpu_offload()` für knappes VRAM — Comfy-Äquivalent ist Cache-Node `cpu` plus Comfy Auto-VRAM, nicht ein zweiter Diffusers-Stack.

Temp: Comfy `output/` + Archiv-Kopie. PNG 1024² RGBA ≈ wenige MB bis ~20 MB. Limit später z. B. 25 MB Eingabe, 4096 px Kante.

Geschwindigkeit: Template 25 Schritte vs. FLUX 4. Gemessen: 512-Edit kalt 37,86 s, 1024 warm 15,22 s — in der Größenordnung FLUX-T2I, nicht langsamer sobald die Gewichte geladen sind.

---

## 4. ComfyUI-Upgrade 0.33.0 → 0.37.0

| | 0.33.0 live | Ziel 0.37.0 |
|--|-------------|-------------|
| Tag | (Commit `cc0fc21`, pyproject 0.33.0) | GitHub **v0.37.0**, published 2026-09-21T07:35Z, prerelease=false |
| Qwen-Image-2.1 | nein | ja, PR #16400 + Templates 0.11.65/66 |
| Python | ≥3.10, hier 3.13.15 | ≥3.10, unverändert in pyproject |
| Torch im venv | 2.13.0+cu130 | `requirements.txt` pinnt bei 0.33 nur `torch`. 0.37 Release erwähnt CUDA-12.9 nur für **Windows Portable**-Script. Linux-Manual: bestehenden NVIDIA-Torch **nicht** leichtfertig ersetzen. |
| Frontend | comfyui-frontend-package 1.49.6 | Release: 1.53.6 |
| Kitchen | 0.2.31 | 0.2.35 |
| Custom Nodes | keine | geringeres Risiko |

### Breaking / FLUX

Zwischen 0.33 und 0.37 liegen mehrere Minors. Offizielle 0.37-Notes listen Qwen-2.1, Qwen3 w4a8/cudagraphs, Partner-Nodes — **kein explizites „FLUX.2 klein broken“**. Trotzdem: `EmptyFlux2LatentImage` / `CLIPLoader type=flux2` **müssen** nach Upgrade dieselben API-Jobs akzeptieren. Das ist die Stop-Bedingung von Stufe 2.

### Isolierter Test-Checkout: ja

Nicht in-place `git pull` auf `/srv/ai/apps/ComfyUI`.

Geplanter Weg (spätere Phase, nicht jetzt):

1. Archiv-HDD muss gemountet sein.
2. `cp -a /srv/ai/apps/ComfyUI /mnt/ai-archive/backups/comfyui-0.33.0-<stamp>/tree`
3. `cp -a /srv/ai/venvs/comfyui /mnt/ai-archive/backups/comfyui-0.33.0-<stamp>/venv` (groß, 6 G — oder venv-Pfad + `pip freeze`).
4. Clone **tag v0.37.0** nach `/srv/ai/apps/ComfyUI-0.37.0`.
5. Gleiche `extra_model_paths.yaml` (Modelle bleiben unter `/srv/ai/models/comfyui`).
6. Entweder neues venv `comfyui-0.37` aus 0.37-`requirements.txt` **mit dem bestehenden Torch, wenn Import klappt**, oder Kopie des 0.33-venv plus gezielte Package-Pins (frontend/kitchen/templates).
7. Test-Start: `python main.py --listen 127.0.0.1 --port 8189` (nicht 8188), FLUX-API-Graph einmal.
8. Erst nach PASS systemd `WorkingDirectory`/`ExecStart` auf 0.37 umbiegen; 0.33-Tree behalten.

Rollback: Unit wieder auf `/srv/ai/apps/ComfyUI` + altes venv. Gewichte unangetastet.

Sudo: Comfy liegt unter `/srv/ai` (User mike). **Kein Root** für Tree/venv. kdialog nur falls später Systempakete — nicht vorgesehen.

---

## 5. Workflow-Architektur (Plan)

```
KI-Arbeitsplatz (8790)
  ├─ Einfach T2I     → flux2-klein-t2i-v1          → generate_image
  ├─ Einfach Edit    → qwen-image-21-edit-v1       → edit_image (neu)
  └─ Experte         → volle Comfy-UI :8188 (unverändert)
       ↓
  ensure_image_mode (Ollama unload, Comfy start)
       ↓
  fest verdrahteter JSON-Graph (keine Agent-Graphen)
       ↓
  /mnt/ai-archive/images/inbox/JJJJ-MM-TT/JOB-ID/
       ↓
  GPU-Cleanup wie heute
```

### Feste IDs

- `flux2-klein-t2i-v1` — unverändert.
- `qwen-image-21-edit-v1` — Single- und Multi-Ref in **einem** Graphen: `image_1` Pflicht, `image_2`/`image_3` optional leer.
- Kein zweiter MCP-Server. Kein frei übergebbarer Comfy-Prompt-JSON.

### Edit-Graph (Inhalt)

Aus offiziellem Template `image_qwen_image_2_1_image_edit.json`, **eingefroren** im Repo unter `apps/ki-workplace/workflows/`, mit festen Dateinamen:

- DiT: `qwen_image_2.1_int8_convrot.safetensors`
- Encoder: `qwen3vl_8b_w4a8.safetensors` (nicht bf16)
- VAE: `qwen_image_2.1_vae_bf16.safetensors`
- `QwenImage21Cache`: `device=cpu`, `dtype=int8` (weniger VRAM; Docs: int8 halbiert Cache)
- `steps=25`, `cfg=1`, Euler, `resolution=1024` default, max 1024 in der Einfach-UI
- Seed durch Workplace gesetzt
- SaveImage-Prefix `ki_arbeitsplatz_{job_id}` wie T2I

Referenzen: Dateien aus erlaubten Roots nach Comfy `input/` **kopieren** (nicht Agent-Pfad als Comfy-Pfad durchreichen). Danach Temp löschen.

### Limits v1

| Limit | Wert |
|-------|------|
| Referenzbilder | 1 Pflicht + max 2 extra (**3 total**). Offiziell 10; 16 GB und Prompt-Komplexität begrenzen. |
| Eingabe | PNG/JPEG/WebP, max 25 MiB, max 4096 px Kante, keine URL, kein Base64 im Agent-Prompt |
| Größen UI | 512 / 768 / 1024 (wie T2I). 2K erst nach gemessenem VRAM. |
| Timeout | 420 s Generate-Poll (Edit 25 Schritte) |
| Alpha | `preserve_alpha` default false; true setzt Instruction-Präfix laut Qwen-README für RGBA |

### Manifest-Erweiterung (neben bestehenden Feldern)

`workflow_id=qwen-image-21-edit-v1`, Quantisierung (`dit=int8`, `encoder=w4a8`), `instruction`, `input_sha256`, `reference_sha256[]`, `preserve_alpha`, `error` null oder Text, `vram_peak_mib` wenn `nvidia-smi` greift.

---

## 6. MCP `edit_image` (Plan, nicht gebaut)

Gleicher Server `local-tools`. Kurzname `edit_image` → `mcp__local-tools__edit_image`. `trust: false`, Vote `proceed_once`, `alwaysLoadTools: true`, Eintrag in `includeTools` + `tools.visible`.

Vorschlag Schema:

- `instruction` (string, Pflicht, ≤ 4000)
- `input_path` (string, Pflicht)
- `reference_paths` (string[], optional, max 2)
- `width`/`height` enum 512/768/1024, default 1024
- `seed` int, default 42
- `preserve_alpha` bool, default false
- **kein** `workflow_id` vom Modell — Konstante im Server

Gateway analog `generate_image_via_workplace` → neues `POST /api/images/edit`. Pfadprüfung `resolve_existing_file` mit Suffix `{.png,.jpg,.jpeg,.webp}`. Nach Job Cleanup wie T2I.

Rückgabe: `ok`, `job_id`, `output_path`, `manifest_path`, Hashes, `runtime_seconds`, `workflow_id`, `quantization`, `error`.

Kein Shell-Ersatz. Kein Graph-Feld.

---

## 7. UI (umgesetzt 21.09.2026 15:17)

Bilder-Ansicht: Subnav **Erzeugen | Bearbeiten | Workflow (Experte)**. Bericht: [`docs/QWEN_IMAGE_2_1_EDIT_UI.md`](QWEN_IMAGE_2_1_EDIT_UI.md).

- Ausgangsbild über Datei-Dialog (PNG/JPEG/WebP), kleine Vorschau
- Edit-Anweisung, max. 4000 Zeichen
- optional 1–2 Referenzbilder
- Seed, Größe 512/768/1024, `preserve_alpha`
- Staging `POST /api/images/stage`, danach bestehendes `POST /api/images/edit`
- Ergebnis + Job-ID + Archiv/Manifest; Experte und FLUX-Form bleiben

Keine Browser-Automatisierung, kein zweites Fenster-System, kein allgemeiner Dateibrowser.

---

## 8. Ressourcen- und Sicherheitsablauf

1. Qwen Serve stoppen (strenger als heutiges Generate: A12-Lücke schließen, wenn Edit startet).
2. Ollama `/api/ps` leer.
3. `nvidia-smi` free ≥ 2000 MiB sonst Abbruch.
4. ComfyUI starten, `/system_stats` ≤ 45 s.
5. Prüfen: drei 2.1-Dateien existieren, Comfy-Version ≥ 0.37.0 (sonst Abbruch „ComfyUI zu alt“).
6. Graph senden, History-Poll.
7. Archiv + Manifest; defekte/fehlende PNG → Fehler, kein Fake-PASS.
8. Comfy stoppen.
9. VRAM-Probe (Ziel in der Größenordnung T2I-Cleanup, nicht QUALITY-14 GB).
10. Agent-Modus nur wenn der Nutzer Agent öffnet.

### Abbruch

| Bedingung | Aktion |
|-----------|--------|
| `/` frei &lt; 20 G oder Archiv frei &lt; 5 G | kein Start |
| RAM available kritisch (z. B. &lt; 4 Gi) | kein Start |
| VRAM free &lt; 2 Gi nach Unload | kein Start |
| Archiv nicht gemountet | wie T2I |
| Datei außerhalb Roots / zu groß / falscher Typ | 400 |
| Comfy &lt; 0.37.0 oder Node fehlt | 500 klare Meldung |
| Gewichtdatei fehlt | 500 |
| Timeout | Job abbrechen, Comfy stoppen, Cleanup |
| Output 0 Byte / kein PNG-Header | Fehler, keine Archiv-Lüge |

---

## 9. Testkatalog (spätere Implementierung)

| ID | Fall | Pass |
|----|------|------|
| T-FLUX | bestehendes 512 Seed 42 T2I | Manifest+PNG, runtime grob wie A12, Comfy inactive danach |
| T-EDIT-1 | ein Foto, „Hintergrund Sonnenuntergang“ | PNG, Manifest, proceed_once |
| T-OBJ | klar begrenztes Objekt ändern | visuell + Hash ≠ Input |
| T-BG | nur Hintergrund | — |
| T-PRESERVE | unbeteiligte Flächen erkennbar erhalten | manuell / Stichprobe |
| T-MULTI | 1 Quelle + 1 Ref | Prompt mit `<image1>` `<image2>` |
| T-RGBA | `preserve_alpha=true` | PNG mit Alpha-Kanal |
| T-PATH | Pfad außerhalb Roots | ToolError, kein Comfy-Start nötig |
| T-SIZE | Datei &gt; 25 MiB | Ablehnung |
| T-ARCH | Archiv umount (Testumgebung) | Abbruch ohne `/srv` Write |
| T-GPU-OK | Cleanup nach Erfolg | Comfy inactive, VRAM niedrig |
| T-GPU-ERR | Cleanup nach Timeout | ebenso |
| T-SEARCH | ToolSearch `edit_image` | voller MCP-Name |
| T-PERM | Vote nur proceed_once | kein YOLO |
| T-MAN | SHA Input/Output/Workflow/Modelle | vorhanden |
| T-RB | Comfy 0.37 → 0.33 Rollback | FLUX-T2I wieder PASS |

Messbar (v1-Ziele, nach erstem Smoke justieren):

- Edit 1024²: Ziel &lt; 180 s nach warmem Load; hartes Fail &gt; 420 s.
- VRAM-Peak: Fail wenn Ollama während Edit geladen bleibt.
- RAM: kein Host-OOM.
- Qualität: kein offizielles Score; Smoke „Auftrag ändert das Genannte, Rest erkennbar“.

---

## 10. Stufenplan (nächste Chats)

Jede Stufe: Stop bei FAIL. Kein Git-Push. Keine Alias-Änderung. Kein YOLO.

### Stufe 1 — Backup und isoliertes ComfyUI 0.37.0 — **PASS 21.09.2026**

- Backup `/mnt/ai-archive/backups/comfyui-0.33.0-20260921-140000/`.
- Tree `/srv/ai/apps/ComfyUI-0.37.0` Tag `v0.37.0` Commit `73c9bad`. Testport 8189.
- 0.33-Venv unzureichend (`comfy_aimdo.storage`). Eigenes Venv, Torch 2.13.0+cu130 behalten.

### Stufe 2 — FLUX-Regression auf 0.37 — **PASS 21.09.2026**

- Isoliert 35,0 s; Workplace 61,7 s; MCP 22,6 s. Nodes inkl. Qwen-2.1 vorhanden. Cutover live, Autostart disabled.
- Bericht: `docs/COMFYUI_0_37_UPGRADE.md`.

### Stufe 3 — Kontrollierter Download — **PASS 21.09.2026 14:22**

Nur die drei Dateien von Kandidat 1. SHA gegen HF. Kein bf16-Encoder, kein PE.

### Stufe 4 — Offizieller Workflow-Smoke (isoliert) — **PASS 21.09.2026 14:28**

Template Edit, Encoder w4a8, Cache cpu/int8, 512 dann 1024. Bericht: `docs/QWEN_IMAGE_2_1_SMOKE.md`.

### Stufe 5 — Image-Editing-Test (noch ohne MCP)

- Workplace-Endpoint intern oder Script. Manifest prüfen.
- **Stop:** Archiv schreibt nach `/`.

### Stufe 6 — KI-Arbeitsplatz-UI

- Edit-Ansicht. T2I unverändert.
- **Stop:** T2I-Regression.

### Stufe 7 — MCP `edit_image`

- includeTools/visible. Isolates für Kurzname.
- **Stop:** YOLO/trust-Änderung, Tool ohne Permission.

### Stufe 8 — Tests + Rollback-Drill

- Katalog oben. Einmal 0.37→0.33 FLUX.
- **Stop:** Cleanup lässt Comfy an.

### Stufe 9 — Doku + Handoff

- CHANGELOG, HANDOFF, ACCEPTANCE-Nachtrag. Kein Push.

---

## 11. Status nach isoliertem Edit-Smoke (21.09.2026 14:28)

- ComfyUI **0.37.0** produktiv. 0.33.0-Tree/Venv behalten.
- Drei Qwen-Image-2.1-Gewichte auf der SSD, Hashes offiziell. Lizenz Research, nur privater Test.
- Isolierter Edit 512 und 1024 PASS. FLUX-T2I und MCP `generate_image` PASS.
- Kein `edit_image`, keine Editing-UI, kein produktiver Edit-Workflow.
- Ollama 0.34.2 / Qwen 0.24.2 unangetastet.
- `local-fast` / `local-quality` unangetastet.

Nächster Prompt nur: Stufe 8 ohne Backend-Änderung (sichtbare Editing-UI auf `/api/images/edit`).

## 12. Status nach Edit-Backend + MCP (21.09.2026 14:56)

- Frozen Workflow `qwen-image-21-edit-v1` SHA `78a0d0f445b08557d5e69139ce7f2d2ad547658bcaf90a10cfe154121b65bbe8`.
- Workplace `POST /api/images/edit` live. MCP `edit_image` auf `local-tools` **1.3.0** (13 Tools).
- Live EDIT-1024 81,9 s Peak 15250 MiB; MCP 43,5 s Peak 15525 MiB. FLUX-Hashes unverändert.
- Keine Editing-UI. `trust: false`. Kein YOLO. Kein Git-Push.

## 13. Status nach sichtbarer Editing-UI (21.09.2026 15:17)

- Subnav Erzeugen / Bearbeiten / Experte. Staging-Upload + Archiv-GET. Kein MCP-Change.
- Live UI-Edit `37fa72860c19` 78,681 s Peak 15598 MiB. FLUX `e8e02a01005d` Hashes unverändert.
- Unit 50 OK. `trust: false`. Kein YOLO. Kein Git-Push.
- Nächste Phase nur: Open-WebUI als MCP-Client für die bestehenden Bild-Tools.
