#!/usr/bin/env python3
"""Apply ToolSearch MCP alias patch to Qwen Code 0.24.2."""
from __future__ import annotations

import sys
from pathlib import Path

SELECT_MARKER = "function resolveSelectToolName("
KEYWORD_MARKER = "function collectKeywordCandidateNames("
INSERT_START = "function mcpShortNameForSelect"
TOKENIZE_ANCHOR = "function tokenize(query) {"

STOCK_LOOKUP = """    for (const requested of names) {
      const canonical = lowerIndex.get(requested.toLowerCase());
      if (!canonical) {
        missing.push(requested);
        continue;
      }"""

SELECT_LOOKUP = """    const ambiguous = [];
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
    const maxSubagentDepth = this.config.getMaxSubagentDepth();
    return registry.getAllTools().filter(
      (t) => registry.isDeferredAndHidden(t.name) && // Context-gated: the leader's discovery stays unrestricted (the
      // predicate itself is ungated so prepareTools can fail closed).
      !(isSubagentLikeExecutionContext() && isToolExcludedForCurrentContext(t.name, maxSubagentDepth)) && // Media-policy tools without modelAccess.enabled must never be
      // surfaced to the model — not even via keyword discovery.
      !isMediaPolicyToolHiddenFromModel(this.config, t)
    );
  }"""

NEW_CANDIDATES = """  collectCandidates() {
    const registry = this.config.getToolRegistry();
    const maxSubagentDepth = this.config.getMaxSubagentDepth();
    const all = registry.getAllTools();
    const deferredHidden = all.filter(
      (t) => registry.isDeferredAndHidden(t.name) && // Context-gated: the leader's discovery stays unrestricted (the
      // predicate itself is ungated so prepareTools can fail closed).
      !(isSubagentLikeExecutionContext() && isToolExcludedForCurrentContext(t.name, maxSubagentDepth)) && // Media-policy tools without modelAccess.enabled must never be
      // surfaced to the model — not even via keyword discovery.
      !isMediaPolicyToolHiddenFromModel(this.config, t)
    );
    const visibleMcp = all.filter((t) => !registry.isDeferredAndHidden(t.name) && mcpShortNameForSelect(t.name) && !(isSubagentLikeExecutionContext() && isToolExcludedForCurrentContext(t.name, maxSubagentDepth)) && !isMediaPolicyToolHiddenFromModel(this.config, t));
    const seen = /* @__PURE__ */ new Set();
    const out = [];
    for (const tool of [...deferredHidden, ...visibleMcp]) {
      if (seen.has(tool.name)) continue;
      seen.add(tool.name);
      out.push(tool);
    }
    return out;
  }"""

STOCK_MISSING_LLM = """    if (missing.length > 0) {
      const header = llmContent ? "\\n\\n" : "";
      llmContent += `${header}Not found: ${missing.join(", ")}`;
    }"""

AMBIGUOUS_LLM = """    if (missing.length > 0) {
      const header = llmContent ? "\\n\\n" : "";
      llmContent += `${header}Not found: ${missing.join(", ")}`;
    }
    if (ambiguous.length > 0) {
      const header = llmContent ? "\\n\\n" : "";
      const ambiguousLines = ambiguous.map((item) => {
        return 'Ambiguous tool name "' + item.requested + '". Use one of: ' + item.candidates.join(", ");
      });
      llmContent += header + ambiguousLines.join("\\n");
    }"""

STOCK_MISSING_DISPLAY = """    if (missing.length > 0) displayParts.push(`${missing.length} missing`);"""

AMBIGUOUS_DISPLAY = """    if (missing.length > 0) displayParts.push(`${missing.length} missing`);
    if (ambiguous.length > 0) displayParts.push(`${ambiguous.length} ambiguous`);"""


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
    if KEYWORD_MARKER in text and SELECT_MARKER in text and "const ambiguous = []" in text:
        return "already"

    if STOCK_LOOKUP in text:
        text = _replace_once(text, STOCK_LOOKUP, SELECT_LOOKUP, "select-lookup")
    elif SELECT_LOOKUP not in text:
        raise SystemExit("ABBRUCH: Lookup-Block nicht gefunden.")

    if STOCK_CANDIDATES in text:
        text = _replace_once(text, STOCK_CANDIDATES, NEW_CANDIDATES, "collectCandidates")
    elif NEW_CANDIDATES not in text:
        raise SystemExit("ABBRUCH: collectCandidates-Block nicht gefunden.")

    if STOCK_MISSING_LLM in text:
        text = _replace_once(text, STOCK_MISSING_LLM, AMBIGUOUS_LLM, "missing-llm")
    elif AMBIGUOUS_LLM not in text:
        raise SystemExit("ABBRUCH: missing-llm Block nicht gefunden.")

    if STOCK_MISSING_DISPLAY in text:
        text = _replace_once(text, STOCK_MISSING_DISPLAY, AMBIGUOUS_DISPLAY, "missing-display")
    elif AMBIGUOUS_DISPLAY not in text:
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
    print(apply_patch(Path(sys.argv[1]), Path(sys.argv[2])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
