from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATCH_DIR = REPO / "patches" / "qwen-code" / "0.24.2"
STOCK = Path("/srv/ai/cache/qwen-code-0.24.2/inspect/qwen-code/lib/chunks")
STOCK_TOOLSEARCH = "c883f6def29f1eb479254a540a9c3d63c6dd44d31b5aef3d8efa81b13653fabc"
PATCHED_TOOLSEARCH = "2034ea26db4eb499fc2ac4138d698597315c1ef1ac2df22ed7f8451b1ccd8cb4"
STOCK_REGISTRY = "901b95cd0105ffa0d4c90159e556885e6edca990687727278e98916d90dcc9c5"
PATCHED_REGISTRY = "2433fc7ca45bc5afc22efc91be0da87ba1f420b213d5d9e61a180e9525924035"
STOCK_GIT = "ffee7068d4e3df196ee71949d1a0c966a96a03147ffda529a7ad0777e726e017"
PATCHED_GIT = "263eaabf01768c1837bb6224f404916b63cce24d74477b7dbbbc57f60d1e7a2f"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Qwen0242PatchApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not STOCK.exists():
            raise unittest.SkipTest("Qwen 0.24.2 inspect tree missing")

    def test_isolated_apply_matches_known_shas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            ts = work / "tool-search-ANXFKRMW.js"
            reg = work / "chunk-VQUX7GWP.js"
            git = work / "chunk-IOISNXQ2.js"
            shutil.copyfile(STOCK / "tool-search-ANXFKRMW.js", ts)
            shutil.copyfile(STOCK / "chunk-VQUX7GWP.js", reg)
            shutil.copyfile(STOCK / "chunk-IOISNXQ2.js", git)
            self.assertEqual(_sha(ts), STOCK_TOOLSEARCH)
            self.assertEqual(_sha(reg), STOCK_REGISTRY)
            self.assertEqual(_sha(git), STOCK_GIT)

            import importlib.util

            def load(name: str, path: Path):
                spec = importlib.util.spec_from_file_location(name, path)
                assert spec and spec.loader
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod

            ts_mod = load("patch_toolsearch", PATCH_DIR / "patch_toolsearch.py")
            reg_mod = load("patch_registry", PATCH_DIR / "patch_registry.py")
            git_mod = load("patch_git_snapshot", PATCH_DIR / "patch_git_snapshot.py")
            self.assertEqual(ts_mod.apply_patch(ts, PATCH_DIR / "tool-search-insert.js"), "applied")
            self.assertEqual(reg_mod.apply_patch(reg), "applied")
            self.assertEqual(git_mod.apply_patch(git), "applied")
            self.assertEqual(ts_mod.apply_patch(ts, PATCH_DIR / "tool-search-insert.js"), "already")
            self.assertEqual(reg_mod.apply_patch(reg), "already")
            self.assertEqual(git_mod.apply_patch(git), "already")
            self.assertEqual(_sha(ts), PATCHED_TOOLSEARCH)
            self.assertEqual(_sha(reg), PATCHED_REGISTRY)
            self.assertEqual(_sha(git), PATCHED_GIT)
            self.assertIn("resolveSelectToolName(", ts.read_text(encoding="utf-8"))
            self.assertIn("resolveMcpShortToolName(", reg.read_text(encoding="utf-8"))
            self.assertIn("linux-lokales-ki-omit-git-snapshot", git.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
