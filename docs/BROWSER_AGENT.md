# Lokaler Browser-Agent

Stand: 21.09.2026 19:40. **PASS.** Kein Git-Push. Kein YOLO. `trust: false`. `approvalMode: default`. Default bleibt `local-fast`.

SoT: [`docs/CHATGPT_HANDOFF.md`](CHATGPT_HANDOFF.md). Belege: `benchmarks/browser-agent-20260921/`.

Nur der Browser. Keine Desktop-Steuerung, keine Maus über den ganzen Bildschirm, kein Shell, kein JavaScript vom Modell.

---

## Engine

| Feld | Wert |
|------|------|
| Browser | **Brave 153.1.95.104**, schon installiert (`/usr/bin/brave-browser`) |
| Steuerung | **Playwright 1.55.0**, neu im MCP-venv. Kein Playwright-Chromium-Download |
| Selenium | nicht installiert, nicht benutzt |
| Qwen Computer Use | bleibt `enabled: false` |
| Fenster | sichtbar (Wayland), `--disable-gpu`, `--remote-debugging-pipe` |
| Debug-Port | keiner. Nicht `0.0.0.0` |

Playwright setzt unter der MCP-Unit (`NoNewPrivileges`) zusätzlich `--no-sandbox`. Der Dienst ist kein Root. Es gibt keinen offenen TCP-Debug-Port.

---

## Profil

Eigenes Profil: `/srv/ai/cache/browser-agent`

Eigenes Home nur für den Browserprozess: `/srv/ai/cache/browser-agent-home`

Nicht benutzt:

- persönliches Brave-Profil
- WhatsApp-Profil
- `/srv/ai/cache/brave/local-chat`
- `/srv/ai/cache/brave/ki-workplace`

Ohne das eigene Home bleibt Brave unter `ProtectHome=read-only` hängen. Das persönliche Home wird nicht beschrieben.

---

## Tools

Derselbe MCP-Server `local-tools`. Version **1.3.0 / 13 Tools → 1.4.0 / 21 Tools**.

| Tool | Rolle |
|------|--------|
| `browser_open` | `http`/`https` öffnen, Snapshot zurückgeben |
| `browser_snapshot` | URL, Titel, Text, Element-IDs |
| `browser_click` | nur eine ID aus dem letzten Snapshot |
| `browser_type` | Text in Eingabe oder Textarea, kein Enter |
| `browser_scroll` | hoch/runter, danach neuer Snapshot |
| `browser_back` | eine Seite zurück |
| `browser_screenshot` | nur das Browserfenster, PNG |
| `browser_close` | Fenster und Prozess beenden |

Kein zweiter MCP-Server. ToolSearch-Patch unverändert: Kurznamen `browser_open` → `mcp__local-tools__browser_open` laufen über die bestehende Registry.

`includeTools` und `.qwen/settings.json` `tools.visible` enthalten die acht Namen. `alwaysLoadTools` bleibt true. `trust` bleibt false.

---

## Snapshot

```text
[l1] link "Learn more"
[b1] button "Search"
[i1] input "custname"
[t1] textarea "comments"
[c1] checkbox "topping"
[s1] select "…"
```

IDs gelten nur bis zur nächsten Aktion. Eine unbekannte ID (`l99`) liefert einen Fehler und macht nichts anderes. Das Modell darf keinen Selektor erfinden.

---

## URL-Regeln

Erlaubt: `http`, `https` auf öffentliche Hosts.

Gesperrt: `file`, `javascript`, `data`, `ftp`, `chrome`, `about`, `blob`, Zugangsdaten in der URL.

