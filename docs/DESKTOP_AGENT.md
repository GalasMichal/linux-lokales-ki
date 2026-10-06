# Lokaler Desktop-Agent

Stand: 21.09.2026 20:30. **PASS.** Kein Git-Push. Kein YOLO. `trust: false`. `approvalMode: default`. Default bleibt `local-fast`.

SoT: [`docs/CHATGPT_HANDOFF.md`](CHATGPT_HANDOFF.md). Browser bleibt [`docs/BROWSER_AGENT.md`](BROWSER_AGENT.md) und wurde nicht umgebaut.

Der Agent bedient sichtbare KDE-Fenster. Er bekommt keine freie Maus und keine freie Tastatur für den ganzen Bildschirm.

---

## Sitzung

| Feld | Wert |
|------|------|
| Anzeige | **Wayland**, `wayland-0`, zusätzlich `DISPLAY=:0` |
| Desktop | **KDE Plasma 6.7.4**, KWin 6.7.4 |
| Monitore | DP-1 an, 2560×1440, Skalierung 1. HDMI-A-1 steckt, ist aus |
| MCP | `local-tools` **1.5.0**, **29 Tools** (vorher 1.4.0 / 21) |

---

## Steuerung

```text
Qwen
  → local-tools MCP
  → desktop_* 
  → kurzer Helfer (/usr/bin/python3)
  → KWin-DBus und AT-SPI
```

Kein zweiter Agent. Kein VNC. Kein Remote-Desktop. Kein eigener Port. Kein `0.0.0.0`.

| Aufgabe | Schnittstelle |
|---------|----------------|
| Fensterliste, Fokus, Größe, Monitor | festes KWin-Skript, nur für diesen Aufruf geladen und danach entladen |
| Screenshot | `spectacle -b -n -f`, eigenes Home unter `/srv/ai/cache/desktop-agent-home` |
| Text, Klick, Auswahl, Kopieren, Scroll | AT-SPI (Bedienungshilfe), schon installiert |
| Monitore | `kscreen-doctor` |

Nicht benutzt und nicht installiert: `ydotool`, `wtype`, `dotool`, `xdotool`. `/dev/uinput` gehört root. Der Benutzer ist nicht in der Gruppe `input`. Deshalb kein Eingabe-Daemon.

Das KWin-Skript liegt unter `/srv/ai/cache/desktop-agent/bridge.js`. Es kann nur die Fensterliste schreiben oder ein Fenster mit einer festen ID nach vorn holen. Es führt keine Befehle aus.

---

## Werkzeuge

| Tool | Wirkung |
|------|---------|
| `desktop_snapshot` | Monitore, Fenster `[w1]`, Fokus, Elemente `[e1]`, PNG |
| `desktop_focus` | Ein Fenster aus dem letzten Snapshot nach vorn |
| `desktop_click` | Element-ID, sonst ein Punkt nur innerhalb dieses Fensters |
| `desktop_type` | Text in ein Textfeld dieses Fensters |
| `desktop_scroll` | `up` oder `down` im Text |
| `desktop_key` | nur Escape, Enter, Tab, Shift+Tab, Ctrl+A, Ctrl+C, Ctrl+V |
| `desktop_screenshot` | PNG nach `/srv/ai/workspaces/desktop-screenshots/` |
| `desktop_close` | IDs verwerfen. Schließt keine Programme |

Fenster-IDs gelten nur bis zum nächsten Snapshot. Eine unbekannte ID bricht ab. Es wird kein anderes Fenster genommen.

Ein Klick auf eine Koordinate geht nur, wenn an dem Punkt ein Bedienungshilfe-Element liegt und der Punkt im Fenster ist. Es gibt keinen Klick auf den ganzen Bildschirm.

Ctrl+A markiert den Text im Feld. Ctrl+C kopiert diese Markierung. Ctrl+V fügt die Zwischenablage ein. Enter schreibt einen Zeilenumbruch. Tab springt zum nächsten Feld. Escape holt nur den Fensterrahmen nach vorn. Super, Alt+F2 und virtuelle Konsolen sind gesperrt.

---

## Sperren

Eingabe wird verweigert, das Fenster darf aber im Snapshot stehen:

