#!/usr/bin/env python3
"""Apply ToolSearch MCP short-name alias patch to Qwen Code 0.24.6 (minified chunks)."""
from __future__ import annotations

import sys
from pathlib import Path

SELECT_MARKER = "function resolveSelectToolName("
INSERT_START = "function mcpShortNameForSelect"
TOKENIZE_ANCHOR = "function tokenize(query){"

# Stock 0.24.6 uses resolveRegisteredToolName (case only). Extend with MCP short alias.
STOCK_LOOKUP = (
    "const canonical=resolveRegisteredToolName(canonicalToolName(requested),knownNames);"
    "if(Array.isArray(canonical)){ambiguous.push({requested,candidates:canonical});continue}"
    "if(!canonical){missing.push(requested);continue}"
)

SELECT_LOOKUP = (
    "let canonical=resolveRegisteredToolName(canonicalToolName(requested),knownNames);"
    "if(Array.isArray(canonical)){ambiguous.push({requested,candidates:canonical});continue}"
    "if(!canonical){"
    "const shortResolved=resolveSelectToolName(requested,knownNames);"
    'if(shortResolved.status==="ambiguous"){ambiguous.push({requested:shortResolved.requested,candidates:shortResolved.candidates});continue}'
    'if(shortResolved.status==="ok"){canonical=shortResolved.name}'
    "else{missing.push(requested);continue}"
    "}"
)

STOCK_CANDIDATES = (
    "collectCandidates(){const registry=this.config.getToolRegistry();"
    "const maxSubagentDepth=this.config.getMaxSubagentDepth();"
    "return registry.getAllTools().filter(t=>registry.isDeferredAndHidden(t.name)"
    "&&!(isSubagentLikeExecutionContext()&&isToolExcludedForCurrentContext(t.name,maxSubagentDepth))"
    "&&!isMediaPolicyToolHiddenFromModel(this.config,t))}"
)

NEW_CANDIDATES = (
    "collectCandidates(){const registry=this.config.getToolRegistry();"
    "const maxSubagentDepth=this.config.getMaxSubagentDepth();"
    "const all=registry.getAllTools();"
    "const deferredHidden=all.filter(t=>registry.isDeferredAndHidden(t.name)"
    "&&!(isSubagentLikeExecutionContext()&&isToolExcludedForCurrentContext(t.name,maxSubagentDepth))"
    "&&!isMediaPolicyToolHiddenFromModel(this.config,t));"
    "const visibleMcp=all.filter(t=>!registry.isDeferredAndHidden(t.name)&&mcpShortNameForSelect(t.name)"
    "&&!(isSubagentLikeExecutionContext()&&isToolExcludedForCurrentContext(t.name,maxSubagentDepth))"
    "&&!isMediaPolicyToolHiddenFromModel(this.config,t));"
    "const seen=/* @__PURE__ */new Set();const out=[];"
    "for(const tool of[...deferredHidden,...visibleMcp]){if(seen.has(tool.name))continue;seen.add(tool.name);out.push(tool)}"
    "return out}"
)


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ABBRUCH: {label} nicht eindeutig ({count} Treffer).")
    return text.replace(old, new, 1)


def _replace_insert(text: str, insert: str) -> str:
    start = text.find(INSERT_START)
    if start < 0:
        if TOKENIZE_ANCHOR not in text:
            raise SystemExit("ABBRUCH: tokenize()-Anker fehlt.")
        return text.replace(TOKENIZE_ANCHOR, insert + TOKENIZE_ANCHOR, 1)
    end = text.find(TOKENIZE_ANCHOR, start)
    if end < 0:
        raise SystemExit("ABBRUCH: tokenize() nach Insert-Block fehlt.")
    return text[:start] + insert + text[end:]


def apply_patch(target: Path, insert_js: Path) -> str:
    text = target.read_text(encoding="utf-8")
    insert = insert_js.read_text(encoding="utf-8").rstrip() + "\n"
    if SELECT_MARKER in text and "mcpShortNameForSelect" in text and SELECT_LOOKUP in text:
        return "already"

    if STOCK_LOOKUP in text:
        text = _replace_once(text, STOCK_LOOKUP, SELECT_LOOKUP, "select-lookup")
    elif SELECT_LOOKUP not in text:
        raise SystemExit("ABBRUCH: Lookup-Block nicht gefunden.")

    if STOCK_CANDIDATES in text:
        text = _replace_once(text, STOCK_CANDIDATES, NEW_CANDIDATES, "collectCandidates")
    elif NEW_CANDIDATES not in text:
        raise SystemExit("ABBRUCH: collectCandidates-Block nicht gefunden.")

    text = _replace_insert(text, insert)

    if SELECT_MARKER not in text or "mcpShortNameForSelect" not in text:
        raise SystemExit("ABBRUCH: Marker nach Patch fehlen.")
    target.write_text(text, encoding="utf-8")
    return "applied"


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: patch_toolsearch.py TARGET INSERT_JS", file=sys.stderr)
        return 2
    print(apply_patch(Path(sys.argv[1]), Path(sys.argv[2])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
