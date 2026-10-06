# Qwen ToolSearch MCP-Patch

Gilt für die **aktuell installierte** Qwen Code **0.24.2** unter `/srv/ai/apps/qwen-code`.
Ältere Sets bleiben unter `patches/qwen-code/0.23.4/` und `patches/qwen-code/0.21.15/`.

## Warum (0.24.2 stock löst das nicht)

1. `select:generate_image` vergleicht weiter nur den vollen Namen `mcp__local-tools__generate_image`.
2. Keyword `image` sucht nur versteckte Deferred-Tools. Sichtbare MCP-Tools sind keine Kandidaten.
3. `ToolRegistry.ensureTool` / `getTool` kennen keine MCP-Kurznamen.

## Was der Patch tut

- `select:`: eindeutiger MCP-Kurzname `mcp__<server>__<tool>` → `<tool>`
- Keyword: zusätzlich bereits sichtbare MCP-Tools
- Registry: `resolveMcpShortToolName` bei `ensureTool` / `getTool` / declared-tool-check
- Mehrere Keyword-Treffer: volle Namen; Kollision: Ambiguous, keine Rate
- Keine sichtbaren Builtins (`read_file`) in der Keyword-Kandidatenliste

## Anwenden

```bash
./scripts/apply-qwen-toolsearch-mcp-alias-patch.sh --check
./scripts/apply-qwen-toolsearch-mcp-alias-patch.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests/test_qwen_toolsearch_mcp_alias.py tests/test_qwen_0242_patch_apply.py
python3 patches/qwen-code/0.24.2/verify-installed-isolates.py
```

Prüft die installierte Version und bekannte SHAs. Patch-Set nicht versionsübergreifend anwenden.

## Zurück (Stock, nicht Zwischenpatch)

```bash
./scripts/rollback-qwen-toolsearch-mcp-alias-patch.sh
```

Stellt die Stock-Chunks der **aktuell installierten** Version wieder her.

## Dateien (0.24.2)

- Logik: `patches/qwen-code/0.24.2/resolve_select_tool_name.py`
- JS-Insert: `patches/qwen-code/0.24.2/tool-search-insert.js`
- Patcher: `patch_toolsearch.py`, `patch_registry.py`, `patch_git_snapshot.py`
- Ziele:
  - `lib/chunks/tool-search-ANXFKRMW.js` SHA `2034ea26…`
  - `lib/chunks/chunk-VQUX7GWP.js` SHA `2433fc7c…`
  - `lib/chunks/chunk-IOISNXQ2.js` SHA `263eaabf…`

Ändert nicht `~/.qwen/settings.json`, Ollama, MCP-Trust oder YOLO.
