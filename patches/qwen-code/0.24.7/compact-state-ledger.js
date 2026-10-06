var COMPACT_STATE_LEDGER_MARKER = "linux-lokales-ki-compact-state-ledger";
var COMPACT_STATE_LEDGER_MAX_OUTPUT = 600;
function compactStateToolName(call) {
  if (!call) return "";
  if (call.name === "tool_call") {
    const inner = call.args && call.args.name;
    return typeof inner === "string" && inner.length > 0 ? inner : "";
  }
  return typeof call.name === "string" ? call.name : "";
}
function compactStateShortName(name) {
  if (typeof name !== "string" || name.length === 0) return "";
  const parts = name.split("__");
  return parts.length > 1 ? parts[parts.length - 1] : name;
}
function compactStateArgs(call) {
  const raw = call && call.name === "tool_call" ? call.args && call.args.arguments : call && call.args;
  if (typeof raw === "string") {
    try {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }
  return raw && typeof raw === "object" ? raw : {};
}
function compactStateArtifact(args, parsed) {
  const keys = ["path", "output", "job_id", "jobId"];
  for (const source of [args, parsed]) {
    if (!source || typeof source !== "object") continue;
    for (const key of keys) {
      const value = source[key];
      if (typeof value === "string" && value.length > 0 && value.length <= 240 && !value.includes("\n")) {
        return value;
      }
    }
  }
  return "";
}
function compactStateFirstJsonObject(text) {
  if (typeof text !== "string") return null;
  const start = text.indexOf("{");
  if (start < 0) return null;
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (escape) {
        escape = false;
        continue;
      }
      if (ch === "\\") {
        escape = true;
        continue;
      }
      if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) {
        try {
          const parsed = JSON.parse(text.slice(start, i + 1));
          return parsed && typeof parsed === "object" ? parsed : null;
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}
function compactStateParsedOutput(response) {
  const output = response && response.output;
  if (typeof output === "string" && output.trim().startsWith("{")) {
    try {
      const parsed = JSON.parse(output);
      if (parsed && typeof parsed === "object") return parsed;
    } catch {
    }
    return compactStateFirstJsonObject(output);
  }
  if (output && typeof output === "object") return output;
  return null;
}
function compactStateStatus(response) {
  if (!response || typeof response !== "object") return "unknown";
  if (typeof response.error === "string" && response.error.length > 0) return "failed";
  const parsed = compactStateParsedOutput(response);
  if (parsed) {
    if (parsed.ok === false || typeof parsed.error === "string") return "failed";
    if (parsed.ok === true) return "success";
    return "unknown";
  }
  const output = response.output;
  if (typeof output === "string") {
    const head = output.slice(0, 240);
    if (/"ok"\s*:\s*false/.test(head) || /"error"\s*:\s*"/.test(head)) return "failed";
    if (/"ok"\s*:\s*true/.test(head)) return "success";
  }
  return "unknown";
}
function scanCompactStatePairs(history) {
  const calls = [];
  const responses = /* @__PURE__ */ new Map();
  for (const content of history) {
    for (const part of content && content.parts || []) {
      if (part.functionCall && part.functionCall.id) calls.push(part.functionCall);
      if (part.functionResponse && part.functionResponse.id) {
        responses.set(part.functionResponse.id, part.functionResponse);
      }
    }
  }
  const entries = [];
  for (const call of calls) {
    const name = compactStateToolName(call);
    if (!name || name === "tool_search") continue;
    const responsePart = responses.get(call.id);
    if (!responsePart) continue;
    const status = compactStateStatus(responsePart.response);
    if (status !== "success" && status !== "failed") continue;
    entries.push({
      name: compactStateShortName(name),
      status,
      artifact: compactStateArtifact(compactStateArgs(call), compactStateParsedOutput(responsePart.response))
    });
  }
  return entries;
}
function parsePriorCompactStateLedger(history) {
  const entries = [];
  const pattern = /<tool_continuity marker="linux-lokales-ki-compact-state-ledger">([\s\S]*?)<\/tool_continuity>/g;
  for (const content of history) {
    for (const part of content && content.parts || []) {
      if (typeof part.text !== "string" || !part.text.includes(COMPACT_STATE_LEDGER_MARKER)) continue;
      pattern.lastIndex = 0;
      let match;
      while (match = pattern.exec(part.text)) {
        for (const line of match[1].split("\n")) {
          const item = line.match(/^- (success|failed) (\S+)(?: artifact=(\S+))?/);
          if (!item) continue;
          entries.push({
            name: item[2],
            status: item[1] === "success" ? "success" : "failed",
            artifact: item[3] || ""
          });
        }
      }
    }
  }
  return entries;
}
function mergeCompactStateEntries(prior, current) {
  const seen = /* @__PURE__ */ new Set();
  const merged = [];
  for (const entry of [...prior, ...current]) {
    const key = `${entry.status}|${entry.name}|${entry.artifact}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(entry);
  }
  return merged.slice(-30);
}
function formatCompactStateLedger(entries) {
  const lines = ['<tool_continuity marker="linux-lokales-ki-compact-state-ledger">'];
  lines.push("completed:");
  const completed = entries.filter((entry) => entry.status === "success");
  const failed = entries.filter((entry) => entry.status === "failed");
  if (completed.length === 0) lines.push("- none");
  for (const entry of completed) {
    lines.push(`- success ${entry.name}${entry.artifact ? ` artifact=${entry.artifact}` : ""}`);
  }
  lines.push("failed:");
  if (failed.length === 0) lines.push("- none");
  for (const entry of failed) {
    lines.push(`- failed ${entry.name}${entry.artifact ? ` artifact=${entry.artifact}` : ""}`);
  }
  lines.push("Facts from recorded tool results. A success does not forbid a later call when the user asks again or an earlier call failed.");
  lines.push("</tool_continuity>");
  return lines.join("\n");
}
function shrinkCompactStateResponse(response) {
  if (!response || typeof response !== "object") return response;
  const status = compactStateStatus(response);
  const output = response.output;
  const size = typeof output === "string" ? output.length : output ? JSON.stringify(output).length : 0;
  if (status === "success" && size > COMPACT_STATE_LEDGER_MAX_OUTPUT) {
    const parsed = compactStateParsedOutput(response);
    const artifact = compactStateArtifact(null, parsed);
    const excerpt = typeof output === "string" ? output.slice(0, 400) : "";
    return {
      ...response,
      output: JSON.stringify({
        ok: true,
        compact_continuity: "excerpt",
        marker: COMPACT_STATE_LEDGER_MARKER,
        ...artifact ? { path: artifact } : {},
        ...excerpt ? { excerpt } : {}
      })
    };
  }
  if (status === "failed" && typeof output === "string" && output.length > 800) {
    return { ...response, output: output.slice(0, 800) };
  }
  return response;
}
function applyCompactStateLedger(history, pendingUserContent, entries) {
  const ledger = formatCompactStateLedger(entries);
  const first = history && history[0];
  if (first && first.role === "user" && Array.isArray(first.parts)) {
    const textPart = first.parts.find((part) => typeof part.text === "string");
    if (textPart && !textPart.text.includes(COMPACT_STATE_LEDGER_MARKER)) {
      textPart.text = `${textPart.text}

${ledger}`;
    }
  }
  if (!pendingUserContent || !Array.isArray(pendingUserContent.parts)) return pendingUserContent;
  const parts = pendingUserContent.parts.map((part) => {
    if (!part.functionResponse) return part;
    return {
      ...part,
      functionResponse: {
        ...part.functionResponse,
        response: shrinkCompactStateResponse(part.functionResponse.response)
      }
    };
  });
  if (!parts.some((part) => typeof part.text === "string" && part.text.includes(COMPACT_STATE_LEDGER_MARKER))) {
    parts.push({ text: ledger });
  }
  return { ...pendingUserContent, parts };
}
