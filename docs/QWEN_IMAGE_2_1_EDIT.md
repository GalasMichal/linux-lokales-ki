# Qwen-Image-2.1 Edit — produktiver Pfad

Stand: 21.09.2026 15:17. Backend + MCP **PASS** (14:56). Sichtbare UI **PASS** — [`docs/QWEN_IMAGE_2_1_EDIT_UI.md`](QWEN_IMAGE_2_1_EDIT_UI.md). Kein Git-Push. Kein YOLO. `trust: false`. `approvalMode: default`. Default bleibt `local-fast`.

SoT: [`docs/CHATGPT_HANDOFF.md`](CHATGPT_HANDOFF.md). Smoke-Vorstufe: [`docs/QWEN_IMAGE_2_1_SMOKE.md`](QWEN_IMAGE_2_1_SMOKE.md). Belege: `benchmarks/qwen-image-21-edit-20260921/` (Backend) und `benchmarks/qwen-image-21-edit-ui-20260921/` (UI).

Lizenz: **Qwen Research License**. Privater lokaler Test, nicht kommerziell freigegeben.

---

## Architektur

```text
UI Bearbeiten
  → POST /api/images/stage (nur Bild, Server wählt den Namen)
  → POST /api/images/edit
  → frozen workflow qwen-image-21-edit-v1
  → ComfyUI 0.37.0
  → Archiv /mnt/ai-archive/images/inbox/YYYY-MM-DD/JOB-ID/

MCP edit_image
  → local-tools gateway (kein eigener Comfy-Client)
  → KI-Arbeitsplatz POST /api/images/edit
  → derselbe frozen Workflow
```

FLUX-T2I (`generate_image` / `flux2-klein-t2i-v1`) bleibt unverändert. Es gibt keinen zweiten Comfy-Client im MCP und keine Graph-Übergabe vom Agenten.

---

## Frozen Workflow

ID: `qwen-image-21-edit-v1`  
Datei: `apps/ki-workplace/workflows/qwen-image-21-edit-v1.json`  
SHA-256 (canonical JSON): `78a0d0f445b08557d5e69139ce7f2d2ad547658bcaf90a10cfe154121b65bbe8`

| Feld | Wert |
|------|------|
| DiT | `qwen_image_2.1_int8_convrot.safetensors` (`int8`) |
| Encoder | `qwen3vl_8b_w4a8.safetensors` (`w4a8`, type `qwen_image`) |
| VAE | `qwen_image_2.1_vae_bf16.safetensors` |
| Cache | `QwenImage21Cache` device `cpu`, dtype `int8` |
| Sampler | Euler / simple, 25 Schritte, CFG 1 |
| Auflösung | Default und Maximum 1024 |
| Seed | nur Backend |

Kein Prompt-Enhancer, keine PE-Gewichte, keine bf16-Encoder-Variante.

---

## Endpoint

`POST http://127.0.0.1:8790/api/images/edit`

| Feld | Pflicht | Grenzen |
|------|---------|---------|
| `instruction` | ja | ≤ 4000 Zeichen |
| `input_path` | ja | lokaler Pfad, png/jpg/jpeg/webp |
| `reference_paths` | nein | max. 2 zusätzliche Bilder |
| `width` / `height` | nein | 512, 768 oder 1024 |
| `seed` | nein | Default 42 |
| `preserve_alpha` | nein | Default false |

Kein `workflow_id`, kein Graph. Timeout 420 s.

`preserve_alpha=true` setzt den offiziellen RGBA-Präfix vor die User-Anweisung, ersetzt sie aber nicht.

---

## Pfade und Limits

Erlaubte Roots: `/home/mike/Projects`, `/srv/ai/workspaces`, `/mnt/ai-archive`, `/tmp`, `/var/tmp`.  
Max. 25 MiB und 4096 px Kante. Keine URL, kein Base64. Originale werden nur kopiert; Staging-Namen `ki_edit_{job}_{n}`. Kopien werden nach Erfolg **und** Fehler gelöscht.

Die Units haben `PrivateTmp=true`. Host-`/tmp` ist für Workplace/MCP unsichtbar. Praktisch: Projects, Workspaces oder Archiv verwenden.

---

## GPU-Lifecycle (nur Edit)

