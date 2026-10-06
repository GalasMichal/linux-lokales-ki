# Open WebUI — lokale Bild-Tools

Stand: 21.09.2026 19:20. **PASS.** Kein Git-Push. Kein YOLO. `trust: false`. `approvalMode: default`. Default bleibt `local-fast`.

SoT: [`docs/CHATGPT_HANDOFF.md`](CHATGPT_HANDOFF.md). Backend unverändert: [`docs/QWEN_IMAGE_2_1_EDIT.md`](QWEN_IMAGE_2_1_EDIT.md), UI: [`docs/QWEN_IMAGE_2_1_EDIT_UI.md`](QWEN_IMAGE_2_1_EDIT_UI.md). Belege: `benchmarks/open-webui-image-tools-20260921/`.

Open WebUI spricht **nicht** ComfyUI und **nicht** das bestehende MCP. Es nutzt denselben KI-Arbeitsplatz wie die Bilder-UI.

---

## Open-WebUI-Version

| Feld | Wert |
|------|------|
| Image | `ghcr.io/open-webui/open-webui:main` |
| Version | **0.11.0** |
| Bind | `127.0.0.1:3000` → Container `8080` |
| Daten | `/srv/ai/apps/open-webui/data` |
| Auth | `WEBUI_AUTH=False`, Admin `admin@localhost` |
| Ollama | `http://host.containers.internal:11434` via Pasta `--map-host-loopback 169.254.1.2` |
| Quadlet | `~/.config/containers/systemd/open-webui.container` |

Native MCP existiert in 0.11 (`open_webui/utils/mcp/client.py`), wird **nicht** verwendet.

---

## Integrationsart

Open-WebUI-**Python-Tool** (`class Tools`, id `local_images`). Workspace-Modelle `local-fast:latest` und `local-quality:latest` haben `meta.toolIds=["local_images"]`. Ollama-Aliase selbst sind unverändert.

Nur zwei öffentliche Specs: `generate_image`, `edit_image`.

Pfad:

```text
Chat (local-fast / local-quality)
  → Open-WebUI Tool local_images
  → HTTP KI-Arbeitsplatz 127.0.0.1:8790
       POST /api/images/generate   → flux2-klein-t2i-v1
       POST /api/images/stage
       POST /api/images/edit       → qwen-image-21-edit-v1
       GET  /api/images/jobs/{id}/output
  → Archiv /mnt/ai-archive/images/inbox/YYYY-MM-DD/JOB-ID/
```

Container erreicht den Arbeitsplatz als `http://host.containers.internal:8790` (dieselbe Pasta-Loopback-Map).

---

## Tool-Bridge / MCP

| Weg | Diese Phase |
|-----|-------------|
| Open-WebUI-Python-Tool `local_images` | **ja** |
| Direktes MCP Open WebUI → `local-tools :8765` | **nein** |
| Eingebaute Open-WebUI-Bildengines / Comfy-Client | **aus** (`enable_image_generation: false`) |
| MCP `local-tools` für Qwen Code | unverändert 1.3.0 / 13 Tools |

Direktes MCP wurde verworfen: es würde alle 13 Tools exponieren, `input_path` vom Modell erfinden lassen und Open-WebUI-Uploads nicht lesen können.

---

## Upload-Pfad

Open WebUI speichert Uploads im Container unter `/app/backend/data/uploads/{file_id}_{filename}` = Host `/srv/ai/apps/open-webui/data/uploads/`.

`local-tools` hat diesen Ordner **nicht** als erlaubten Root (`ReadWritePaths` bleiben `/home/mike/Projects`, `/srv/ai/workspaces`, `/mnt/ai-archive`, `/tmp`, `/var/tmp`). Deshalb liest der Adapter die Datei im Container und schickt **Bytes** an `POST /api/images/stage`. Staging bleibt `ui_stage_{uuid}` unter `/srv/ai/workspaces/ki-workplace-stage`. Kein Host-Pfad vom Modell, keine URL, kein Base64 in MCP, kein allgemeiner Dateibrowser.

Ungültige Typen (z. B. `.txt`) erzeugen keinen Edit-Job.

---

## Originalbild-Regel

Standard: erstes Nutzer-Upload in diesem Chat = `input_path`. Ein vorheriges KI-Ergebnis wird nicht automatisch weitergereicht.

Nur bei ausdrücklichen Phrasen (u. a. `Nimm dieses Ergebnis`, `Nimm das zuletzt erzeugte`, `Bearbeite das Ergebnis`, `an diesem Ergebnis`) wird `last_job_id` aus `/app/backend/data/cache/local_images_jobs/{chat_id}.json` verwendet.

