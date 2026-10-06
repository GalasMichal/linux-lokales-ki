# Master-Plan

Stand: **04.10.2026 ~13:20**. Runtime-Update PASS. QUALITY produktiv **64K**. Nachtleiter scoped-Shell + 80/88/96 **fertig, kein Cutover**. Realistic 80K-Coding **fertig, kein 80K-Cutover** (order_service: 1× echter MUST-Fail, 2× Tool-Abort; kein MUST-Muster). Context Boundary bleibt **aktiv**. 1536, 2K und 4K deferred.

Hauptziel: Der lokale Stack soll zu einem möglichst autonomen lokalen KI-Entwicklungsteam werden, das allgemeine Ideen in funktionierende digitale Produkte umsetzen kann. Dazu gehören Web-Apps, Desktop-Software, Mobile-Apps, Spiele, Tools, Automatisierungen und weitere Softwareprojekte. Plattform und Tech-Stack werden pro Projekt gewählt. Qualität, Autonomie, Wiederverwendbarkeit und stabile Orchestrierung haben Vorrang vor einer bestimmten Zielplattform. Mobile- und Game-Entwicklung bleiben wichtige Use Cases, aber keine feste Hauptplattform.

## Reihenfolge

1. Continuity und Compact stabilisieren. **PASS 22.09.** Lazy Schemata + Compact State Ledger (`docs/QWEN_COMPACT_STATE_LEDGER.md`).
2. Projekt-Knowledge-Base ausbauen. **PASS 22.09.** Decisions/Failures/Fixes/Fallbacks/Replans/Research, Failure → Fix → Fallback → Replan, kompakte Retrieval-Pakete (`docs/KNOWLEDGE_BASE_V2.md`).
3. Supervisor- und Multi-Agent-Orchestrierung. **PASS 22.09.** Native Named Subagents: Supervisor + researcher / architect / reviewer (`docs/SUPERVISOR_MULTI_AGENT.md`).
4. Context bewusst benchmarken. **AKTIV.** Produktiv `local-quality` **65536**, `local-fast` **32768**. Nacht 03.–04.10.: scoped Shell 80K-Coding **5/5**, ohne Shell 80K-Coding **4/5**; 64K mit Shell **3/5**. Leiter 80/88/96: Fair-Bar nicht erfüllt. **04.10. vormittags:** Realistic 80K nur — config_merge **3/3**, ledger_repair **2/3**, order_service **0/3** (MUST-Verlust). Kein 80K-Cutover. Berichte: `docs/REALISTIC_80K_CODING_2026-10-04.md`, `docs/NIGHT_SCOPED_SHELL_LADDER_2026-10-04.md`. Vorher: `docs/RETRY_EMPTY_START_2026-10-03.md`, `docs/FAIR_64_VS_80_2026-10-03.md`, `docs/POST64K_BOUNDARY_2026-10-03.md`.
5. Autonomen Software-Development-Workflow bauen (Web, Desktop, Mobile, Spiel, Tool, Automatisierung — plattform- und stackabhängig pro Projekt). **Noch nicht gestartet** — erst wenn die höchste stabile QUALITY-Stufe und die nächste getestete Grenze festliegen.
6. Danach High-Resolution: 1536, dann 2K, dann 4K.
7. Blender und 3D später.
8. PDF-Layoutqualität später weiter verbessern.

## Modellrollen, später

`local-fast` für Routine und Orchestrierung. `local-quality` für schwere Architektur, Coding und Review. Ein geprüftes weiteres lokales Modell nur als Gegenprüfung. Bildmodelle nur für Assets.

## Jetzt nicht

Kein QUALITY-Cutover über 64K ohne erfüllte Fair-Kriterien + Freigabe. `local-fast` bleibt 32K. Kein YOLO. `trust` bleibt false. `approvalMode` bleibt default. Keine Fähigkeit löschen, nur damit der Prompt kleiner wird. Kein Cloud-Agent. Kein paralleler Writer-Pool auf dem Hauptworkspace.
