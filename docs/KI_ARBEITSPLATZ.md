# KI-Arbeitsplatz und Lokaler Chat

Stand: 21.09.2026 20:30. Runtime: Ollama 0.34.2, Qwen Code 0.24.2, ComfyUI **0.37.0**. Abnahme: `docs/ACCEPTANCE_A01_A14.md`. SoT: `docs/CHATGPT_HANDOFF.md`. Upgrade: `docs/COMFYUI_0_37_UPGRADE.md`. Image-2.1 Edit: [`docs/QWEN_IMAGE_2_1_EDIT.md`](QWEN_IMAGE_2_1_EDIT.md) (Backend + MCP) und [`docs/QWEN_IMAGE_2_1_EDIT_UI.md`](QWEN_IMAGE_2_1_EDIT_UI.md) (sichtbare Bearbeiten-Ansicht). Lokaler Chat Bilder: [`docs/OPEN_WEBUI_IMAGE_TOOLS.md`](OPEN_WEBUI_IMAGE_TOOLS.md). Browser-Agent: [`docs/BROWSER_AGENT.md`](BROWSER_AGENT.md). Desktop-Agent: [`docs/DESKTOP_AGENT.md`](DESKTOP_AGENT.md).

## Was installiert ist

Es gibt zwei Desktop-Anwendungen:

1. **Lokaler Chat** öffnet Open WebUI in einem eigenen App-Fenster. Das ist für allgemeine Gespräche, Erklärungen und schnelle Aufgaben. Bild erzeugen und bearbeiten laufen über das Tool `local_images` (nur `generate_image` / `edit_image`) gegen denselben KI-Arbeitsplatz, nicht gegen ComfyUI und nicht gegen MCP.
2. **KI-Arbeitsplatz** öffnet ein gemeinsames Fenster mit den Bereichen Agent, Bilder und System.

Beide Oberflächen laufen nur auf diesem Rechner. Es gibt kein LAN-Binding und keinen automatischen Cloud-Fallback.

Beide App-Fenster verwenden eigene lokale Browserprofile unter `/srv/ai/cache/brave/`. Dadurch lassen sie sich zuverlässig als getrennte Anwendungen schließen. Beim Schließen des letzten KI-Fensters werden Qwen Code, ComfyUI und geladene Ollama-Modelle kontrolliert beendet. Open WebUI speichert Chats in seiner lokalen Datenbank, Qwen schreibt Projektänderungen direkt in den Workspace und Bilder werden vor dem GPU-Cleanup auf der Archiv-HDD gesichert.

## Agent

Der Bereich **Agent** zeigt die originale Web-Shell der installierten Qwen-Code-Version. Qwen Code ist der Agent-Harness: Er kann Projekte lesen, Dateien ändern, Git verwenden sowie Builds und Tests starten. Die sichere Arbeitsregel bleibt: Änderungen nur in einem Git-Branch oder Worktree.

Beim Öffnen des Agent-Bereichs wird ComfyUI beendet. Dadurch steht die RTX 5080 dem Ollama-Modell zur Verfügung. Qwen Code läuft auf `127.0.0.1:4170`. Die Oberfläche bettet ihn über einen festen Proxy auf `127.0.0.1:8791` ein. Dieser Proxy hat kein frei wählbares Ziel und ist kein allgemeiner Netzwerk-Proxy.

Beim Schließen des Fensters bekommt der Qwen-Dienst zuerst ein reguläres Stoppsignal. Bereits geschriebene Dateien und Git-Änderungen bleiben erhalten. Eine gerade laufende Agentenaktion sollte trotzdem möglichst erst fertig werden, bevor das Fenster geschlossen wird.

Qwen-Code-Shellzugriff ist deaktiviert. `--yolo` wird nicht verwendet. Die Anzahl paralleler Sitzungen und Prompts ist auf eins begrenzt.

Der Arbeitsplatz-Proxy filtert die eingebaute Provider-Liste auf `local-fast` und `local-quality` mit der festen Ollama-URL. Provider-Anmeldungen und Modellwechsel auf andere Ziele werden mit HTTP 403 blockiert. Dadurch kann der in Qwen Code weiterhin enthaltene, aber als eingestellt markierte Qwen-OAuth-Provider nicht versehentlich aus dieser Oberfläche aktiviert werden.

