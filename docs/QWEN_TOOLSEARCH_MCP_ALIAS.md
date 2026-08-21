# Qwen ToolSearch MCP-Patch

Gilt nur für **Qwen Code 0.21.15** unter `/srv/ai/apps/qwen-code`.

## Warum

1. `select:generate_image` verglich nur den vollen Namen `mcp__local-tools__generate_image`.
2. Keyword `image` suchte nur versteckte Deferred-Tools. Das sichtbare MCP-Bildtool war kein Kandidat.

## Was der Patch tut

- `select:`: eindeutiger MCP-Kurzname `mcp__<server>__<tool>` → `<tool>`
- Keyword: zusätzlich bereits sichtbare MCP-Tools; Ranking wie bisher (Name, inkl. `_image`)
- Mehrere Keyword-Treffer: alle mit vollem Namen
- `select:`-Kollision: keine Rate, Ambiguous-Meldung
- Kein generisches Aufnehmen sichtbarer Builtins (`read_file`)

## Anwenden

```bash
./scripts/apply-qwen-toolsearch-mcp-alias-patch.sh --check
./scripts/apply-qwen-toolsearch-mcp-alias-patch.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests/test_qwen_toolsearch_mcp_alias.py
python3 patches/qwen-code/0.21.15/verify-installed-isolates.py
```

Prüft Version `0.21.15` und bekannte SHAs. Nicht blind auf eine neuere Qwen-Version anwenden.

## Zurück (Stock, nicht Zwischenpatch)

```bash
./scripts/rollback-qwen-toolsearch-mcp-alias-patch.sh
```

## Dateien

- Logik: `patches/qwen-code/0.21.15/resolve_select_tool_name.py`
- JS-Insert: `patches/qwen-code/0.21.15/tool-search-insert.js`
- Patcher: `patches/qwen-code/0.21.15/patch_toolsearch.py`
- Ziel: `/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-4NQJASFC.js`

Ändert nicht `~/.qwen/settings.json`, Ollama, MCP-Trust oder YOLO.
