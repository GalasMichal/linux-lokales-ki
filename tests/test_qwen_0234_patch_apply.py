from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATCH_DIR = REPO / "patches" / "qwen-code" / "0.23.4"
STOCK = Path("/srv/ai/cache/qwen-code-0.23.4/inspect/qwen-code/lib/chunks")
STOCK_TOOLSEARCH = "0a4102a6c626f09c42c76227e49893f2769523876704029261fc277120a92378"
PATCHED_TOOLSEARCH = "dcdf42c5a9eae6886f21967634818b94c70f98aeab036d0eb870d061d14418f6"
STOCK_REGISTRY = "951396560a737fcbfbfb05dfa3f83efd6b309cb80072cf0d5d303d480c5a8e58"
PATCHED_REGISTRY = "ac82a673836a95776588c3bbe155b75e0bcb630c3ce5e1ca1e4ab8ca9bd7bc46"
STOCK_GIT = "6a4773e4bf518a029d88fc2d89d8911155be26a58f8af5ffc4ee188ccf84736e"
PATCHED_GIT = "aad7c86aa166989ca6da1be6e0c0a9c66ffb9a92e31089cb642782262ce11da2"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Qwen0234PatchApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not STOCK.exists():
            raise unittest.SkipTest("Qwen 0.23.4 inspect tree missing")

    def test_isolated_apply_matches_known_shas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            ts = work / "tool-search-XCEN7VXX.js"
            reg = work / "chunk-DCRVSIK6.js"
            git = work / "chunk-NXUZFW3G.js"
            shutil.copyfile(STOCK / "tool-search-XCEN7VXX.js", ts)
            shutil.copyfile(STOCK / "chunk-DCRVSIK6.js", reg)
            shutil.copyfile(STOCK / "chunk-NXUZFW3G.js", git)
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
