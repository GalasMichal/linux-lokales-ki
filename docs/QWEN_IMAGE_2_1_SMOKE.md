# Qwen-Image-2.1 — Isolierter Edit-Smoke

Stand: 21.09.2026 14:28. **PASS.** Kein Git-Push. Kein YOLO. `trust: false`. `approvalMode: default`. Default bleibt `local-fast`.

SoT: [`docs/CHATGPT_HANDOFF.md`](CHATGPT_HANDOFF.md). Analyse: [`docs/QWEN_IMAGE_2_1_ANALYSIS.md`](QWEN_IMAGE_2_1_ANALYSIS.md). Belege: `benchmarks/qwen-image-21-smoke-20260921/`.

Lizenz: **Qwen Research License**. Dieser Lauf ist ein privater lokaler Test/Evaluation auf diesem Rechner. **Keine kommerzielle Nutzung als freigegeben.**

Nicht gebaut in **dieser Smoke-Phase**: KI-Arbeitsplatz-Editing-UI, MCP-Tool `edit_image`, produktive Editing-API. Diese Teile sind seit 21.09.2026 14:56 in [`docs/QWEN_IMAGE_2_1_EDIT.md`](QWEN_IMAGE_2_1_EDIT.md) **PASS** (weiterhin keine Editing-UI).

---

## Verdict

| Kriterium | Ergebnis |
|-----------|----------|
| Exakt drei erlaubte Dateien | PASS |
| Offizielle SHA-256 | PASS, alle drei |
| Safetensors-Header | PASS |
| Kein bf16-Encoder / kein PE | PASS |
| Stufe A Graph + Nodes | PASS |
| 512-Edit technisch + sichtbar | PASS, Apfel rot → grün |
| 1024-Edit | PASS, kein OOM |
| Ressourcen vollständig | PASS |
| Cleanup :8189 / VRAM | PASS, ~2,1 GiB |
| FLUX-T2I Workplace | PASS, Job `9fbab1ed7eaa`, 42,31 s |
| MCP `generate_image` | PASS, Job `7fb6b408ab1b` |
| FLUX Workflow-/Modell-Hashes | unverändert |
| Security / systemd | unverändert |

---

## Offizielle Quelle

| | |
|--|--|
| Repo | [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1) |
| Revision | `ace0edeb3791a594ddfa36ed5f41a178a394e921` |
| Lizenz | `qwen-research` — [LICENSE](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE) |
| Host | ComfyUI **0.37.0** `73c9bad`, Venv `/srv/ai/venvs/comfyui-0.37`, Torch **2.13.0+cu130** |
| Template | `image_qwen_image_2_1_image_edit.json` (comfyui-workflow-templates **0.11.66**) |

Download: `scripts/download-qwen-image-21.sh` sequentiell, `.part`, `curl -C -`, atomar `os.replace` nach Größe+SHA+Safetensors. Keine parallelen Downloads. Keine Secrets.

Vorher frei auf `/srv/ai`: **133 G** (Preflight 14:13). Nachher: **120,33 G**. Archiv: **309 G**. Reserve ≥25 G gehalten.

---

## Heruntergeladene Dateien

| Datei | Ziel | Bytes | SHA-256 |
|-------|------|------:|---------|
| `qwen_image_2.1_int8_convrot.safetensors` | `/srv/ai/models/comfyui/diffusion_models/` | 7256783064 | `cb74113cb03faecd79611b01fd7fd642f0aa60d6f0b95086abee214d75eaa57d` |
| `qwen3vl_8b_w4a8.safetensors` | `/srv/ai/models/comfyui/text_encoders/` | 6312105364 | `7754425e55e7bea2bfde4dde59a4cc236cb44e5ee9c215ea66ef8d47012824eb` |
| `qwen_image_2.1_vae_bf16.safetensors` | `/srv/ai/models/comfyui/vae/` | 675509688 | `bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9` |

Summe **14,25 GB**. Belegter SSD-Zuwachs grob **13 G** (`/` 791 G → 798 G während des DiT). Keine `.part`-Reste. Keine gleichnamigen Altdateien zum Überschreiben. Manifest: `benchmarks/qwen-image-21-smoke-20260921/download/download-manifest.json`.

Nicht gezogen: bf16-DiT, bf16-Encoder, int8-Encoder, PE-9,47-GB, Diffusers, LoRAs, Community-Reuploads.

---

## Testgraph vs. offizielle Vorlage

Vorlage kopiert nach `benchmarks/qwen-image-21-smoke-20260921/official-image_qwen_image_2_1_image_edit.json`. Keine produktive Datei unter `apps/ki-workplace/workflows/`.

API-Graphen: `api-workflow-512.json` / `api-workflow-1024.json`. Isolierter Server `127.0.0.1:8189`, systemd-Unit unangetastet.

Nachgewiesene Abweichungen (nötig für 16 GB und API):

1. Encoder `qwen3vl_8b_int8_convrot` → **`qwen3vl_8b_w4a8`**. CLIP-Typ bleibt `qwen_image`.
2. `QwenImage21Cache.device` `auto` → **`cpu`**.
3. `QwenImage21Cache.dtype` `default` → **`int8`**.
4. Subgraph abgeflacht. `ComfySwitchNode` weggelassen: offizieller Default `switch=false` nutzt das Encoder-Latent.
5. `SaveImageAdvanced` → `SaveImage` (fester Prefix).
6. Ein `LoadImage` statt zwei Template-Assets.
7. `TextEncodeQwenImage21.resolution` explizit 512 bzw. 1024. Offizielles Subgraph-Widget ist `0` (Quellgröße behalten); die 1024-WxH-Felder greifen nur bei `switch=true`.