Der Agent kann zusätzlich einen **eigenen Brave** steuern (`browser_open` bis `browser_close` über local-tools). Das Fenster gehört nur dem Agenten. Der normale Browser, der Lokale Chat und der Arbeitsplatz behalten ihre Profile. Details: [`docs/BROWSER_AGENT.md`](BROWSER_AGENT.md).

Native Fenster (Kate, Rechner, Dateimanager) gehen über `desktop_snapshot` bis `desktop_close`. Webseiten bleiben beim Browser. Terminal, Passwort und Löschen sind gesperrt. Details: [`docs/DESKTOP_AGENT.md`](DESKTOP_AGENT.md).

## Bilder

Der Bereich **Bilder** besitzt drei Ansichten:

- **Erzeugen**: Bildtext, Breite, Höhe und Seed auswählen, dann Bild erzeugen (FLUX.2 [klein]).
- **Bearbeiten**: lokales Ausgangsbild wählen, Anweisung eingeben, optional bis zu zwei Referenzbilder, dann mit Qwen-Image-2.1 bearbeiten.
- **Workflow (Experte)**: vollständige ComfyUI-Oberfläche für späteres Lernen und kontrollierte Workflows.

Die einfache Ansicht verwendet ausschließlich den versionierten Workflow `flux2-klein-t2i-v1`:

- `flux-2-klein-4b-fp8.safetensors`
- `qwen_3_4b.safetensors` mit CLIP-Typ `flux2`
- `flux2-vae.safetensors`
- Batch 1
- maximal 1024 × 1024
- 4 Schritte, CFG 1.0, Sampler Euler

Vor einem Bildauftrag werden alle geladenen Ollama-Modelle entladen. Erst danach startet ComfyUI. Es können keine Shell-Befehle oder Dateipfade aus dem Bildtext übernommen werden.

ComfyUI hat keinen Autostart (Unit **disabled**). Live-Version ist **0.37.0** unter `/srv/ai/apps/ComfyUI-0.37.0`; der 0.33.0-Tree bleibt liegen. Beim Schließen des letzten KI-Fensters wartet der Arbeitsplatz auf einen noch laufenden Bildauftrag und dessen Manifest. Erst danach wird ComfyUI gestoppt und die GPU freigegeben.

Ergebnisse werden nach folgendem Muster gespeichert:

```text
/mnt/ai-archive/images/inbox/JJJJ-MM-TT/JOB-ID/
├── erzeugtes-bild.png
└── manifest.json
```

Das Manifest enthält Bildtext, Seed, Größe, Laufzeit, Workflow-Hash und Modell-Hashes. Wenn die Archiv-HDD nicht eingehängt ist, stoppt der Auftrag sicher, statt versehentlich auf die Systemplatte zu schreiben.

Die Ansicht **Bearbeiten** spricht ausschließlich `POST /api/images/edit` an (fester Workflow `qwen-image-21-edit-v1`). Der Browser wählt lokale PNG/JPEG/WebP-Dateien; ein kleiner Staging-Endpunkt `POST /api/images/stage` legt sie unter `/srv/ai/workspaces/ki-workplace-stage` mit zufälligem Namen ab. Es gibt keinen Dateisystem-Browser und kein frei eintippbares Serverpfad-Feld. Das Ergebnis kommt aus dem Archiv über `GET /api/images/jobs/{job_id}/output`. MCP-Tool `edit_image` bleibt parallel bestehen. Details: [`docs/QWEN_IMAGE_2_1_EDIT.md`](QWEN_IMAGE_2_1_EDIT.md), [`docs/QWEN_IMAGE_2_1_EDIT_UI.md`](QWEN_IMAGE_2_1_EDIT_UI.md).

Das FLUX-Formular bleibt unverändert.

Der **Lokale Chat** erzeugt und bearbeitet Bilder nicht selbst. Open WebUI 0.11 ruft denselben Arbeitsplatz auf (`generate` / `stage` / `edit` / `output`). Hochgeladene Chat-Bilder werden im Container gelesen und nur als Staging-Kopie übergeben. Standard ist das Originalupload; ein KI-Ergebnis nur nach ausdrücklicher Anweisung. Ergebnisse erscheinen im Chat als Bild, die dauerhafte Ablage bleibt das Archiv. Details: [`docs/OPEN_WEBUI_IMAGE_TOOLS.md`](OPEN_WEBUI_IMAGE_TOOLS.md).

