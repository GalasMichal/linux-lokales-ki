#!/usr/bin/env python3
"""Patch ToolRegistry so unique MCP short names resolve at call time (Qwen 0.24.2)."""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "resolveMcpShortToolName("

OLD_ENSURE = """  async ensureTool(name) {
    if (!this.isToolAvailable(name)) return void 0;
    const cached3 = this.tools.get(name);"""

NEW_ENSURE = """  resolveMcpShortToolName(requested) {
    if (this.tools.has(requested) || this.factories.has(requested) || this.inflight.has(requested)) {
      return requested;
    }
    const want = requested.toLowerCase();
    const allNames = this.getAllToolNames();
    for (const realName of allNames) {
      if (realName.toLowerCase() === want) return realName;
    }
    const matches = [];
    for (const realName of allNames) {
      if (!realName.toLowerCase().startsWith("mcp__")) continue;
      const rest = realName.slice(5);
      const sep = rest.indexOf("__");
      if (sep <= 0) continue;
      const shortName = rest.slice(sep + 2);
      if (shortName && shortName.toLowerCase() === want) matches.push(realName);
    }
    if (matches.length === 1) return matches[0];
    return requested;
  }
  async ensureTool(name) {
    name = this.resolveMcpShortToolName(name);
    if (!this.isToolAvailable(name)) return void 0;
    const cached3 = this.tools.get(name);"""

OLD_GET = """  getTool(name) {
    return this.isToolAvailable(name) ? this.tools.get(name) : void 0;
  }"""

NEW_GET = """  getTool(name) {
    name = this.resolveMcpShortToolName(name);
    return this.isToolAvailable(name) ? this.tools.get(name) : void 0;
  }"""

OLD_DECLARED = """      const toolName = String(fc.name);
      const args = fc.args ?? {};
      let errorMessage;
      if (!declaredToolNames.has(fc.name)) {"""

NEW_DECLARED = """      const rawToolName = String(fc.name);
      const toolName = this.runtimeContext.getToolRegistry().resolveMcpShortToolName(rawToolName);
      const args = fc.args ?? {};
      let errorMessage;
      if (!declaredToolNames.has(toolName) && !declaredToolNames.has(rawToolName)) {"""


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ABBRUCH: {label} nicht eindeutig ({count} Treffer).")
    return text.replace(old, new, 1)


def apply_patch(target: Path) -> str:
    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        return "already"
    text = _replace_once(text, OLD_ENSURE, NEW_ENSURE, "ensureTool")
    text = _replace_once(text, OLD_GET, NEW_GET, "getTool")
    if OLD_DECLARED in text:
        text = _replace_once(text, OLD_DECLARED, NEW_DECLARED, "declaredToolNames")
    if MARKER not in text:
        raise SystemExit("ABBRUCH: Registry-Marker nach Patch fehlt.")
    target.write_text(text, encoding="utf-8")
    return "applied"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: patch_registry.py TARGET", file=sys.stderr)
        return 2
    print(apply_patch(Path(sys.argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
