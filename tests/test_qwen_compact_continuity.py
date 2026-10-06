#!/usr/bin/env python3
"""Patch-file tests for the Qwen 0.24.2 compact-continuity prompt."""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATCHER = REPO / "patches" / "qwen-code" / "0.24.2" / "patch_compact_continuity.py"
LIVE_PROMPT = Path("/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-CXXHL3XJ.js")
LIVE_TRAILER = Path("/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-VQUX7GWP.js")
PROMPT_STOCK_SHA = "859c4a89149f02e271f73039bf4aa4d31eead0e08dd333d3a17f790bd754986c"
REGISTRY_MARKER = "resolveMcpShortToolName("
GIT_MARKER = "linux-lokales-ki-omit-git-snapshot"
TOOLSEARCH = Path("/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/tool-search-ANXFKRMW.js")
GIT = Path("/srv/ai/apps/qwen-code/lib/qwen-code/lib/chunks/chunk-IOISNXQ2.js")


def _load():
    spec = importlib.util.spec_from_file_location("patch_compact_continuity", PATCHER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompactContinuityPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not LIVE_PROMPT.is_file() or not LIVE_TRAILER.is_file():
            raise unittest.SkipTest("Qwen 0.24.2 chunks missing")
        cls.mod = _load()

    def test_patch_stock_known_base(self) -> None:
        self.assertEqual(_sha(LIVE_PROMPT), PROMPT_STOCK_SHA)
        self.assertIn(REGISTRY_MARKER, LIVE_TRAILER.read_text(encoding="utf-8"))
        self.assertNotIn(self.mod.MARKER, LIVE_PROMPT.read_text(encoding="utf-8"))

    def test_patch_apply_idempotent_check_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "chunk-CXXHL3XJ.js"
            trailer = Path(tmp) / "chunk-VQUX7GWP.js"
            shutil.copyfile(LIVE_PROMPT, prompt)
            shutil.copyfile(LIVE_TRAILER, trailer)
            self.assertEqual(self.mod.apply_prompt_text(prompt.read_text(encoding="utf-8")) != prompt.read_text(encoding="utf-8"), True)
            prompt.write_text(self.mod.apply_prompt_text(prompt.read_text(encoding="utf-8")), encoding="utf-8")
            trailer.write_text(self.mod.apply_trailer_text(trailer.read_text(encoding="utf-8")), encoding="utf-8")
            patched_prompt = prompt.read_text(encoding="utf-8")
            patched_trailer = trailer.read_text(encoding="utf-8")
            self.assertIn("<completed_tool_calls>", patched_prompt)
            self.assertIn("explicitly asked to run the tool again", patched_prompt)
            self.assertIn(self.mod.MARKER, patched_prompt)
            self.assertIn("do not repeat a tool listed under completed_tool_calls", patched_trailer.lower())
            self.assertIn(REGISTRY_MARKER, patched_trailer)
            self.assertEqual(self.mod.apply_prompt_text(patched_prompt), patched_prompt)
            self.assertEqual(self.mod.apply_trailer_text(patched_trailer), patched_trailer)
            prompt.write_text(self.mod.rollback_prompt_text(patched_prompt), encoding="utf-8")
            trailer.write_text(self.mod.rollback_trailer_text(patched_trailer), encoding="utf-8")
            self.assertEqual(_sha(prompt), PROMPT_STOCK_SHA)
            self.assertIn(REGISTRY_MARKER, trailer.read_text(encoding="utf-8"))
            self.assertNotIn(self.mod.MARKER, trailer.read_text(encoding="utf-8"))
            self.assertNotIn(self.mod.MARKER, prompt.read_text(encoding="utf-8"))

    def test_patch_unknown_sha_aborts(self) -> None:
        broken = LIVE_PROMPT.read_text(encoding="utf-8").replace("    <next_step>\n", "    <next_step_missing>\n", 1)
        with self.assertRaises(SystemExit):
            self.mod.apply_prompt_text(broken)

    def test_other_patches_not_required_to_change(self) -> None:
        self.assertIn("resolveSelectToolName(", TOOLSEARCH.read_text(encoding="utf-8"))
        self.assertIn(GIT_MARKER, GIT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
