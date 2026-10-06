# Open WebUI Prepared State — 2026-09-28

**Kein Pull / kein Cutover in dieser Phase.**

## Ist-Zustand

| Feld | Wert |
|------|------|
| Container | `open-webui` (Podman) |
| Image-Tag | `ghcr.io/open-webui/open-webui:main` (**floating**) |
| Image ID | `e97bf95319168ab7fdfc5bd1e869f6a1cf6349bdf6d3e8fe16c733d2ca473491` |
| Digest | `sha256:6a773e5c3a246b65cbe74ce942b294292c0e5f81c138f703d111bc162f7d7c3d` |
| Image Created | 2026-07-27 (OCI label `org.opencontainers.image.version=main`) |
| App-Version im Stack | 0.11.0 (laut Audit) |
| Unit | `open-webui.service` (user) active |
| Quadlet | `~/.config/containers/systemd/open-webui.container` → `Image=…:main` |
| Data | `/srv/ai/apps/open-webui/data` (~927 MB) |

## Floating-Tag-Risiko (`:main`)

Jeder Podman/systemd-Pull von `:main` kann ein anderes Image liefern als der aktuelle Digest. Unkontrollierte Drifts möglich bei `podman auto-update` oder manuellem Pull. **Pin auf festen Tag oder Digest empfohlen.**

## Ziel 0.11.4 (vorbereitet, nicht gezogen)

- GitHub Release: `v0.11.4` (2026-09-21)
- Empfohlener Image-Bezug: `ghcr.io/open-webui/open-webui:v0.11.4` (oder Digest nach Pull)
- Manifest-Lookup ohne Auth von hier: GHCR 401 — Digest erst beim freigegebenen Pull mit `podman pull` erfassen und pinnen

## Backup-Plan vor Cutover

1. Container stoppen: `systemctl --user stop open-webui.service`
2. Data atomar kopieren:
   ```bash
   rsync -aHAX --info=progress2 \
     /srv/ai/apps/open-webui/data/ \
     /mnt/ai-archive/backups/open-webui-data-$(date +%Y%m%d-%H%M%S)/
   ```
3. Quadlet-Datei sichern: `~/.config/containers/systemd/open-webui.container`
4. Aktuelles Image behalten (nicht `rmi`), bis Regression PASS
5. Image-Zeile auf `…:v0.11.4` oder `…@sha256:…` umstellen, `systemctl --user daemon-reload`, Start, Regression

## Vor Cutover prüfen (Docs / Features)

- Skills / AGENTS.md Integration unverändert nutzbar?
- Terminal-/Tool-Integration (falls genutzt) gegen 0.11.4 Release Notes
- MCP-Kompatibilität mit local-tools 1.6.0
- Ollama-Bind bleibt `127.0.0.1:11434`

## Status

**PREPARED ONLY — kein Update durchgeführt.**
