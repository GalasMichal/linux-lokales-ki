/**
 * Inserted into Qwen Code 0.24.6 tool-search-5QBXSAXP.js.
 * Keep in lockstep with resolve_select_tool_name.py.
 * Upstream 0.24.6 has case-resolve via resolveRegisteredToolName, but NOT MCP short-name aliases.
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
function resolveSelectToolName(requested, knownNames) {
  const want = requested.toLowerCase();
  for (const realName of knownNames) {
    if (realName.toLowerCase() === want) return { status: "ok", name: realName };
  }
  const matches = [];
  const seen = /* @__PURE__ */ new Set();
  for (const realName of knownNames) {
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
