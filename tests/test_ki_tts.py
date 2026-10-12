from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SERVER = Path(__file__).parents[1] / "apps" / "ki-tts" / "server.py"
SPEC = importlib.util.spec_from_file_location("ki_tts_server", SERVER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TtsParseTests(unittest.TestCase):
    def test_valid_request(self):
        text, lang = MODULE.parse_synthesize({"text": "  Hallo  ", "lang": "de"})
        self.assertEqual(text, "Hallo")
        self.assertEqual(lang, "de")

    def test_empty_text_rejected(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.parse_synthesize({"text": " ", "lang": "de"})

    def test_unknown_lang_rejected(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.voice_model("xx")


if __name__ == "__main__":
    unittest.main()
