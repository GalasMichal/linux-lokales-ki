from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

PATCH_DIR = Path(__file__).resolve().parents[1] / "patches" / "qwen-code" / "0.23.4"
SPEC = importlib.util.spec_from_file_location(
    "resolve_select_tool_name",
    PATCH_DIR / "resolve_select_tool_name.py",
)
assert SPEC and SPEC.loader
RESOLVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESOLVE)

REGISTRY = [
    "read_file",
    "write_file",
    "tool_search",
    "mcp__local-tools__generate_image",
]

VISIBLE = [
    "read_file",
    "write_file",
    "tool_search",
    "mcp__local-tools__generate_image",
]
DEFERRED = ["zoom_image", "record_artifact", "web_fetch"]
ALL_NAMES = VISIBLE + DEFERRED


class ExactMatchTests(unittest.TestCase):
    def test_normal_builtin_read_file(self):
        result = RESOLVE.resolve_select_tool_name("read_file", REGISTRY)
        self.assertEqual(result, {"status": "ok", "name": "read_file"})

    def test_read_file_case_insensitive(self):
        result = RESOLVE.resolve_select_tool_name("Read_File", REGISTRY)
        self.assertEqual(result["name"], "read_file")


class McpMatchTests(unittest.TestCase):
    def test_full_mcp_name(self):
        result = RESOLVE.resolve_select_tool_name(
            "mcp__local-tools__generate_image", REGISTRY
        )
        self.assertEqual(result, {"status": "ok", "name": "mcp__local-tools__generate_image"})

    def test_unique_mcp_short_alias(self):
        result = RESOLVE.resolve_select_tool_name("generate_image", REGISTRY)
        self.assertEqual(result, {"status": "ok", "name": "mcp__local-tools__generate_image"})

    def test_short_alias_does_not_use_generic_suffix(self):
        names = REGISTRY + ["read_file_backup"]
        result = RESOLVE.resolve_select_tool_name("file", names)
        self.assertEqual(result["status"], "missing")


class AmbiguousAndUnknownTests(unittest.TestCase):
    def test_ambiguous_mcp_short_alias(self):
        names = [
            "mcp__server-a__generate_image",
            "mcp__server-b__generate_image",
            "read_file",
        ]
        result = RESOLVE.resolve_select_tool_name("generate_image", names)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(
            result["candidates"],
            [
                "mcp__server-a__generate_image",
                "mcp__server-b__generate_image",
            ],
        )
        message = RESOLVE.format_ambiguous(result)
        self.assertIn("mcp__server-a__generate_image", message)
        self.assertIn("mcp__server-b__generate_image", message)
        self.assertTrue(message.startswith('Ambiguous tool name "generate_image"'))

    def test_unknown_tool(self):
        result = RESOLVE.resolve_select_tool_name("no_such_tool", REGISTRY)
        self.assertEqual(result["status"], "missing")
        self.assertEqual(
            RESOLVE.format_not_found([result["requested"]]),
            "Not found: no_such_tool",
        )


class CurrentExactOnlyBehaviorTests(unittest.TestCase):
    """Documents Qwen 0.23.4 stock select: matching (exact only)."""

    def test_stock_select_generate_image_fails(self):
        lower = {name.lower(): name for name in REGISTRY}
        canonical = lower.get("generate_image")
        self.assertIsNone(canonical)

    def test_stock_select_full_mcp_passes(self):
        lower = {name.lower(): name for name in REGISTRY}
        self.assertEqual(
            lower.get("mcp__local-tools__generate_image"),
            "mcp__local-tools__generate_image",
        )

    def test_stock_select_read_file_passes(self):
        lower = {name.lower(): name for name in REGISTRY}
        self.assertEqual(lower.get("read_file"), "read_file")


class ExactWinsOverAliasTests(unittest.TestCase):
    def test_builtin_same_short_name_wins(self):
        names = ["generate_image", "mcp__local-tools__generate_image"]
        result = RESOLVE.resolve_select_tool_name("generate_image", names)
        self.assertEqual(result["name"], "generate_image")


class KeywordVisibleMcpTests(unittest.TestCase):
    def test_deferred_zoom_image_still_matches_image(self):
        ranked = RESOLVE.rank_keyword_tools("image", ALL_NAMES, DEFERRED)
        self.assertIn("zoom_image", ranked)

    def test_visible_mcp_image(self):
        ranked = RESOLVE.rank_keyword_tools("image", ALL_NAMES, DEFERRED)
        self.assertIn("mcp__local-tools__generate_image", ranked)

    def test_visible_mcp_generate(self):
        ranked = RESOLVE.rank_keyword_tools("generate", ALL_NAMES, DEFERRED)
        self.assertIn("mcp__local-tools__generate_image", ranked)

    def test_visible_mcp_generate_image(self):
        ranked = RESOLVE.rank_keyword_tools("generate_image", ALL_NAMES, DEFERRED)
        self.assertIn("mcp__local-tools__generate_image", ranked)

    def test_unrelated_database_skips_image_tool(self):
        ranked = RESOLVE.rank_keyword_tools("database", ALL_NAMES, DEFERRED)
        self.assertNotIn("mcp__local-tools__generate_image", ranked)

    def test_visible_builtin_not_added_for_file(self):
        ranked = RESOLVE.rank_keyword_tools("file", ALL_NAMES, DEFERRED)
        self.assertNotIn("read_file", ranked)
        self.assertNotIn("write_file", ranked)
        self.assertNotIn("mcp__local-tools__generate_image", ranked)

    def test_two_visible_mcp_image_keeps_full_names(self):
        names = VISIBLE + [
            "mcp__server-a__generate_image",
            "mcp__server-b__search_image",
        ]
        ranked = RESOLVE.rank_keyword_tools("image", names, [])
        self.assertIn("mcp__local-tools__generate_image", ranked)
        self.assertIn("mcp__server-a__generate_image", ranked)
        self.assertIn("mcp__server-b__search_image", ranked)

    def test_candidates_exclude_visible_builtins(self):
        candidates = RESOLVE.collect_keyword_candidate_names(ALL_NAMES, DEFERRED)
        self.assertNotIn("read_file", candidates)
        self.assertIn("zoom_image", candidates)
        self.assertIn("mcp__local-tools__generate_image", candidates)


if __name__ == "__main__":
    unittest.main()
