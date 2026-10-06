from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "apps" / "local-tools"
sys.path.insert(0, str(TOOLS_DIR))

from errors import ToolError  # noqa: E402
from pdf_tools import ensure_pdf_imports  # noqa: E402
from pdf_vision import pdf_vision_qa, validate_page_payload  # noqa: E402


def _make_pdf(dest: Path, kind: str) -> Path:
    ensure_pdf_imports()
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    if kind == "clean":
        page.insert_text((50, 72), "Invoice 2026-09-15", fontsize=18)
        body = (
            "This page has a normal left margin, readable 11pt body text, and even spacing. "
            "Paragraph two continues with enough content so the page is not empty. "
            "A short table of contents line sits inside the printable area."
        )
        page.insert_textbox(pymupdf.Rect(50, 100, 545, 760), body, fontsize=11)
    elif kind == "clipped":
        page.insert_text((-80, 200), "CLIPPED_LEFT this heading is cut by the page edge", fontsize=16)
        page.insert_text((520, 400), "OVERFLOW_RIGHT continues past the margin", fontsize=16)
    elif kind == "overlap":
        page.insert_text((80, 280), "OVERLAP_A large heading sitting on top", fontsize=22)
        page.insert_text((95, 286), "OVERLAP_B second heading covering the first", fontsize=22)
        page.insert_text((80, 300), "OVERLAP_C third line colliding with both", fontsize=22)
    elif kind == "blank":
        pass
    elif kind == "table":
        for col in range(10):
            x0 = 40 + col * 90
            page.draw_rect(pymupdf.Rect(x0, 80, x0 + 85, 320), color=(0, 0, 0), width=0.8)
            page.insert_text((x0 + 4, 100), f"COL{col}_OFF_PAGE", fontsize=9)
    else:
        raise AssertionError(kind)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)
    doc.close()
    return dest


def _chat_from_map(mapping: dict[int, dict]):
    def _chat(png: Path) -> dict:
        stem = png.stem
        page = 1
        if ".vision-p" in stem:
            page = int(stem.rsplit("p", 1)[-1])
        payload = mapping[page]
        return {"content": __import__("json").dumps(payload), "prompt_eval_count": 10, "eval_count": 5}

    return _chat


class SchemaTests(unittest.TestCase):
    def test_valid_issue(self):
        checked = validate_page_payload(
            {
                "summary": "clipped heading",
                "issues": [
                    {
                        "type": "clipped_text",
                        "severity": "high",
                        "description": "Left heading is cut off.",
                        "confidence": 0.9,
                    }
                ],
            },
            page=2,
        )
        self.assertEqual(checked["issues"][0]["page"], 2)
        self.assertEqual(checked["issues"][0]["type"], "clipped_text")

    def test_confidence_percent_normalized(self):
        checked = validate_page_payload(
            {
                "summary": "ok",
                "issues": [
                    {
                        "type": "empty_page",
                        "severity": "high",
                        "description": "blank",
                        "confidence": 95,
                    }
                ],
            },
            page=1,
        )
        self.assertAlmostEqual(checked["issues"][0]["confidence"], 0.95)
        with self.assertRaises(ToolError):
            validate_page_payload(
                {
                    "summary": "x",
                    "issues": [
                        {
                            "type": "grammar",
                            "severity": "high",
                            "description": "nope",
                            "confidence": 0.5,
                        }
                    ],
                },
                page=1,
            )

    def test_invalid_json_is_not_pass(self):
        tmp = tempfile.TemporaryDirectory(prefix="vision-schema-")
        self.addCleanup(tmp.cleanup)
        pdf = _make_pdf(Path(tmp.name) / "clean.pdf", "clean")

        def bad_chat(_png: Path) -> dict:
            return {"content": "not json at all"}

        result = pdf_vision_qa(str(pdf), pages="1", chat_fn=bad_chat)
        self.assertFalse(result["ok"])
        self.assertTrue(result["invalid_output"])
        self.assertTrue(result["needs_regeneration"])
        self.assertEqual(result["issues"][0]["type"], "other")
        self.assertEqual(result["issues"][0]["severity"], "high")


class MockedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vision-fix-")
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_ok(self):
        pdf = _make_pdf(self.dir / "clean.pdf", "clean")
        result = pdf_vision_qa(
            str(pdf),
            pages="1",
            chat_fn=_chat_from_map({1: {"summary": "clean readable page", "issues": []}}),
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["needs_regeneration"])
        self.assertEqual(result["pages_checked"], [1])
        self.assertEqual(result["issues"], [])

    def test_clipped_fails(self):
        pdf = _make_pdf(self.dir / "clip.pdf", "clipped")
        result = pdf_vision_qa(
            str(pdf),
            pages="1",
            chat_fn=_chat_from_map(
                {
                    1: {
                        "summary": "text cut off",
                        "issues": [
                            {
                                "type": "clipped_text",
                                "severity": "high",
                                "description": "Heading clipped on the left.",
                                "confidence": 0.95,
                            }
                        ],
                    }
                }
            ),
        )
        self.assertFalse(result["ok"])
        self.assertIn(result["issues"][0]["type"], {"clipped_text", "overflow"})

    def test_overlap(self):
        pdf = _make_pdf(self.dir / "overlap.pdf", "overlap")
        result = pdf_vision_qa(
            str(pdf),
            pages="1",
            chat_fn=_chat_from_map(
                {
                    1: {
                        "summary": "overlapping headings",
                        "issues": [
                            {
                                "type": "overlap",
                                "severity": "high",
                                "description": "Two headings occupy the same space.",
                                "confidence": 0.9,
                            }
                        ],
                    }
                }
            ),
        )
        self.assertEqual(result["issues"][0]["type"], "overlap")
        self.assertFalse(result["ok"])

    def test_blank_empty_page(self):
        pdf = _make_pdf(self.dir / "blank.pdf", "blank")
        result = pdf_vision_qa(
            str(pdf),
            pages="1",
            chat_fn=_chat_from_map(
                {
                    1: {
                        "summary": "The page is completely blank.",
                        "issues": [],
                    }
                }
            ),
        )
        self.assertEqual(result["issues"][0]["type"], "empty_page")
        self.assertFalse(result["ok"])

    def test_table_overflow(self):
        pdf = _make_pdf(self.dir / "table.pdf", "table")
        result = pdf_vision_qa(
            str(pdf),
            pages="1",
            chat_fn=_chat_from_map(
                {
                    1: {
                        "summary": "table runs off the page",
                        "issues": [
                            {
                                "type": "broken_table",
                                "severity": "high",
                                "description": "Columns extend past the right edge.",
                                "confidence": 0.88,
                            }
                        ],
                    }
                }
            ),
        )
        self.assertIn(result["issues"][0]["type"], {"broken_table", "overflow"})
        self.assertFalse(result["ok"])

    def test_png_path_accepted(self):
        pdf = _make_pdf(self.dir / "clean.pdf", "clean")
        from pdf_tools import pdf_render

        png = self.dir / "page.png"
        pdf_render(str(pdf), str(png), page=1)
        result = pdf_vision_qa(
            str(png),
            chat_fn=_chat_from_map({1: {"summary": "ok", "issues": []}}),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], str(png.resolve()))


class LiveVisionTests(unittest.TestCase):
    """Hits local-quality over Ollama. Probabilistic: match category families, not wording."""

    @classmethod
    def setUpClass(cls):
        import urllib.request

        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=3).read()
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"Ollama nicht erreichbar: {exc}") from exc

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vision-live-")
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, kind: str) -> dict:
        pdf = _make_pdf(self.dir / f"{kind}.pdf", kind)
        return pdf_vision_qa(str(pdf), pages="1")

    def test_live_clean_has_no_high(self):
        result = self._run("clean")
        self.assertFalse(result["invalid_output"])
        highs = [item for item in result["issues"] if item["severity"] == "high"]
        self.assertEqual(highs, [], result["summary"])
        self.assertTrue(result["ok"], result)

    def test_live_clipped(self):
        result = self._run("clipped")
        self.assertFalse(result["invalid_output"])
        types = {item["type"] for item in result["issues"]}
        self.assertTrue(types & {"clipped_text", "overflow"}, result)

    def test_live_overlap(self):
        result = self._run("overlap")
        self.assertFalse(result["invalid_output"])
        types = {item["type"] for item in result["issues"]}
        self.assertTrue(types & {"overlap", "bad_spacing", "bad_alignment"}, result)

    def test_live_blank(self):
        result = self._run("blank")
        self.assertFalse(result["invalid_output"])
        types = {item["type"] for item in result["issues"]}
        self.assertIn("empty_page", types, result)

    def test_live_table(self):
        result = self._run("table")
        self.assertFalse(result["invalid_output"])
        types = {item["type"] for item in result["issues"]}
        self.assertTrue(types & {"broken_table", "overflow", "clipped_text"}, result)


if __name__ == "__main__":
    unittest.main()