- Terminal, Konsole, Kitty, Alacritty und die anderen üblichen Terminals
- Brave, Firefox und andere Browser. Dafür bleiben `browser_*`
- Cursor und Entwicklerkonsolen
- ChatGPT, Mail und Messenger
- Polkit, KWallet, Passwortfelder. Ein Fenster mit Passwortfeld wird beschrieben und nicht ausgefüllt
- Ausführen-Dialog (KRunner), Plasma-Leiste, Absturzbericht

Klicks auf Löschen, Verschieben, Umbenennen, Senden, Kaufen, Bezahlen, Herunterfahren, Installieren und ähnliche Namen stoppen mit einer klaren Meldung. In den Systemeinstellungen sind Anwenden und OK gesperrt.

Es werden keine Geheimnisse aus Dateien oder aus dem Memory geholt.

---

## Rechte

| Frage | Antwort |
|-------|---------|
| Root oder sudo | nein |
| Hintergrund-Daemon | nein. KWin, Portal und AT-SPI liefen schon |
| Andere Benutzer | nein. Nur die Sitzung von `mike` auf dem User-Bus |
| Globale Tastatureingabe | nein |
| `trust` | bleibt `false` |
| Zustimmung | `proceed_once`. Kein `always_allow` |
| Computer Use | bleibt aus |
| Bedienungshilfe | `org.a11y.Status.IsEnabled` wurde für diese Sitzung eingeschaltet. Der AT-SPI-Dienst war schon da |

Spectacle bekommt ein eigenes Home, damit es unter `ProtectHome=read-only` nicht hängt und nicht ins persönliche Home schreibt.

---

## Tests

Policy-Tests: `tests/test_desktop_policy.py`, zusammen mit den Browser-Tests **15 OK**.

Live, ohne Root:

- Snapshot: DP-1 und HDMI, Fenster, Fokus, PNG 2560×1440
- Kate fokussiert, Text `Desktop Agent Test`, Ctrl+A, Ctrl+C, Scroll
- KCalc-Knopf `Eins`, Anzeige `1`
- `Löschen` blockiert. Knopf `Info` ging
- Passwortfeld blieb leer (0 Zeichen)
- Konsole: Tippen blockiert
- unbekannte Fenster-ID: Fehler, keine Ersatzaktion
- `desktop_close` beendet nur die IDs

Qwen `local-fast`, Session `7276c1fe-221e-4e87-b73f-0289683b8af9`: `desktop_snapshot` → `desktop_type` → `desktop_snapshot`. Dreimal `proceed_once`. Keine Shell, keine Browser-Tools. In Kate steht `Hallo vom lokalen Desktop-Agenten`. Ein eigenes `desktop_focus` war nicht nötig, weil die Fenster-ID direkt an `desktop_type` ging.

RAM während des Snapshots praktisch unverändert (etwa 10,7 GiB belegt). Kein Ollama-Modell bleibt geladen. VRAM der Desktop-Tools selbst: keins. Die Grafikkarte blieb bei den schon laufenden Programmen.

Browser danach: `file`, `javascript` und `127.0.0.1` weiter gesperrt. `memory_load` OK. Bildgrößen im Smoke weiter 512/768/1024. FLUX- und Edit-SHA nicht angefasst.

---

## Backup

`/mnt/ai-archive/backups/local-tools-mcp/20260921-202347`

Zurück:

```bash
/mnt/ai-archive/backups/local-tools-mcp/20260921-202347/rollback-local-tools-mcp.sh \
  /mnt/ai-archive/backups/local-tools-mcp/20260921-202347
```

Das entfernt die Desktop-Tools und stellt die MCP-Version aus der Sicherung wieder her. Browser, Memory, PDF und Bild-Tools aus der Sicherung bleiben. Kein `git reset`.

Git HEAD `abd0282f0939a321d4735b1579b68a86c1c7e61d`. Kein Push.

---

## Grenzen

Koordinaten ohne Element gibt es nicht. Ein zweiter Monitor ist angeschlossen, aber aus. Dateien löschen, verschieben oder umbenennen geht über die Oberfläche nicht. Webseiten bleiben beim Browser-Agenten.

---

## Später, nicht jetzt

High-Resolution Image Pipeline (1536, 2K, 4K), optionaler Compact-Prompt-Patch, 32K QUALITY nicht produktiv.
