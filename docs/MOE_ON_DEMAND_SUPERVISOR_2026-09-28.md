# MoE On-Demand Supervisor — 2026-09-28

## Verdict

**PASS.** CPU-MoE `Qwen3-Coder-30B-A3B-Instruct-Q4_K_S` ist als on-demand MCP-Tool `moe_consult` verfügbar. Kein systemd, kein Dauerprozess, `local-fast` bleibt Default.

## Integration

| Item | Wert |
|------|------|
| MCP Tool | `moe_consult` |
| MCP Version | **1.7.0** (33 Tools) |
| Modul | `apps/local-tools/moe_consult.py` → live `/srv/ai/apps/local-tools/` |
| Runtime | `/srv/ai/apps/llama.cpp-0.5.0/llama-cli` |
| Model | `/srv/ai/models/gguf/qwen3-coder-30b-a3b/Qwen3-Coder-30B-A3B-Instruct-Q4_K_S.gguf` |
| Flags | `-ngl 0 -t 16 -c 4096 --jinja --reasoning off -st --temp 0.2` |
| Roles | `planner`, `reviewer`, `architect`, `supervisor`, `second_opinion` |
| Tokens | role defaults 384–640, clamp 64–768 |
| Timeout | default 300s (explizit ab 2s erlaubt für Cleanup-Tests) |

## Guards

- MemAvailable &lt; 8 GiB → Start verweigert
- Ein Lock unter `/srv/ai/cache/moe_consult.lock`
- Nur eigene llama.cpp-Prozesse (Pfad `/srv/ai/apps/llama.cpp*` / GGUF), nicht Ollama
- Timeout/Fehler: Prozessgruppe SIGTERM→SIGKILL, Lock weg, leftover-Sweep
- Kein Port, kein Server-Daemon

## Routing (leicht)

Keine invasive Auto-Klassifikation. Instruktionen:

- Architect/Reviewer dürfen `moe_consult` gezielt nutzen
- Researcher normalerweise nicht
- Trivial (Rename, CSS, One-Liner): kein MoE
- Antwort ist **Zweitmeinung** (`authority: advisory`) — Hauptagent prüft Code/Tests

Dateien: `.qwen/agents/{architect,reviewer,researcher}.md`, `skills/supervisor-team/SKILL.md`, `QWEN.md`

## Tests

Artefakte: `benchmarks/moe_ondemand_2026-09-28/`

| Test | Ergebnis |
|------|----------|
| Architecture / Reviewer consult | PASS (Antwort + Cleanup) |
| Timeout cleanup (4s) | PASS, kein Zombie |
| Repeated after timeout | PASS |
| Parallel local-fast GPU + MoE CPU | PASS (`ngl=0`, leftover `[]`) |
| Trivial routing | Instruction-only PASS (`routing_note.json`) |

## Security

Unverändert: `trust: false`, `approvalMode: default`, kein YOLO, erlaubte Roots, kein permanenter MoE-Dienst.
