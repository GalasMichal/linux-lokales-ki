from __future__ import annotations

import json
import unittest
from pathlib import Path

import importlib.util

SETTER = Path(__file__).resolve().parents[1] / "scripts/set-qwen-fast-context.py"
SPEC = importlib.util.spec_from_file_location("set_qwen_fast_context", SETTER)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

MODELFILE = Path(__file__).resolve().parents[1] / "config/modelfiles/local-fast.Modelfile"
MODELFILE_16K = Path(__file__).resolve().parents[1] / "config/modelfiles/local-fast.Modelfile.16k"

SAMPLE = {
    "modelProviders": {
        "openai": [
            {
                "id": "local-quality",
                "generationConfig": {"timeout": 300000, "contextWindowSize": 8192},
            },
            {
                "id": "local-fast",
                "generationConfig": {"timeout": 180000, "contextWindowSize": 16384},
            },
        ]
    },
    "model": {"name": "local-fast"},
    "mcpServers": {"local-tools": {"trust": False, "includeTools": ["generate_image"]}},
}


class FastContextSetterTests(unittest.TestCase):
    def test_sets_only_fast(self):
        out = MOD.set_fast_context(json.loads(json.dumps(SAMPLE)), 32768)
        fast, quality = MOD.read_fast_quality(out)
        self.assertEqual(fast, 32768)
        self.assertEqual(quality, 8192)
        self.assertEqual(out["model"]["name"], "local-fast")
        self.assertIs(out["mcpServers"]["local-tools"]["trust"], False)

    def test_rejects_quality_drift(self):
        bad = json.loads(json.dumps(SAMPLE))
        bad["modelProviders"]["openai"][0]["generationConfig"]["contextWindowSize"] = 16384
        with self.assertRaises(SystemExit):
            MOD.set_fast_context(bad, 32768)


class FastModelfileTests(unittest.TestCase):
    def test_32k_parent_and_ctx(self):
        text = MODELFILE.read_text(encoding="utf-8")
        self.assertIn("FROM qwen3.5:9b\n", text)
        self.assertIn("PARAMETER num_ctx 32768\n", text)
        self.assertNotIn("num_ctx 16384", text)

    def test_16k_rollback_file(self):
        text = MODELFILE_16K.read_text(encoding="utf-8")
        self.assertIn("FROM qwen3.5:9b\n", text)
        self.assertIn("PARAMETER num_ctx 16384\n", text)


if __name__ == "__main__":
    unittest.main()