Die Entscheidung hängt am **Nutzertext**, nicht an der vom Modell umgeschriebenen Tool-Anweisung. `Danke, das sieht gut aus.` startet keinen zweiten Edit.

---

## Auflösungsregel

Kein Upscaling. Frozen Backend bleibt 512 / 768 / 1024, nie größer als 1024.

| Original (längste Kante) | Chat-Default |
|--------------------------|--------------|
| ≤ 640                    | 512 |
| ≤ 896                    | 768 |
| sonst                    | 1024 |

Eine vom Nutzer **geschriebene** Zahl 512/768/1024 gilt. Vom Modell erfundene `width`/`height` ohne Zahl im Text werden ignoriert.

---

## Ergebnisanzeige

Nach Erfolg sendet das Tool `files` und `chat:message:files` mit `data:image/png;base64,…` und `local_ki_output: true`. Das Bild liegt im Chat sichtbar. Die Hauptantwort ist kein Host-Pfad. Archivierung bleibt ausschließlich das Inbox-Archiv. Open WebUI bekommt keine zweite dauerhafte Bildablage.

Native Tool-Ausführung in 0.11 braucht `chat_id` plus Assistant-`id` (`message_id`), sonst bleibt `finish_reason: tool_calls` ohne Lauf.

---

## Security

- Nur localhost. Kein öffentliches Binding. Keine Cloud.
- Adapter bindet nichts extra; er ruft den bestehenden Arbeitsplatz.
- Open WebUI sieht nur `generate_image` / `edit_image`. Memory- und PDF-Tools bleiben MCP-only.
- Keine neuen erlaubten Roots. Kein Shell. Kein allgemeines HTTP-Proxying.
- `trust: false`, `approvalMode: default`, kein YOLO.
- Workplace `image_lock` bleibt sequentiell. Generate räumt GPU im `finally` wie Edit.

---

## Tests

Unit: `tests/test_open_webui_image_tools.py` — **16 OK**.

Live: `python3 benchmarks/open_webui_image_tools_e2e.py` — **13/13 PASS**.

| Test | Ergebnis |
|------|----------|
| SHA | FLUX `d9d752d52b1430bd3756908885146daea41279e29a7b6e3a9e05705572f39953`, Edit `78a0d0f445b08557d5e69139ce7f2d2ad547658bcaf90a10cfe154121b65bbe8` |
| MCP-HEALTH | 1.3.0 / 13 Tools |
| TOOL | Specs nur `generate_image`, `edit_image` |
| CHAT-IMAGE-TALK | kein Bild-Tool |
| CHAT-BAD-FILE | kein Job |
| CHAT-GENERATE | `148297e9d23b` `flux2-klein-t2i-v1` einmal |
| CHAT-EDIT-ORIGINAL | `527b0e73279c`, Original-SHA `af0c3a65165f198ed9c287ee67b5966dd1a2deab3827b30bba8b3b50d5a40096`, 512 |
| CHAT-SIZE-512 | 512, nicht 1024 |
| CHAT-NO-DOUBLE-EDIT | kein neuer Job nach „Danke, das sieht gut aus.“ |
| CHAT-EXPLICIT-SECOND-EDIT | `a1a1fb7103b1`, Input-SHA = Output von `527b0e73279c`, `used_second_edit: true` |
| CHAT-SIZE-EXPLICIT | `e317ab836680` 1024, weiter Original-SHA |
| WORKPLACE-GENERATE | `d54456bb448e` 65,3 s, FLUX-SHA unverändert |
| CLEANUP | Comfy inactive, Staging leer |

Workplace-Unit-Tests bleiben 38 OK (Generate-`finally`-Cleanup).

---

## Rollback

Letztes Deploy-Backup: `/mnt/ai-archive/backups/open-webui-image-tools-20260921-164833`

```bash
python3 scripts/rollback-open-webui-image-tools.py \
  /mnt/ai-archive/backups/open-webui-image-tools-20260921-164833
```

Stellt `webui.db` wieder her und startet Open WebUI neu. Ollama-Aliase und Frozen-Workflows bleiben unberührt.

---

## Bekannte Einschränkungen

- `local-fast` (9B, kein Vision) sieht Uploads nicht. Tool-Doc + Systemprompt erzwingen den Call; Dateien liest der Adapter.
- Das Modell kürzt oft die Anweisung. Original-vs-Ergebnis und Größe hängen deshalb am Nutzertext.
- Native Tools brauchen `chat_id` + Assistant-`id`.
- Bildjobs bleiben sequentiell (`image_lock`). Nach Generate/Edit muss Comfy frei sein, sonst RAM-Preflight.
- Kein MCP in Open WebUI. Keine Memory-/PDF-Tools im Chat.
- Lizenz Qwen-Image-2.1: Qwen Research, privater lokaler Test, nicht kommerziell.