Sampler wie Vorlage: 25 Schritte, CFG 1, Euler, Scheduler `simple`, Seed 42. Log bestätigt die drei erlaubten Pfade; `qwen3vl_8b_bf16` war nicht sichtbar.

---

## Eingabe und Anweisung

Kopie des A12-FLUX-Apfels, Original unverändert:

- Quelle: `/mnt/ai-archive/images/inbox/2026-09-21/b8d57bc6dd22/ki_arbeitsplatz_b8d57bc6dd22_00001_.png`
- Kopie: `benchmarks/qwen-image-21-smoke-20260921/input/source.png`
- PNG 512×512 RGB, 190999 Bytes, SHA `af0c3a65165f198ed9c287ee67b5966dd1a2deab3827b30bba8b3b50d5a40096`

Anweisung: *Change only the apple in \<image1\> from red to bright green. Keep the white table, lighting, composition and everything else unchanged.*

---

## Messwerte

GPU vorher: Qwen Serve gestoppt, Ollama leer, produktives Comfy inactive, kein zweiter Comfy-Prozess. Isoliert `:8189` Bind `127.0.0.1`, Version 0.37.0. NORMAL_VRAM. Kitchen nativ `w4a8_int8_linear` + `dequantize_int8_convrot_weight`.

| | 512 kalt | 1024 warm |
|--|----------:|----------:|
| Comfy „Prompt executed“ | **37,86 s** | **15,22 s** |
| Harness | 38,511 s | 15,624 s |
| Sampling | ~2 s nach 16 s Init | ~11 s, ~2,23 it/s |
| Output | 512×512 RGBA PNG | 1024×1024 RGBA PNG |
| Bytes / SHA | 275069 / `3abd7a80…` | 1092725 / `7f60f0ee…` |
| VRAM idle → peak → end | 2357 → **15509** → 15023 MiB | 14998 → **15618** → 13429 MiB |
| GPU-Util peak | 98 % | 100 % |
| RAM used peak | 22,91 Gi | 24,31 Gi |
| Swap used peak | 7,46 Gi (von 3,7) | 7,55 Gi |
| CPU peak | 19,6 % | 13,8 % |
| OOM / Offload-Schleife | nein | nein |

Alpha 253–255 (praktisch opak, RGBA-VAE). Kein schwarzes Bild, kein leerer Rand, nicht abgeschnitten. 768 nicht nötig. `--lowvram` nicht nötig. Produktlimit auf dieser Box: **1024 ist stabil**, VRAM aber eng (~15,6 GiB von 16).

`first_progress` im Harness ist die Queue-Aufnahme (~0,03 s), nicht der erste Sampler-Schritt. Maßgeblich sind die Comfy-Logzeiten.

Nach Stop `:8189`: VRAM **2095 MiB**, Port tot, Input-Kopie entfernt. Gewichte behalten.

---

## Bildqualität

Sichtprüfung (technisch maßgeblich):

- 512 und 1024: Apfel eindeutig **grün**, Dampf, weißer Tisch, Komposition erhalten.
- Keine schweren Artefakte, keine falsche Auflösung.
- Tischkanten leicht grauer als das FLUX-Original — lokale Farbverschiebung, keine neue Szene.

Optionale **Modellmeinung** `local-quality` (nach Comfy-Stop, 59,6 s, danach Unload). Ersetzt **nicht** die Bildprüfung:

`apple_now_green=true`, `table_and_steam_preserved=true`, `severe_artifacts=false`.

---

## FLUX-Regression

Produktives Comfy über KI-Arbeitsplatz, Workflow **unverändert** `flux2-klein-t2i-v1`.

| | Workplace | MCP `generate_image` |
|--|-----------|----------------------|
| Job | `9fbab1ed7eaa` | `7fb6b408ab1b` |
| Runtime | **42,31 s** | **0,785 s** (warm, gleicher Prompt/Seed direkt danach; Comfy-Cache) |
| PNG | gültiger roter Apfel 512 | gültiger roter Apfel 512 |
| Workflow-SHA | `d9d752d52b1430bd3756908885146daea41279e29a7b6e3a9e05705572f39953` | gleich |
| DiT / Encoder / VAE SHA | `97ed34fe…` / `6c671498…` / `868fe7b3…` | gleich |
| GPU-Cleanup | Comfy danach vom MCP gestoppt | VRAM **2116 MiB** |

`live_mcp_smoke` PASS (12 Tools, **kein** `edit_image`). `/health` 1.2.0. Agent-Modus wieder `:4170`. ComfyUI-Unit **disabled/inactive**. `model.name=local-fast`. `trust: false`. `approvalMode: default`.

---

## Git

HEAD bleibt `abd0282`. **Kein Push.** Diese Phase fügt Benchmarks, Download-Skript, Smoke-Runner und Doku hinzu. Keine Änderung an `generate_image`, systemd-Units, FLUX-Workflow oder Security-Flags.

Nächste Phase ausschließlich: **sichtbare KI-Arbeitsplatz-Editing-UI** auf dem geprüften `/api/images/edit`. Der produktive Edit-Pfad ist seit 14:56 dokumentiert in [`docs/QWEN_IMAGE_2_1_EDIT.md`](QWEN_IMAGE_2_1_EDIT.md).
