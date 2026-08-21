#!/usr/bin/env python3
"""Apply the combined ToolSearch MCP patch to a Qwen 0.21.15 chunk file."""
from __future__ import annotations

import sys
from pathlib import Path

SELECT_MARKER = "function resolveSelectToolName("
KEYWORD_MARKER = "function collectKeywordCandidateNames("
INSERT_START = "function mcpShortNameForSelect"

STOCK_LOOKUP = """    const newlyRevealed = [];
    for (const requested of names) {
      const canonical = lowerIndex.get(requested.toLowerCase());
      if (!canonical) {
        missing.push(requested);
        continue;
      }"""

SELECT_LOOKUP = """    const newlyRevealed = [];
    const ambiguous = [];
    const alreadyAvailable = [];
    for (const requested of names) {
      const resolved = resolveSelectToolName(requested, lowerIndex);
      if (resolved.status === "missing") {
        missing.push(requested);
        continue;
      }
      if (resolved.status === "ambiguous") {
        ambiguous.push(resolved);
        continue;
      }
      const canonical = resolved.name;
      if (!canonical) {
        missing.push(requested);
        continue;
      }"""

SELECT_LOOKUP_V1 = """    const newlyRevealed = [];
    const ambiguous = [];
    for (const requested of names) {
      const resolved = resolveSelectToolName(requested, lowerIndex);
      if (resolved.status === "missing") {
        missing.push(requested);
        continue;
      }
      if (resolved.status === "ambiguous") {
        ambiguous.push(resolved);
        continue;
      }
      const canonical = resolved.name;
      if (!canonical) {
        missing.push(requested);
        continue;
      }"""

STOCK_CANDIDATES = """  collectCandidates() {
    const registry = this.config.getToolRegistry();
    return registry.getAllTools().filter((t) => registry.isDeferredAndHidden(t.name));
  }"""

NEW_CANDIDATES = """  collectCandidates() {
    const registry = this.config.getToolRegistry();
    const all = registry.getAllTools();
    const deferredHidden = all.filter((t) => registry.isDeferredAndHidden(t.name));
    const visibleMcp = all.filter((t) => !registry.isDeferredAndHidden(t.name) && mcpShortNameForSelect(t.name));
    const seen = /* @__PURE__ */ new Set();
    const out = [];
    for (const tool of [...deferredHidden, ...visibleMcp]) {
      if (seen.has(tool.name)) continue;
      seen.add(tool.name);
      out.push(tool);
    }
    return out;
  }"""

STOCK_LOADABLE = """      const isLoadable = registry.isDeferredAndHidden(canonical);
      if (isLoadable) {
        const wasRevealed = registry.isDeferredToolRevealed(canonical);
        registry.revealDeferredTool(canonical);
        if (!wasRevealed) {
          newlyRevealed.push(canonical);
        }
      }
      loaded.push(tool);"""

NEW_LOADABLE = """      const isLoadable = registry.isDeferredAndHidden(canonical);
      if (isLoadable) {
        const wasRevealed = registry.isDeferredToolRevealed(canonical);
        registry.revealDeferredTool(canonical);
        if (!wasRevealed) {
          newlyRevealed.push(canonical);
        }
      } else if (mcpShortNameForSelect(canonical)) {
        alreadyAvailable.push(canonical);
      }
      loaded.push(tool);"""

STOCK_MISSING_DISPLAY = """    if (missing.length > 0) displayParts.push(`${missing.length} missing`);"""

AMBIGUOUS_BLOCK = """    if (ambiguous.length > 0) {
      const header = llmContent ? "\\n\\n" : "";
      const ambiguousLines = ambiguous.map((item) => {
        return 'Ambiguous tool name "' + item.requested + '". Use one of: ' + item.candidates.join(", ");
      });
      llmContent += header + ambiguousLines.join("\\n");
    }
    if (alreadyAvailable.length > 0) {
      const header = llmContent ? "\\n\\n" : "";
      llmContent += header + "Already available (call by this exact name): " + alreadyAvailable.join(", ");
    }
    if (missing.length > 0) displayParts.push(`${missing.length} missing`);
    if (ambiguous.length > 0) displayParts.push(`${ambiguous.length} ambiguous`);
    if (alreadyAvailable.length > 0) displayParts.push(`${alreadyAvailable.length} already available`);"""

AMBIGUOUS_BLOCK_V1 = """    if (ambiguous.length > 0) {
      const header = llmContent ? "\\n\\n" : "";
      const ambiguousLines = ambiguous.map((item) => {
        return 'Ambiguous tool name "' + item.requested + '". Use one of: ' + item.candidates.join(", ");
      });
      llmContent += header + ambiguousLines.join("\\n");
    }
    if (missing.length > 0) displayParts.push(`${missing.length} missing`);
    if (ambiguous.length > 0) displayParts.push(`${ambiguous.length} ambiguous`);"""

TOKENIZE_ANCHOR = "function tokenize(query) {"


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
    if KEYWORD_MARKER in text and SELECT_MARKER in text and "alreadyAvailable" in text:
        return "already"

    if STOCK_LOOKUP in text:
        text = _replace_once(text, STOCK_LOOKUP, SELECT_LOOKUP, "select-lookup")
    elif SELECT_LOOKUP_V1 in text:
        text = _replace_once(text, SELECT_LOOKUP_V1, SELECT_LOOKUP, "select-lookup-v1")
    elif SELECT_LOOKUP not in text:
        raise SystemExit("ABBRUCH: Lookup-Block nicht gefunden.")

    if STOCK_CANDIDATES in text:
        text = _replace_once(text, STOCK_CANDIDATES, NEW_CANDIDATES, "collectCandidates")
    elif NEW_CANDIDATES not in text:
        raise SystemExit("ABBRUCH: collectCandidates-Block nicht gefunden.")

    if STOCK_LOADABLE in text:
        text = _replace_once(text, STOCK_LOADABLE, NEW_LOADABLE, "alreadyAvailable-load")
    elif NEW_LOADABLE not in text:
        raise SystemExit("ABBRUCH: isLoadable-Block nicht gefunden.")

    if AMBIGUOUS_BLOCK in text:
        pass
    elif AMBIGUOUS_BLOCK_V1 in text:
        text = _replace_once(text, AMBIGUOUS_BLOCK_V1, AMBIGUOUS_BLOCK, "ambiguous-v1")
    elif STOCK_MISSING_DISPLAY in text:
        text = _replace_once(text, STOCK_MISSING_DISPLAY, AMBIGUOUS_BLOCK, "missing-display")
    else:
        raise SystemExit("ABBRUCH: missing-display Block nicht gefunden.")

    text = _replace_insert(text, insert)

    if SELECT_MARKER not in text or KEYWORD_MARKER not in text:
        raise SystemExit("ABBRUCH: Marker nach Patch fehlen.")
    target.write_text(text, encoding="utf-8")
    return "applied"


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: patch_toolsearch.py TARGET INSERT_JS", file=sys.stderr)
        return 2
    status = apply_patch(Path(sys.argv[1]), Path(sys.argv[2]))
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