Gesperrt als Ziel: `localhost`, `127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `100.64/10`, IPv6-Loopback und Link-Local. DNS-Antworten werden mitgeprüft. Eine optionale Host-Allowlist gibt es nur über `BROWSER_AGENT_ALLOW_HOSTS` (leer).

Jede Weiterleitung und jedes Unterelement läuft durch dieselbe Prüfung.

---

## Downloads und Screenshots

Downloads: `/srv/ai/workspaces/browser-downloads/`. Nur speichern. Nicht öffnen, nicht ausführen.

Abgelehnt: `.appimage`, `.exe`, `.msi`, `.sh`, `.run`, `.bin`, `.desktop` und weitere Installer-Endungen.

Screenshots: `/srv/ai/workspaces/browser-screenshots/browser-JJJJMMTT-HHMMSS.png`. Nur die Seite, nicht der Desktop. Älter als eine Stunde wird beim nächsten Screenshot gelöscht.

Klicks auf Kaufen, Bestellen, Bezahlen, Konto löschen, E-Mail senden, Upload und `Submit order` werden verweigert. Passwort- und Dateifelder nehmen keine Eingabe an.

---

## Tests

Unit: `tests/test_browser_policy.py` — **9 OK**.

Live über MCP `:8765`: `benchmarks/browser_agent_e2e.py` — **PASS**.

| Fall | Ergebnis |
|------|----------|
| BROWSER-OPEN / READ | `https://example.com/` Titel `Example Domain` |
| BROWSER-CLICK | `l1` → `https://www.iana.org/help/example-domains` |
| BROWSER-BACK | zurück auf example.com |
| BROWSER-SCREENSHOT | PNG, 19445 Bytes |
| BROWSER-INVALID-ID | `l99` Fehler, keine Ersatzaktion |
| BROWSER-BLOCK-FILE | `file:///etc/passwd` gesperrt |
| BROWSER-BLOCK-JS | `javascript:` gesperrt |
| BROWSER-BLOCK-LOCAL | `127.0.0.1:9` gesperrt |
| BROWSER-TYPE | 20 Zeichen in `i1` auf httpbin |
| BROWSER-SCROLL | `down` |
| BROWSER-CLOSE | kein Prozess mit diesem Profil |

Qwen-E2E (`local-fast`, Session `8a6243d4-b169-438f-968e-409251afee9f`): `browser_open` → `browser_click`, beide Votes `proceed_once`. Ziel danach `https://www.iana.org/help/example-domains`. `browser_open` enthält den Snapshot, deshalb kein extra `browser_snapshot`. Keine Shell.

RAM während des Live-Laufs etwa 23,3 → 23,1 GiB. Brave mit `--disable-gpu`. Nach dem Agentenlauf wurde `local-fast` entladen, VRAM wieder ~2123 MiB. ComfyUI nicht angefasst.

`tests/live_mcp_smoke.py` PASS mit 21 Tools. Bildgrößen im Schema weiter 512/768/1024. Workflow-SHA unverändert.

---

## Regression

| Prüfung | Ergebnis |
|---------|----------|
| FLUX-SHA | `d9d752d52b1430bd3756908885146daea41279e29a7b6e3a9e05705572f39953` |
| Edit-SHA | `78a0d0f445b08557d5e69139ce7f2d2ad547658bcaf90a10cfe154121b65bbe8` |
| MCP `generate_image` / `edit_image` | weiter in der Liste, Schema unverändert |
| Open WebUI `local_images` | Specs nur `generate_image`, `edit_image` |
| `local-fast` / `local-quality` | beide weiter in Ollama, Default `local-fast` |
| `trust` / `approvalMode` | `false` / `default` |

Kein neuer Bildjob in dieser Phase. Bildcode und Frozen-Workflows wurden nicht geändert.

---

## Rollback

Sicherung: `/mnt/ai-archive/backups/local-tools-mcp/20260921-192942`

```bash
/mnt/ai-archive/backups/local-tools-mcp/20260921-192942/rollback-local-tools-mcp.sh \
  /mnt/ai-archive/backups/local-tools-mcp/20260921-192942
```

Stellt MCP-Code, Unit, venv-Zeiger und die `local-tools`-Einträge in `~/.qwen/settings.json` wieder her. Ollama-Aliase bleiben. Playwright liegt nur im neuen venv und fällt mit dem Symlink weg. Profilordner unter `/srv/ai/cache/browser-agent*` bleiben liegen und werden nicht benutzt, solange die Tools weg sind.

---

## Bekannte Einschränkungen

- Headful braucht eine grafische Anmeldung (Wayland).
- Ein Browserfenster, eine Seite. Kein zweites Profil parallel.
- `browser_open` liefert den Snapshot mit. Der Agent ruft `browser_snapshot` dann oft nicht extra auf.
- Käufe, Posts und Uploads sind nur über eine Namensliste gesperrt, nicht über eine allgemeine Bestätigung.
- Kein Desktop-Agent.
