from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "apps" / "local-tools"
sys.path.insert(0, str(TOOLS_DIR))

from errors import ToolError  # noqa: E402
from memory import MEMORY_FILES, memory_load, memory_update  # noqa: E402


class AgentMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="local-ai-memory-")
        self.workspace = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_bootstraps_and_returns_compact_files(self):
        result = memory_load(self.workspace)
        self.assertTrue(result["ok"])
        self.assertEqual(set(result["files"]), set(MEMORY_FILES))
        self.assertTrue((self.workspace / ".agent" / "STATE.md").is_file())
        self.assertIn("source of truth", result["instruction"])
        self.assertLessEqual(result["budget"]["loaded_chars"], result["budget"]["max_total_chars"])

    def test_update_writes_state_tasks_and_appends_decisions(self):
        memory_load(self.workspace)
        first = memory_update(
            self.workspace,
            summary="first decision",
            state="# State\n\nPhase: smoke\n",
            tasks="# Tasks\n\n- [x] load memory\n- [ ] next\n",
            decisions="Use `.agent/` files, not Qwen auto-memory.",
            decision_title="Persistent memory store",
        )
        self.assertTrue(first["ok"])
        self.assertIn("DECISIONS.md", first["changed"])
        second = memory_update(
            self.workspace,
            summary="second decision",
            decisions="PDF tools stay on the existing local-tools MCP server.",
            decision_title="PDF via local-tools",
        )
        text = (self.workspace / ".agent" / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn("Persistent memory store", text)
        self.assertIn("PDF via local-tools", text)
        self.assertGreaterEqual(text.count("## "), 2)
        history = list((self.workspace / ".agent" / "history").glob("*.md"))
        self.assertGreaterEqual(len(history), 2)
        loaded = memory_load(self.workspace)
        self.assertIn("Phase: smoke", loaded["files"]["STATE.md"]["content"])
        self.assertIn("[x] load memory", loaded["files"]["TASKS.md"]["content"])

    def test_update_rejects_empty_summary(self):
        with self.assertRaises(ToolError):
            memory_update(self.workspace, summary="  ")

    def test_rejects_unknown_memory_file(self):
        with self.assertRaises(ToolError):
            memory_load(self.workspace, files=["secrets.env"])

    def test_history_names_are_listed_not_inlined(self):
        memory_update(self.workspace, summary="note", state="alive")
        loaded = memory_load(self.workspace)
        self.assertTrue(loaded["recent_history"])
        for item in loaded["recent_history"]:
            self.assertIn("name", item)
            self.assertNotIn("content", item)

    def test_decisions_compact_keeps_recent_and_older_headings(self):
        memory_load(self.workspace)
        for index in range(8):
            memory_update(
                self.workspace,
                summary=f"decision {index}",
                decisions=f"Body for decision {index} stays available on disk.",
                decision_title=f"Decision {index}",
            )
        loaded = memory_load(self.workspace)
        content = loaded["files"]["DECISIONS.md"]["content"]
        self.assertTrue(loaded["files"]["DECISIONS.md"]["compacted"])
        self.assertIn("Older decisions (headings only", content)
        self.assertIn("Decision 7", content)
        self.assertIn("Body for decision 7", content)
        self.assertIn("Decision 0", content)
        self.assertNotIn("Body for decision 0", content)
        self.assertIn("next required tool", loaded["instruction"])
        self.assertNotIn("After the task, call memory_update.", loaded["instruction"])

    def test_requirements_are_not_dropped_when_compacting_decisions(self):
        memory_load(self.workspace)
        memory_update(
            self.workspace,
            summary="keep requirements",
            requirements="# Requirements\n\nMust keep local-only and trust false.\n",
        )
        for index in range(6):
            memory_update(
                self.workspace,
                summary=f"later {index}",
                decisions=f"later body {index}",
                decision_title=f"Later {index}",
            )
        loaded = memory_load(self.workspace)
        self.assertIn("trust false", loaded["files"]["REQUIREMENTS.md"]["content"])
        self.assertFalse(loaded["files"]["REQUIREMENTS.md"]["truncated"])

    def test_completed_tasks_are_compacted(self):
        memory_load(self.workspace)
        lines = ["# Tasks", ""] + [f"- [x] done {i}" for i in range(8)] + ["- [ ] still open"]
        (self.workspace / ".agent" / "TASKS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        loaded = memory_load(self.workspace)
        content = loaded["files"]["TASKS.md"]["content"]
        self.assertTrue(loaded["files"]["TASKS.md"]["compacted"])
        self.assertIn("Completed: 8", content)
        self.assertIn("still open", content)
        self.assertNotIn("done 0", content)



if __name__ == "__main__":
    unittest.main()
