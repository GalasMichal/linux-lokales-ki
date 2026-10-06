/**
 * Inserted into Qwen Code 0.23.4 tool-search-XCEN7VXX.js.
 * Keep in lockstep with resolve_select_tool_name.py.
 */
function mcpShortNameForSelect(fullName) {
  if (!fullName.toLowerCase().startsWith("mcp__")) return null;
  const rest = fullName.slice(5);
  const sep = rest.indexOf("__");
  if (sep <= 0) return null;
  const shortName = rest.slice(sep + 2);
  return shortName || null;
}
__name(mcpShortNameForSelect, "mcpShortNameForSelect");
function isMcpToolName(name) {
  return mcpShortNameForSelect(name) !== null;
}
__name(isMcpToolName, "isMcpToolName");
function resolveSelectToolName(requested, lowerIndex) {
  const want = requested.toLowerCase();
  const exact = lowerIndex.get(want);
  if (exact) return { status: "ok", name: exact };
  const matches = [];
  const seen = /* @__PURE__ */ new Set();
  for (const realName of lowerIndex.values()) {
    const shortName = mcpShortNameForSelect(realName);
    if (shortName && shortName.toLowerCase() === want && !seen.has(realName)) {
      seen.add(realName);
      matches.push(realName);
    }
  }
  if (matches.length === 1) return { status: "ok", name: matches[0] };
  if (matches.length > 1) {
    matches.sort((a, b) => a.localeCompare(b));
    return { status: "ambiguous", requested, candidates: matches };
  }
  return { status: "missing", requested };
}
__name(resolveSelectToolName, "resolveSelectToolName");
function collectKeywordCandidateNames(allNames, deferredHiddenNames) {
  const hidden = /* @__PURE__ */ new Set(deferredHiddenNames.map((n) => n.toLowerCase()));
  const out = [];
  const seen = /* @__PURE__ */ new Set();
  for (const name of allNames) {
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    if (hidden.has(key) || isMcpToolName(name)) {
      seen.add(key);
      out.push(name);
    }
  }
  return out;
}
__name(collectKeywordCandidateNames, "collectKeywordCandidateNames");
function scoreKeywordToolName(name, terms) {
  const isMcp = isMcpToolName(name);
  const nameLower = name.toLowerCase();
  let total = 0;
  for (const term of terms) {
    if (!term) continue;
    if (nameLower === term || nameLower.endsWith("_" + term) || nameLower.endsWith("." + term)) {
      total += isMcp ? 12 : 10;
    } else if (nameLower.includes(term)) {
      total += isMcp ? 6 : 5;
    }
  }
  return total;
}
__name(scoreKeywordToolName, "scoreKeywordToolName");
function rankKeywordTools(query, allNames, deferredHiddenNames, maxResults = 5) {
  const terms = query.toLowerCase().split(/\s+/).filter((t) => t.length >= 2);
  const scored = [];
  for (const name of collectKeywordCandidateNames(allNames, deferredHiddenNames)) {
    const score = scoreKeywordToolName(name, terms);
    if (score > 0) scored.push({ name, score });
  }
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return a.name.localeCompare(b.name);
  });
  return scored.slice(0, maxResults).map((s) => s.name);
}
__name(rankKeywordTools, "rankKeywordTools");
