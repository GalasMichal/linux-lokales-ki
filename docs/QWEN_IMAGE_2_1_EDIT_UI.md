# Qwen-Image-2.1 — sichtbare Bearbeiten-UI

Stand: 21.09.2026 15:17. **PASS.** Kein Git-Push. Kein YOLO. `trust: false`. `approvalMode: default`. Default bleibt `local-fast`.

SoT: [`docs/CHATGPT_HANDOFF.md`](CHATGPT_HANDOFF.md). Backend: [`docs/QWEN_IMAGE_2_1_EDIT.md`](QWEN_IMAGE_2_1_EDIT.md). Belege: `benchmarks/qwen-image-21-edit-ui-20260921/`.

Diese Phase ändert **nicht** MCP, Gateway, Frozen-Workflow oder Modell-Aliase. Sie hängt die vorhandene Bilder-Ansicht an `POST /api/images/edit`.

---

## UI-Struktur

Bilder-Subnav (bestehender Stil):

1. **Erzeugen** — unverändertes FLUX-Formular `flux2-klein-t2i-v1`
2. **Bearbeiten** — neues Formular auf `/api/images/edit`
3. **Workflow (Experte)** — ComfyUI-iframe `127.0.0.1:8188`

Bearbeiten-Felder: Ausgangsbild (Datei, Pflicht), Anweisung (Textarea, max. 4000), bis zu zwei Referenzbilder, Größe 512/768/1024, Seed Default 42, Checkbox `Transparenz erhalten` (`preserve_alpha`, Default aus), Button `Bild bearbeiten`.

Kein `workflow_id`, kein Graph, kein Modellname, keine URL, kein Base64-Feld, kein frei eintippbarer Serverpfad.

---

## Lokale Dateiauswahl

Der Browser kennt keine Host-Pfade. Kleinster sicherer Weg:

1. Datei-Dialog (PNG/JPG/JPEG/WebP, max. 25 MiB, Client-Prüfung vor jedem Request).
2. `POST /api/images/stage` (multipart, nur Bild). Server schreibt `ui_stage_{uuid}.ext` unter `/srv/ai/workspaces/ki-workplace-stage`.
3. UI sendet nur diesen Serverpfad an `POST /api/images/edit`.
4. Nach Erfolg und Fehler löscht der Edit-Handler Stage-Dateien mit Prefix `ui_stage_` in diesem Ordner. Zusätzlich 2-Stunden-Sweep.

`client_max_size` der Workplace-App: 28 MiB (nur damit 25-MiB-Uploads durchkommen). Ergebnisanzeige: `GET /api/images/jobs/{job_id}/output` aus dem Archiv, weil Edit-Cleanup ComfyUI vor der HTTP-Antwort stoppt. Generate nutzt weiter Comfy `/view` (unverändert, Comfy bleibt dort bis Fenster-Cleanup).

---

## Live-UI-Edit

| Feld | Wert |
|------|------|
| Job | `37fa72860c19` |
| Anweisung | `Change only the apple from red to bright green. Keep everything else unchanged.` |
| Größe | 1024 × 1024, Seed 42 |
| Laufzeit | **78,681 s** |
| Peak-VRAM | **15598 MiB** |
| Output | `/mnt/ai-archive/images/inbox/2026-09-21/37fa72860c19/ki_arbeitsplatz_37fa72860c19_00001_.png` (1024×1024 RGBA PNG, 1 510 181 B) |
| Manifest | `.../37fa72860c19/manifest.json` |
| Workflow | `qwen-image-21-edit-v1` SHA `78a0d0f445b08557d5e69139ce7f2d2ad547658bcaf90a10cfe154121b65bbe8` |

In der UI sichtbar: grüner Apfel, Job-ID, Laufzeit, Archivpfad.

---

## Tests

Unit: `tests/test_ki_workplace.py` + `tests/test_local_tools_gateway.py` — **50 OK**. MCP unverändert 1.3.0 / 13 Tools.

| Fall | Ergebnis |
|------|----------|
| UI-EDIT-EMPTY | keine Anfrage, „Bitte zuerst ein Ausgangsbild wählen.“ |
| UI-EDIT-INSTRUCTION | keine Anfrage, „Bitte eine Bearbeitungsanweisung eingeben.“ |
| UI-EDIT-TYPE | `.txt` abgelehnt vor Request |
| UI-EDIT-1 | Live-Job `37fa72860c19` PASS |
| UI-EDIT-MULTI | Request mit genau 1 `reference_paths`-Eintrag |
| UI-EDIT-2REF | Request mit genau 2 Pfaden |
| UI-EDIT-3REF | nur zwei Datei-Felder, kein `multiple` |
| UI-EDIT-ALPHA | `preserve_alpha: true` |
| UI-EDIT-SIZE | 512 / 768 / 1024 im JSON |
| UI-ERROR | 500 sichtbar, Button wieder aktiv |
| UI-T2I-REGRESSION | Job `e8e02a01005d`, 59,425 s, Workflow-SHA und Modell-Hashes = `bf5df1a30c27` |
| Nav | Agent, System, Experte erreichbar |

---

## Rollback

Sicherung: `/mnt/ai-archive/backups/qwen-image-21-edit-ui-20260921-150824`

```bash
BACKUP=/mnt/ai-archive/backups/qwen-image-21-edit-ui-20260921-150824
cp -a "$BACKUP/." /srv/ai/apps/ki-workplace/
systemctl --user restart ki-workplace.service
```

MCP nicht zurückrollen — diese Phase hat local-tools nicht geändert.

---

## Einschränkungen

- Peak-VRAM ~15,6 GiB auf 16 GB — eng, kein OOM.
- Die UI wartet die GPU-Cleanup-Phase mit ab, bevor „Fertig“ erscheint (aiohttp sendet erst nach `finally`).
- Generate räumt ComfyUI nicht selbst auf (bestehend). Edit tut das.
- Qwen-Research-Lizenz, nur privater lokaler Test.
- Kein allgemeiner Dateibrowser, keine URL, kein Base64 als API.