## System

Der Bereich **System** zeigt:

- Ollama-Version und geladenes Modell
- Qwen-Code-Status
- ComfyUI-Status
- VRAM-Nutzung
- RAM- und Swap-Nutzung
- freien Speicher auf `/srv/ai` und `/mnt/ai-archive`
- erwartete localhost-Ports

## Dienste und Ports

| Dienst | Port | Bindung | Aufgabe |
|---|---:|---|---|
| Ollama | 11434 | 127.0.0.1 | lokale Modell-Runtime |
| Open WebUI | 3000 | 127.0.0.1 | allgemeiner Chat |
| Qwen Code Web | 4170 | 127.0.0.1 | Agent-Harness |
| ComfyUI | 8188 | 127.0.0.1 | Bild-Workflows |
| KI-Arbeitsplatz | 8790 | 127.0.0.1 | gemeinsame Oberfläche |
| Qwen-Einbettungsproxy | 8791 | 127.0.0.1 | feste lokale Qwen-Einbettung |
| local-tools MCP | 8765 | 127.0.0.1 | Memory, PDF, Vision-QA, T2I, Image-Edit, isolierter Browser |

## Startreihenfolge

KI-Arbeitsplatz und `local-tools-mcp` starten mit der Benutzersitzung (`WantedBy=default.target`, `After=network.target`). MCP hängt **nicht** am Arbeitsplatz. Qwen Code Web und ComfyUI bleiben deaktiviert und starten nur über die Knöpfe Agent bzw. Bilder.

Bis 21.09.2026 erzeugte `After=default.target` am Arbeitsplatz plus `Wants=ki-workplace` am MCP einen systemd-Zyklus. systemd hat dann den MCP-Start verworfen. Fix und Rollback: `scripts/apply-mcp-independent-boot.sh` / `scripts/rollback-mcp-independent-boot.sh`. Nach einem Rechnerstart soll `curl http://127.0.0.1:8765/health` ohne Handstart funktionieren.

## Diagnose

```bash
systemctl --user status ki-workplace.service
systemctl --user status local-tools-mcp.service
systemctl --user status qwen-code-web.service
journalctl --user -u ki-workplace.service -n 100 --no-pager
journalctl --user -u local-tools-mcp.service -n 100 --no-pager
journalctl --user -u qwen-code-web.service -n 100 --no-pager
```

Die Oberfläche selbst benötigt keine Terminalbedienung. Diese Befehle sind nur für Diagnose und Wartung dokumentiert.

## Rollback

Jede Installation legt eine datierte Sicherung unter `/mnt/ai-archive/backups/ki-ui/` an. Der genaue Rollback-Befehl wird am Ende der Installation ausgegeben. Der alte `ki-hub` wird nur deaktiviert und gesichert, nicht gelöscht.

## Noch bewusst offen

- High-Resolution Image Pipeline: 1536, 2K direkt, 2K-Upscale, 4K-Upscale (deferred, nicht gestartet)
- Compact State Ledger 22.09.: **PASS**. Folgeprompt nach Compact **9318**. Bericht: `docs/QWEN_COMPACT_STATE_LEDGER.md`.
- Lazy Tool Loading bleibt (`alwaysLoadTools: false`). Compact-Prompt-Patch bleibt nicht installiert.

A01–A14 inklusive Reboot-Beweis ist dokumentiert. Die sichtbare Image-Editing-UI ist PASS. Open-WebUI-Bild-Tools sind PASS. Der lokale Browser-Agent ist PASS. Der Desktop-Agent ist PASS. MCP local-tools ist 1.5.0 mit 29 Tools. Bildgrößen bleiben 512, 768 und 1024.

## Knowledge Base v2

Seit 22.09.2026: MCP `local-tools` 1.6.0 mit `knowledge_*` (lazy). SoT: `docs/KNOWLEDGE_BASE_V2.md`.