Vor dem Job: Qwen Serve stoppen, Ollama vollständig entladen, ComfyUI ≥ 0.37.0 starten, Nodes und die drei Gewichte prüfen, VRAM frei ≥ 2 GiB. Archiv muss gemountet sein; sonst Abbruch, kein Schreiben auf `/`.

Nach Erfolg und Fehler: Staging weg, ComfyUI inactive, Ollama leer, Qwen Serve inactive.

`generate_image` nutzt weiter `ensure_image_mode` **ohne** Qwen-Stopp (unverändert).

---

## MCP `edit_image`

Version `local-tools` **1.3.0** (vorher 1.2.0 / 12 Tools, jetzt 13).  
Kurzname `edit_image`, voller Name `mcp__local-tools__edit_image`.  
`includeTools` + Projekt-`tools.visible`. Timeout-Fragment 720000 ms.  
`trust: false`, `approvalMode: default`, nur `proceed_once`. Kein YOLO.

Gateway: nur `POST /api/images/edit`. Kein Cleanup-Duplikat im MCP (Workplace räumt selbst auf).

---

## Tests

Unit: `tests/test_ki_workplace.py`, `tests/test_local_tools_gateway.py` — PATH, SIZE, TYPE, ARCHIVE-Mock, MULTI-Graph, FLUX-Hash, Cleanup-on-error. **61 OK.**

Live 21.09.2026 14:50–14:55:

| Fall | Ergebnis |
|------|----------|
| PATH `/etc/hostname` | HTTP 400, ComfyUI blieb inactive |
| TYPE `.txt` | HTTP 400 |
| SIZE >25 MiB | HTTP 400 |
| EDIT-1024 `cd3220e9efaa` | 81,947 s, Peak 15250 MiB, gültiges PNG, Hash ≠ Input |
| MULTI `faacb571fbd1` | 43,485 s, Peak 15500 MiB, eine Referenz |
| MCP `93d02c1bffad` | 43,469 s, Peak 15525 MiB |
| FLUX `bf5df1a30c27` | 0,854 s (Comfy-Cache), Workflow-SHA und Modell-Hashes unverändert |
| CLEANUP SUCCESS | Comfy/Qwen inactive, Ollama leer, Staging leer, VRAM ~2,2 GiB |
| CLEANUP ERROR | Unit-HTTP: `cleanup_gpu` nach simuliertem Fehler |

UI 21.09.2026 15:08–15:17 (historische Backend-Zeilen oben **nicht** überschrieben):

| Fall | Ergebnis |
|------|----------|
| UI-EDIT-1 `37fa72860c19` | 78,681 s, Peak 15598 MiB, 1024×1024 PNG in der Bilder-Ansicht |
| UI-T2I `e8e02a01005d` | 59,425 s, Workflow-SHA und Modell-Hashes unverändert |
| Unit | 50 OK (`test_ki_workplace` + `test_local_tools_gateway`) |

---

## Rollback

Sicherung: `/mnt/ai-archive/backups/qwen-image-21-edit-20260921-144943`

```bash
BACKUP=/mnt/ai-archive/backups/qwen-image-21-edit-20260921-144943
cp -a "$BACKUP/ki-workplace/." /srv/ai/apps/ki-workplace/
cp -a "$BACKUP/local-tools/." /srv/ai/apps/local-tools/
python3 "/home/mike/Projects/Linux Lokales KI/scripts/configure-qwen-mcp.py" \
  --restore-mcp /home/mike/.qwen/settings.json "$BACKUP/config/qwen-settings.json"
systemctl --user restart ki-workplace.service local-tools-mcp.service
```

---

## Bekannte Einschränkungen

- Peak-VRAM ~15,5 GiB auf 16 GB — eng, kein OOM in den Live-Läufen.
- Sichtbare Editing-UI: [`docs/QWEN_IMAGE_2_1_EDIT_UI.md`](QWEN_IMAGE_2_1_EDIT_UI.md) (PASS 15:17).
- Qwen-Research-Lizenz, nur privater lokaler Test.
- Keyword `image` in ToolSearch listet `edit_image` vor `generate_image`.
- Erstes Edit hasht ~14 GB Gewichte (danach LRU-Cache).
- Die UI wartet GPU-Cleanup in `finally` mit ab, bevor „Fertig“ erscheint.
