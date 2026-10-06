from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "apps" / "local-tools"
sys.path.insert(0, str(TOOLS_DIR))

from errors import ToolError  # noqa: E402
from knowledge import (  # noqa: E402
    bootstrap_knowledge,
    knowledge_get,
    knowledge_record,
    knowledge_search,
)


class KnowledgeBaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="local-ai-kb-")
        self.workspace = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bootstrap_seeds_curated_entries(self):
        boot = bootstrap_knowledge(self.workspace)
        self.assertTrue(boot["ok"])
        self.assertTrue(boot["seeded"])
        self.assertGreaterEqual(boot["count"], 15)
        entries = (self.workspace / ".agent" / "knowledge" / "entries.jsonl").read_text(encoding="utf-8")
        self.assertIn("KB-20260922-LEDGER-002", entries)
        self.assertIn("docs/QWEN_COMPACT_STATE_LEDGER.md", entries)

    def test_record_decision_failure_fix_chain(self):
        bootstrap_knowledge(self.workspace)
        fail = knowledge_record(
            self.workspace,
            type="failure",
            topic="unit-chain",
            summary="Approach A failed in unit test.",
            status="failed",
            cause="missing precondition",
            do_not_repeat=True,
            force_new=True,
        )
        self.assertTrue(fail["ok"])
        fix = knowledge_record(
            self.workspace,
            type="fix",
            topic="unit-chain",
            summary="Approach B fixed unit-chain failure.",
            status="validated",
            result="pass",
            fixes=fail["id"],
            evidence="tests/test_knowledge_base.py",
            force_new=True,
        )
        self.assertTrue(fix["ok"])
        fallback = knowledge_record(
            self.workspace,
            type="fallback",
            topic="unit-chain",
            summary="Keep Approach B; do not retry A.",
            status="active",
            fallback_for=fail["id"],
            force_new=True,
        )
        replan = knowledge_record(
            self.workspace,
            type="replan",
            topic="unit-chain",
            summary="Replan unit-chain after fix B.",
            status="active",
            relates_to=f"{fail['id']},{fix['id']}",
            force_new=True,
        )
        search = knowledge_search(self.workspace, "unit-chain Approach A failed")
        ids = {hit["id"] for hit in search["hits"]}
        self.assertIn(fail["id"], ids)
        package = search["package"]
        self.assertIn("KNOWN FAILURE", package)
        # Relations visible via get
        got = knowledge_get(self.workspace, fix["id"])
        self.assertIn(fail["id"], got["entry"]["relations"]["fixes"])
        self.assertTrue(fallback["ok"] and replan["ok"])

    def test_get_and_search_compact(self):
        bootstrap_knowledge(self.workspace)
        got = knowledge_get(self.workspace, "KB-20260922-LEDGER-002")
        self.assertTrue(got["ok"])
        self.assertEqual(got["entry"]["type"], "fix")
        search = knowledge_search(self.workspace, "Was hat die doppelten PDF-Tool-Calls nach Compact gelöst?")
        self.assertTrue(search["hits"])
        self.assertLessEqual(search["stats"]["approx_tokens"], 1500)
        text = search["package"].lower()
        self.assertTrue("ledger" in text or "tool_continuity" in text or "determin" in text)

    def test_lazy_overflow_query(self):
        bootstrap_knowledge(self.workspace)
        search = knowledge_search(self.workspace, "Warum sind die MCP-Schemas lazy?")
        blob = json.dumps(search, ensure_ascii=False).lower()
        self.assertIn("17216", blob)
        self.assertIn("lazy", blob)

    def test_systemd_query(self):
        bootstrap_knowledge(self.workspace)
        search = knowledge_search(self.workspace, "Was ist beim systemd Startproblem passiert?")
        blob = json.dumps(search, ensure_ascii=False).lower()
        self.assertIn("systemd", blob)
        self.assertTrue("cycle" in blob or "boot" in blob)

    def test_superseded_roadmap(self):
        bootstrap_knowledge(self.workspace)
        search = knowledge_search(self.workspace, "Was kommt nach Desktop-Agent?")
        statuses = {hit["id"]: hit["status"] for hit in search["hits"]}
        package = search["package"]
        self.assertIn("SUPERSEDED", package)
        # Active replan should rank at or near top
        top_types = [hit["type"] for hit in search["hits"][:3]]
        self.assertTrue("replan" in top_types or any(h["status"] == "active" for h in search["hits"][:3]))
        if "KB-20260921-ROADMAP-000" in statuses:
            self.assertEqual(statuses["KB-20260921-ROADMAP-000"], "superseded")

    def test_no_result(self):
        bootstrap_knowledge(self.workspace)
        search = knowledge_search(self.workspace, "quantum banana renderer")
        self.assertEqual(search["hits"], [])
        self.assertIn("no relevant knowledge", search["package"])

    def test_dedupe(self):
        bootstrap_knowledge(self.workspace)
        first = knowledge_record(
            self.workspace,
            type="fix",
            topic="dedupe-topic",
            summary="Identical fix summary for dedupe.",
            status="validated",
            evidence="tests/test_knowledge_base.py",
            force_new=True,
        )
        second = knowledge_record(
            self.workspace,
            type="fix",
            topic="dedupe-topic",
            summary="Identical fix summary for dedupe.",
            status="validated",
            evidence="docs/KNOWLEDGE_BASE_V2.md",
        )
        self.assertTrue(second["deduped"])
        self.assertEqual(first["id"], second["id"])
        got = knowledge_get(self.workspace, first["id"])
        evidence = got["entry"]["evidence"]
        self.assertIn("tests/test_knowledge_base.py", evidence)
        self.assertIn("docs/KNOWLEDGE_BASE_V2.md", evidence)

    def test_supersede_mechanism(self):
        bootstrap_knowledge(self.workspace)
        old = knowledge_record(
            self.workspace,
            type="decision",
            topic="supersede-demo",
            summary="Old decision for supersede demo.",
            status="active",
            force_new=True,
        )
        new = knowledge_record(
            self.workspace,
            type="decision",
            topic="supersede-demo",
            summary="New decision replaces old supersede demo.",
            status="active",
            supersedes=old["id"],
            reason="corrected",
            force_new=True,
        )
        old_got = knowledge_get(self.workspace, old["id"])
        self.assertEqual(old_got["entry"]["status"], "superseded")
        self.assertEqual(old_got["entry"]["superseded_by"], new["id"])

    def test_secret_rejected(self):
        bootstrap_knowledge(self.workspace)
        with self.assertRaises(ToolError):
            knowledge_record(
                self.workspace,
                type="research",
                topic="secrets",
                summary="password: hunter2 must not be stored",
                force_new=True,
            )
        with self.assertRaises(ToolError):
            knowledge_search(self.workspace, "api_key=abc")

    def test_prevention_query_avoids_prompt_only(self):
        bootstrap_knowledge(self.workspace)
        search = knowledge_search(
            self.workspace,
            "Der Compact dupliziert pdf_create. Wie soll ich es reparieren?",
        )
        package = search["package"].lower()
        self.assertTrue(search["hits"])
        self.assertTrue("prompt-only" in package or "insufficient" in package or "do_not_repeat" in package)
        self.assertTrue("ledger" in package or "lazy" in package)
        # Prompt-only failure should be present and marked
        fail_hits = [h for h in search["hits"] if h["id"] == "KB-20260922-COMPACT-003"]
        if fail_hits:
            self.assertTrue(fail_hits[0].get("do_not_repeat") or fail_hits[0]["status"] == "failed")


if __name__ == "__main__":
    unittest.main()
