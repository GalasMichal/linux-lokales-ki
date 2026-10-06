from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

PATCH = Path(__file__).resolve().parents[1] / "patches/qwen-code/0.23.4/patch_git_snapshot.py"
SPEC = importlib.util.spec_from_file_location("patch_git_snapshot", PATCH)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

SAMPLE = """function getRecentGitStatus(cwd) {
  if (!isGitRepository(cwd)) return null;
  try {
    const log = "abc";
    return ["Git snapshot", "Recent commits:"];
  } catch (error) {}
}
"""


class GitSnapshotPatchTests(unittest.TestCase):
    def test_early_null_return(self):
        out = MOD.apply_text(SAMPLE)
        self.assertIn(MOD.MARKER, out)
        head = out.split("try {", 1)[0]
        self.assertIn("return null;", head)
        self.assertIn(MOD.MARKER, head)

    def test_idempotent(self):
        once = MOD.apply_text(SAMPLE)
        twice = MOD.apply_text(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
