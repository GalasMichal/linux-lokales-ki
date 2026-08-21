# KI-Arbeitsplatz und Lokaler Chat

Stand: 21.08.2026

## Was installiert ist

Es gibt zwei Desktop-Anwendungen:

1. **Lokaler Chat** öffnet Open WebUI in einem eigenen App-Fenster. Das ist für allgemeine Gespräche, Erklärungen und schnelle Aufgaben.
2. **KI-Arbeitsplatz** öffnet ein gemeinsames Fenster mit den Bereichen Agent, Bilder und System.

Beide Oberflächen laufen nur auf diesem Rechner. Es gibt kein LAN-Binding und keinen automatischen Cloud-Fallback.

Beide App-Fenster verwenden eigene lokale Browserprofile unter `/srv/ai/cache/brave/`. Dadurch lassen sie sich zuverlässig als getrennte Anwendungen schließen. Beim Schließen des letzten KI-Fensters werden Qwen Code, ComfyUI und geladene Ollama-Modelle kontrolliert beendet. Open WebUI speichert Chats in seiner lokalen Datenbank, Qwen schreibt Projektänderungen direkt in den Workspace und Bilder werden vor dem GPU-Cleanup auf der Archiv-HDD gesichert.

## Agent

Der Bereich **Agent** zeigt die originale Web-Shell der installierten Qwen-Code-Version. Qwen Code ist der Agent-Harness: Er kann Projekte lesen, Dateien ändern, Git verwenden sowie Builds und Tests starten. Die sichere Arbeitsregel bleibt: Änderungen nur in einem Git-Branch oder Worktree.

Beim Öffnen des Agent-Bereichs wird ComfyUI beendet. Dadurch steht die RTX 5080 dem Ollama-Modell zur Verfügung. Qwen Code läuft auf `127.0.0.1:4170`. Die Oberfläche bettet ihn über einen festen Proxy auf `127.0.0.1:8791` ein. Dieser Proxy hat kein frei wählbares Ziel und ist kein allgemeiner Netzwerk-Proxy.

Beim Schließen des Fensters bekommt der Qwen-Dienst zuerst ein reguläres Stoppsignal. Bereits geschriebene Dateien und Git-Änderungen bleiben erhalten. Eine gerade laufende Agentenaktion sollte trotzdem möglichst erst fertig werden, bevor das Fenster geschlossen wird.

Qwen-Code-Shellzugriff ist deaktiviert. `--yolo` wird nicht verwendet. Die Anzahl paralleler Sitzungen und Prompts ist auf eins begrenzt.

Der Arbeitsplatz-Proxy filtert die eingebaute Provider-Liste auf `local-fast` und `local-quality` mit der festen Ollama-URL. Provider-Anmeldungen und Modellwechsel auf andere Ziele werden mit HTTP 403 blockiert. Dadurch kann der in Qwen Code weiterhin enthaltene, aber als eingestellt markierte Qwen-OAuth-Provider nicht versehentlich aus dieser Oberfläche aktiviert werden.

## Bilder

Der Bereich **Bilder** besitzt zwei Ansichten:

- **Einfach**: Bildtext, Breite, Höhe und Seed auswählen, dann Bild erzeugen.
- **Workflow (Experte)**: vollständige ComfyUI-Oberfläche für späteres Lernen und kontrollierte Workflows.

Die einfache Ansicht verwendet ausschließlich den versionierten Workflow `flux2-klein-t2i-v1`:

- `flux-2-klein-4b-fp8.safetensors`
- `qwen_3_4b.safetensors` mit CLIP-Typ `flux2`
- `flux2-vae.safetensors`
- Batch 1
- maximal 1024 × 1024
- 4 Schritte, CFG 1.0, Sampler Euler

Vor einem Bildauftrag werden alle geladenen Ollama-Modelle entladen. Erst danach startet ComfyUI. Es können keine Shell-Befehle oder Dateipfade aus dem Bildtext übernommen werden.

ComfyUI hat keinen Autostart. Beim Schließen des letzten KI-Fensters wartet der Arbeitsplatz auf einen noch laufenden Bildauftrag und dessen Manifest. Erst danach wird ComfyUI gestoppt und die GPU freigegeben.

Ergebnisse werden nach folgendem Muster gespeichert:

```text
/mnt/ai-archive/images/inbox/JJJJ-MM-TT/JOB-ID/
├── erzeugtes-bild.png
└── manifest.json
```

Das Manifest enthält Bildtext, Seed, Größe, Laufzeit, Workflow-Hash und Modell-Hashes. Wenn die Archiv-HDD nicht eingehängt ist, stoppt der Auftrag sicher, statt versehentlich auf die Systemplatte zu schreiben.

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

## Diagnose

```bash
systemctl --user status ki-workplace.service
systemctl --user status qwen-code-web.service
journalctl --user -u ki-workplace.service -n 100 --no-pager
journalctl --user -u qwen-code-web.service -n 100 --no-pager
```

Die Oberfläche selbst benötigt keine Terminalbedienung. Diese Befehle sind nur für Diagnose und Wartung dokumentiert.

## Rollback

Jede Installation legt eine datierte Sicherung unter `/mnt/ai-archive/backups/ki-ui/` an. Der genaue Rollback-Befehl wird am Ende der Installation ausgegeben. Der alte `ki-hub` wird nur deaktiviert und gesichert, nicht gelöscht.

## Noch bewusst offen

- Open-WebUI-Chat als MCP-Client für Bilder
- Image Editing und Multi-Reference
- weitere freigegebene Visual-Agent-Workflows
- formaler A01–A14-Abschluss

Diese Punkte werden erst ergänzt, nachdem Agent, einfacher T2I-Auftrag und Chat separat stabil getestet sind.
