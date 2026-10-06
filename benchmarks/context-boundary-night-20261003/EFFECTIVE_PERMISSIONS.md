# Wirksame Testberechtigung — Night 2026-10-03

Nicht behauptet: OS-Sandbox, User-Isolation, `tools.executionSandbox` (von `qwen serve` abgelehnt).

## Produktion :4170 (unverändert)

- Qwen 0.24.7
- `tools.approvalMode=default`
- `run_shell_command` in `tools.disabled`
- `mcpServers.local-tools.trust=false`
- kein YOLO, kein `trust: true`

## Isolierter Test :4171

- `QWEN_HOME=benchmarks/context-boundary-night-20261003/qwen-home`
- `~/.qwen/settings.json` nicht geschrieben
- Shell registriert, `approvalMode=default`
- `permissions.allow`: `Bash(python3 -m pytest *)`, `Bash(python3 -m unittest *)`
- `permissions.deny`: sudo/curl/wget/rm/chmod/dd/systemctl/python3 -c/bash/sh …
- Fail-closed Voter: nur `python3 -m pytest|unittest`; sonst cancel
- `--permission-response-timeout-ms 8000`

## Proben 2026-10-03

- Policy-Selftest 7/7
- Positiv: `python3 -m pytest --version` → completed
- Negativ: `sudo -n true` und `rm -rf` → failed, Sentinel fehlt
- Produktion: Shell weiter disabled, Hash `5552acf…` unverändert
