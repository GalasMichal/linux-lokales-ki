# Lokaler KI-Stack

Dieses private Repository dokumentiert und versioniert den real installierten lokalen KI-Stack unter `/srv/ai`.

## Aktueller Ausbau

- Ollama nur auf `127.0.0.1:11434`
- Qwen Code als lokaler Agent
- Open WebUI als separater lokaler Chat
- ComfyUI mit FLUX.2 [klein] 4B
- KI-Arbeitsplatz als Desktop-Oberfläche für Agent, Bilder und Systemstatus
- automatische sequenzielle GPU-Nutzung zwischen Ollama und ComfyUI
- GPU-Cleanup nach dem Schließen des letzten KI-Fensters
- Qwen-Provider-Sperre auf `local-fast` und `local-quality`

Die Desktop-Oberfläche liegt unter [`apps/ki-workplace`](apps/ki-workplace). Sie benötigt keine Cloud-Verbindung und akzeptiert keine Netzwerkverbindungen außerhalb von `127.0.0.1`.

Qwen-Code-Skills (ohne Cursor-Routing) liegen unter [`skills/`](skills/). Einrichtung: `./scripts/setup-qwen-skills.sh`. Details: [`docs/QWEN_SKILLS.md`](docs/QWEN_SKILLS.md).

## Entwicklungstest

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests/test_ki_workplace.py
```

## Installation

Die Installation verändert User-Dienste und Desktop-Starter. Deshalb darf sie erst nach ausdrücklicher Bestätigung ausgeführt werden:

```bash
./scripts/deploy-local-ui.sh
```

Vorhandene Dateien werden vorher auf der Archiv-HDD unter `/mnt/ai-archive/backups/ki-ui/` gesichert. Das Skript zeigt anschließend den konkreten Rollback-Befehl.
