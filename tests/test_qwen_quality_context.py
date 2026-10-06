from __future__ import annotations

import json
import unittest
from pathlib import Path
import importlib.util

SETTER = Path(__file__).resolve().parents[1] / "scripts/set-qwen-quality-context.py"
SPEC = importlib.util.spec_from_file_location("set_qwen_quality_context", SETTER)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

SAMPLE = {
    "modelProviders": {
        "openai": [
            {
                "id": "local-quality",
                "generationConfig": {"timeout": 300000, "contextWindowSize": 8192},
            },
            {
                "id": "local-fast",
                "generationConfig": {"timeout": 180000, "contextWindowSize": 32768},
            },
        ]
    },
    "model": {"name": "local-quality"},
    "tools": {"approvalMode": "default"},
    "mcpServers": {"local-tools": {"trust": False}},
}


class QualityContextSetterTests(unittest.TestCase):
    def test_pins_compact_settings_and_default_fast(self):
        out = MOD.apply(json.loads(json.dumps(SAMPLE)), 16384)
        self.assertEqual(out["model"]["name"], "local-fast")
        self.assertEqual(out["compactionModel"], "local-fast")
        self.assertEqual(out["context"]["autoCompactThreshold"], 0.95)
        quality = None
        for provider in out["modelProviders"]["openai"]:
            if provider["id"] == "local-quality":
                quality = provider["generationConfig"]["contextWindowSize"]
        self.assertEqual(quality, 16384)

    def test_rejects_fast_drift(self):
        bad = json.loads(json.dumps(SAMPLE))
        bad["modelProviders"]["openai"][1]["generationConfig"]["contextWindowSize"] = 16384
        with self.assertRaises(SystemExit):
            MOD.apply(bad, 16384)


if __name__ == "__main__":
    unittest.main()
