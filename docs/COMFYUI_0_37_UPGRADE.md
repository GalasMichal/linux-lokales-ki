# ComfyUI 0.33.0 → 0.37.0

Stand: 21.09.2026 14:28. Produktiv **PASS**. Qwen-Image-2.1-Gewichte liegen, isolierter Edit-Smoke **PASS**. Kein Git-Push. Kein `edit_image`.

SoT: [`docs/CHATGPT_HANDOFF.md`](CHATGPT_HANDOFF.md). Analyse: [`docs/QWEN_IMAGE_2_1_ANALYSIS.md`](QWEN_IMAGE_2_1_ANALYSIS.md). Smoke: [`docs/QWEN_IMAGE_2_1_SMOKE.md`](QWEN_IMAGE_2_1_SMOKE.md).

---

## Zielversion

GitHub [`Comfy-Org/ComfyUI` releases](https://github.com/Comfy-Org/ComfyUI/releases): **v0.37.0** ist `latest`, `prerelease=false`, published 2026-09-21T07:35:01Z. Kein neuerer Stable-Patch (kein 0.37.1). Kein RC.

Commit: `73c9bad4d21e7addbe1d13bc92eee0f1431b017d`.  
Release enthält PR [#16400](https://github.com/Comfy-Org/ComfyUI/pull/16400) (Qwen-Image-2.1-Nodes).

---

## Vorher / Nachher

| Größe | Vorher | Nachher |
|-------|--------|---------|
| Live-Tree | `/srv/ai/apps/ComfyUI` 0.33.0 `cc0fc21` | `/srv/ai/apps/ComfyUI-0.37.0` 0.37.0 `73c9bad` |
| Keep 0.33 | — | Tree **behalten**, Venv `/srv/ai/venvs/comfyui` **behalten** |
| Venv | `/srv/ai/venvs/comfyui` Py 3.13.15 torch **2.13.0+cu130** | `/srv/ai/venvs/comfyui-0.37` gleiches Torch |
| Port | 8188, disabled | 8188, **disabled**, Bind `127.0.0.1` |
| Output | Tree-output | `--output-directory /srv/ai/apps/ComfyUI/output` (Workplace unverändert) |
| FLUX-T2I | `flux2-klein-t2i-v1` SHA `d9d752d5…` | unverändert |
| Modelle | 3 FLUX-Dateien | Hashes unverändert, **kein** 2.1-Gewicht |
| Ollama / Qwen | 0.34.2 / 0.24.2 | unverändert |

Backup: `/mnt/ai-archive/backups/comfyui-0.33.0-20260921-140000/`  
(Tree-Kopie, Unit, freeze, Workflow, `server.py`, Modell-Hashes. **Kein** 6 GiB-Venv-Duplikat auf die HDD — Original bleibt unter `/srv/ai/venvs/comfyui`.)

---

## Apply / Rollback

```bash
# Isolierter Tree (noch nicht live)
./scripts/install-comfyui-0.37.0-isolated.sh
./scripts/prepare-comfyui-0.37-venv.sh   # nur wenn 0.33-Venv nicht startet
./scripts/start-comfyui-0.37-isolated.sh  # :8189
python3 benchmarks/comfyui_037_isolated_flux.py
./scripts/stop-comfyui-0.37-isolated.sh

# Cutover (braucht Marker .isolated-flux-pass.json)
./scripts/apply-comfyui-0.37.0.sh

# Zurück auf 0.33.0 (Unit only; Trees bleiben)
./scripts/rollback-comfyui-0.33.0.sh /mnt/ai-archive/backups/comfyui-0.33.0-20260921-140000
```

Apply bleibt **idempotent-gefährlich**, wenn der Isolations-Marker liegt — Unittest skippt den Apply-Aufruf dann bewusst.

---

## Venv-Entscheidung

0.33-Venv startet 0.37.0 **nicht**: `ModuleNotFoundError: comfy_aimdo.storage` (aimdo 0.4.13 vs 0.5.5).

Separates Venv: Kopie + nur diese Bumps, Torch **nicht** ersetzt:

| Paket | 0.33 | 0.37 |
|-------|------|------|
| comfyui-frontend-package | 1.49.6 | 1.52.7 (Tag-`requirements.txt`; Release-Notes erwähnen zusätzlich 1.53.6) |
| comfyui-workflow-templates | 0.11.43 | 0.11.66 |
| comfyui-embedded-docs | 0.5.10 | 0.5.12 |
| comfy-kitchen | 0.2.31 | 0.2.35 |
| comfy-aimdo | 0.4.13 | 0.5.5 |
| av | 18.1.0 | unverändert (≥17 erfüllt) |
| torch | 2.13.0+cu130 | **unverändert** |

Zwischenfall: `cp -a` ließ `pip`-Shebang auf `/srv/ai/venvs/comfyui` zeigen; ein `pip install` landete kurz im 0.33-Venv. Sofort zurückgesetzt. Freeze danach **identisch** zum Backup. Skript schreibt Shebangs jetzt um und nutzt `python -m pip`.

---

## Isolierter Test :8189

Nodes: FLUX (`UNETLoader`, `CLIPLoader`, `VAELoader`, `EmptyFlux2LatentImage`, Euler/`Flux2Scheduler`, …) **und** `TextEncodeQwenImage21`, `QwenImage21Cache`.  
FLUX-Gewichte erkannt. Keine 2.1-Gewichte. Bind nur localhost. Keine neuen Custom Nodes.

A12-Prompt, 512×512, Seed 42:

| | Isoliert 0.37 | A12 (0.33 + Workplace) |
|--|---------------|------------------------|
| Laufzeit | **35,0 s** | 64,9 s inkl. Mode/Hashes |
| PNG | 512×512 RGB gültig | gültig |
| VRAM-Peak used | 14310 MiB | historisch ~14701 MiB Peak |
| Workflow-SHA | `d9d752d5…` | gleich |

Keine Verschlechterung. Marker: `/srv/ai/apps/ComfyUI-0.37.0/.isolated-flux-pass.json`.

---

## Produktiv

| Test | Ergebnis |
|------|----------|
| Workplace T2I 512 Seed 42 | Job `5dd9fb157e52`, **61,658 s**, Archiv + Manifest |
| MCP `generate_image` | Job `68ae328f6c49`, **22,572 s** (warm), Cleanup ok |
| Bind | `127.0.0.1:8188`, Version 0.37.0, Torch 2.13.0+cu130 |
| GPU-Cleanup | Comfy inactive, VRAM ~1846 MiB |
| Agent-Modus | Qwen `:4170` health ok, Comfy bleibt aus |
| Ollama | 0.34.2, `local-fast` generate `OK` |
| `/health` | 1.2.0, 12 Tools inkl. Memory/PDF/`generate_image` |
| `live_mcp_smoke` | PASS |
| unittest | `test_comfyui_037_upgrade` + Workplace/Gateway/Memory/PDF **44 OK** (1 skip) |
| `trust` / `approvalMode` / YOLO | false / default / nicht gesetzt |
| Autostart | **disabled** |

Modell-Hashes unverändert (A12). Workflow-SHA unverändert. Output weiterhin `/srv/ai/apps/ComfyUI/output/...`.

Nachtrag 21.09.2026 14:28: drei 2.1-Dateien unter `/srv/ai/models/comfyui`. Isolierter Edit-Smoke PASS. FLUX-Regression danach: Workplace Job `9fbab1ed7eaa` 42,31 s, MCP Job `7fb6b408ab1b`, Hashes identisch.

---

## Einschränkungen

- 0.33-Tree hat nach `git fetch` zusätzliche Tags (v0.34–v0.37); **HEAD bleibt `cc0fc21`**.
- Frontend laut Release-Notes 1.53.6, im Tag-`requirements.txt` **1.52.7** — installiert ist 1.52.7.
- PR #16374 (Text-Encoder bei dynamic VRAM auf GPU) ist für Image-2.1 ein VRAM-Risiko; der isolierte Smoke mit Cache `cpu`/`int8` blieb unter 16 GB (Peak 15618 MiB).
- Kein `edit_image`, keine UI-Editing-Ansicht. 2.1-Gewichte liegen nach dem Smoke.

Nächste Phase: frozen Edit-Workflow + Workplace-Backend + MCP `edit_image`. Noch keine sichtbare UI.
