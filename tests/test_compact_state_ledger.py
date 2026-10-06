#!/usr/bin/env python3
"""The compact-state ledger is runtime evidence, not a model summary."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNIPPET = ROOT / "patches/qwen-code/0.24.2/compact-state-ledger.js"
NODE_BIN = Path("/srv/ai/apps/qwen-code/lib/qwen-code/node/bin/node")

NODE = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[1], "utf8");
const context = { Map, Set, JSON, Object };
vm.createContext(context);
vm.runInContext(code, context);
const history = [
  { role: "model", parts: [{ functionCall: { id: "c1", name: "tool_call", args: { name: "mcp__local-tools__memory_load", arguments: { workspace: "/proj" } } } }] },
  { role: "user", parts: [{ functionResponse: { id: "c1", name: "tool_call", response: { output: '{"ok":true,"files":{"STATE.md":{"content":"' + "x".repeat(2000) + '"}}}\n{"ok":true,"workspace":"/proj"}' } } }] },
  { role: "model", parts: [{ functionCall: { id: "c2", name: "tool_call", args: { name: "mcp__local-tools__pdf_create", arguments: { output: "/proj/a.pdf" } } } }] },
  { role: "user", parts: [{ functionResponse: { id: "c2", name: "tool_call", response: { output: JSON.stringify({ ok: true, path: "/proj/a.pdf" }) } } }] },
  { role: "model", parts: [{ functionCall: { id: "c3", name: "tool_search", args: { query: "select:pdf_read" } } }] },
  { role: "user", parts: [{ functionResponse: { id: "c3", name: "tool_search", response: { output: "schema" } } }] },
  { role: "model", parts: [{ functionCall: { id: "c4", name: "tool_call", args: { name: "mcp__local-tools__pdf_render", arguments: { path: "/proj/a.pdf" } } } }] },
];
const pending = { role: "user", parts: [{ functionResponse: { id: "c4", name: "tool_call", response: { output: JSON.stringify({ ok: false, error: "Pfad liegt außerhalb" }) } } }] };
const unclear = { role: "user", parts: [{ functionResponse: { id: "c9", name: "tool_call", response: { output: "not json" } } }] };
const entries = context.mergeCompactStateEntries(
  [],
  context.scanCompactStatePairs([...history, pending])
);
const ledger = context.formatCompactStateLedger(entries);
const summaryHistory = [{ role: "user", parts: [{ text: "<state_snapshot>next</state_snapshot>" }] }];
const shrunk = context.applyCompactStateLedger(summaryHistory, history[1], entries);
const output = JSON.parse(shrunk.parts[0].functionResponse.response.output);
const unknown = context.scanCompactStatePairs([
  { role: "model", parts: [{ functionCall: { id: "c9", name: "tool_call", args: { name: "mcp__local-tools__pdf_read", arguments: {} } } }] },
  unclear,
]);
console.log(JSON.stringify({
  ledger,
  names: entries.map((entry) => entry.status + " " + entry.name),
  shrunk: output,
  summaryHasLedger: summaryHistory[0].parts[0].text.includes("linux-lokales-ki-compact-state-ledger"),
  unknown: unknown,
  beforeLen: history[1].parts[0].functionResponse.response.output.length,
  afterLen: shrunk.parts[0].functionResponse.response.output.length,
}));
"""


class CompactStateLedgerTests(unittest.TestCase):
    def test_success_failure_and_excerpt(self) -> None:
        raw = subprocess.check_output([str(NODE_BIN), "-e", NODE, str(SNIPPET)], text=True)
        payload = json.loads(raw)
        self.assertIn("success memory_load", payload["names"])
        self.assertIn("success pdf_create", payload["names"])
        self.assertIn("failed pdf_render", payload["names"])
        self.assertNotIn("tool_search", " ".join(payload["names"]))
        self.assertEqual(payload["unknown"], [])
        self.assertEqual(payload["shrunk"]["ok"], True)
        self.assertEqual(payload["shrunk"]["compact_continuity"], "excerpt")
        self.assertLess(len(payload["shrunk"]["excerpt"]), 500)
        self.assertLess(payload["afterLen"], 600)
        self.assertGreater(payload["beforeLen"], 2000)
        self.assertTrue(payload["summaryHasLedger"])
        self.assertIn("linux-lokales-ki-compact-state-ledger", payload["ledger"])
        self.assertIn("artifact=/proj/a.pdf", payload["ledger"])
        self.assertNotIn("next_step", payload["ledger"])


if __name__ == "__main__":
    unittest.main()
