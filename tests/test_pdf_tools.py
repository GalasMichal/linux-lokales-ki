from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "apps" / "local-tools"
sys.path.insert(0, str(TOOLS_DIR))

from errors import ToolError  # noqa: E402
from pdf_tools import (  # noqa: E402
    capabilities,
    make_image_only_pdf,
    pdf_create,
    pdf_edit,
    pdf_inspect,
    pdf_merge,
    pdf_ocr,
    pdf_read,
    pdf_render,
    pdf_split,
    qa_pdf,
)


class PdfToolSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="local-ai-pdf-")
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_read_inspect_render_merge_split_edit_ocr(self):
        first = self.dir / "one.pdf"
        second = self.dir / "two.pdf"
        created = pdf_create(
            str(first),
            text="Alpha document.\nLine two for the smoke test.",
            title="Alpha",
        )
        self.assertTrue(created["ok"])
        self.assertTrue(created["qa"]["ok"])
        self.assertGreaterEqual(created["qa"]["pages"], 1)
        self.assertGreater(created["qa"]["text_chars"], 10)
        self.assertTrue(Path(created["qa"]["render_path"]).is_file())
        self.assertTrue(created["qa"]["vision"]["ready"])

        pdf_create(str(second), text="Beta document.\nSecond file.", title="Beta")

        inspected = pdf_inspect(str(first))
        self.assertTrue(inspected["ok"])
        self.assertGreaterEqual(inspected["pages"], 1)
        self.assertTrue(inspected["page_info"][0]["has_text"])

        read = pdf_read(str(first))
        self.assertTrue(read["ok"])
        self.assertIn("Alpha document", read["text"])

        rendered = pdf_render(str(first), str(self.dir / "page1.png"), page=1)
        self.assertTrue(rendered["ok"])
        self.assertTrue(Path(rendered["path"]).is_file())
        self.assertGreater(os.path.getsize(rendered["path"]), 100)

        merged_path = self.dir / "merged.pdf"
        merged = pdf_merge(f"{first},{second}", str(merged_path))
        self.assertTrue(merged["ok"])
        self.assertGreaterEqual(merged["qa"]["pages"], 2)
        self.assertIn("Alpha", merged["qa"]["text_preview"])
        self.assertIn("Beta", merged["qa"]["text_preview"])

        split_dir = self.dir / "split"
        split = pdf_split(str(merged_path), str(split_dir), pages="1")
        self.assertTrue(split["ok"])
        self.assertEqual(split["count"], 1)
        split_read = pdf_read(split["outputs"][0])
        self.assertIn("Alpha", split_read["text"])
        self.assertNotIn("Beta document", split_read["text"])

        each = pdf_split(str(merged_path), str(self.dir / "pages"))
        self.assertGreaterEqual(each["count"], 2)

        edited_path = self.dir / "edited.pdf"
        edited = pdf_edit(
            str(first),
            str(edited_path),
            replacements="Alpha=>Gamma",
            mode="replace",
        )
        self.assertTrue(edited["ok"])
        self.assertTrue(edited["qa"]["ok"])
        edited_text = pdf_read(str(edited_path))["text"]
        self.assertIn("Gamma", edited_text)

        rewritten = pdf_edit(
            str(first),
            str(self.dir / "rewritten.pdf"),
            new_text="Completely new body after a large rewrite.",
            mode="recreate",
        )
        self.assertTrue(rewritten["ok"])
        self.assertTrue(rewritten["qa"]["ok"])
        self.assertEqual(rewritten["mode"], "recreate-text")
        self.assertIn("Completely new body", pdf_read(str(self.dir / "rewritten.pdf"))["text"])

        image_pdf = self.dir / "scan.pdf"
        make_image_only_pdf(str(first), str(image_pdf))
        ocr_out = self.dir / "ocr.pdf"
        ocr = pdf_ocr(str(image_pdf), str(ocr_out), languages="eng")
        self.assertTrue(ocr.get("callable", True))
        self.assertIn("backend", ocr)
        if ocr.get("ok"):
            self.assertTrue(Path(ocr_out).is_file())
            self.assertTrue(ocr["qa"]["ok"])
            self.assertGreaterEqual(ocr["qa"]["pages"], 1)
        else:
            self.fail(f"OCR pipeline was callable but failed: {ocr}")

        qa = qa_pdf(str(merged_path))
        self.assertTrue(qa["ok"])
        self.assertGreaterEqual(qa["pages"], 2)

    def test_capabilities_include_local_backends(self):
        caps = capabilities()
        self.assertTrue(caps["python"]["pymupdf"])
        self.assertTrue(caps["python"]["pikepdf"])
        self.assertTrue(caps["python"]["reportlab"])
        self.assertTrue(caps["binaries"]["tesseract"])
        self.assertTrue(caps["binaries"]["ocrmypdf"])

    def test_rejects_path_outside_allowed_roots(self):
        with self.assertRaises(ToolError):
            pdf_inspect("/etc/passwd")


if __name__ == "__main__":
    unittest.main()
