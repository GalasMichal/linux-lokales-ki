from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1] / "apps" / "open-webui-tools" / "local_image_policy.py"
SPEC = importlib.util.spec_from_file_location("local_image_policy", POLICY)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class SizeTests(unittest.TestCase):
    def test_512_original_stays_512(self):
        self.assertEqual(MODULE.snap_edit_size(512, 512), (512, 512))

    def test_small_photo_stays_512(self):
        self.assertEqual(MODULE.snap_edit_size(400, 300), (512, 512))

    def test_768_band(self):
        self.assertEqual(MODULE.snap_edit_size(768, 768), (768, 768))

    def test_1024_and_larger_cap(self):
        self.assertEqual(MODULE.snap_edit_size(1024, 1024), (1024, 1024))
        self.assertEqual(MODULE.snap_edit_size(2048, 1536), (1024, 1024))

    def test_explicit_1024_in_text(self):
        self.assertEqual(MODULE.requested_size_from_text("Bitte in 1024 Pixeln."), (1024, 1024))

    def test_model_args_ignored_without_text(self):
        self.assertIsNone(MODULE.resolve_named_size("Ändere nur den Apfel.", 1024, 1024))

    def test_omit_size(self):
        self.assertIsNone(MODULE.parse_requested_size(None, None))

    def test_invalid_size_ignored(self):
        self.assertIsNone(MODULE.parse_requested_size(333, 333))


class SourceTests(unittest.TestCase):
    def test_original_upload_preferred(self):
        files = [
            {"id": "orig", "type": "file", "content_type": "image/png", "name": "apple.png"},
            {"id": "out", "type": "image", "url": "data:image/png;base64,xx", "local_ki_output": True},
        ]
        chosen = MODULE.choose_source_file(files, "Ändere nur den Apfel zu grün.")
        self.assertEqual(chosen["source"], "original")
        self.assertEqual(chosen["file"]["id"], "orig")

    def test_nested_open_webui_file(self):
        files = [
            {
                "type": "file",
                "id": "abc",
                "file": {"id": "abc", "filename": "source.png", "meta": {"content_type": "image/png"}},
                "name": "source.png",
            }
        ]
        chosen = MODULE.choose_source_file(files, "Mach den Apfel grün.")
        self.assertEqual(chosen["source"], "original")
        self.assertEqual(chosen["file"]["id"], "abc")

    def test_thanks_does_not_change_rule(self):
        files = [{"id": "orig", "type": "file", "content_type": "image/png", "name": "apple.png"}]
        chosen = MODULE.choose_source_file(files, "Danke, das sieht gut aus.")
        self.assertEqual(chosen["source"], "original")
        self.assertTrue(MODULE.is_non_edit_ack("Danke, das sieht gut aus."))

    def test_explicit_second_edit_uses_last_job(self):
        files = [{"id": "orig", "type": "file", "content_type": "image/png", "name": "apple.png"}]
        chosen = MODULE.choose_source_file(
            files,
            "Nimm dieses Ergebnis und ändere zusätzlich den Hintergrund zu blau.",
            last_job_id="37fa72860c19",
        )
        self.assertEqual(chosen["source"], "last_job")
        self.assertEqual(chosen["job_id"], "37fa72860c19")
        self.assertFalse(
            MODULE.is_non_edit_ack("Nimm dieses Ergebnis und ändere zusätzlich den Hintergrund zu blau.")
        )

    def test_no_upload_without_explicit_result(self):
        with self.assertRaises(ValueError):
            MODULE.choose_source_file([], "Mach den Himmel blau.")

    def test_second_edit_phrases(self):
        self.assertTrue(MODULE.is_explicit_second_edit("Nimm das zuletzt erzeugte Bild"))
        self.assertFalse(MODULE.is_explicit_second_edit("Warum wirken KI-Bilder gemalt?"))

    def test_second_edit_uses_user_text_not_model_rewrite(self):
        files = [{"id": "orig", "type": "file", "content_type": "image/png", "name": "apple.png"}]
        rewritten = "Ändere den Hintergrund zu blau. Der grüne Apfel bleibt unverändert."
        user = "Nimm dieses Ergebnis und ändere zusätzlich den Hintergrund zu blau."
        chosen = MODULE.choose_source_file(files, rewritten + "\n" + user, last_job_id="abc")
        self.assertEqual(chosen["source"], "last_job")
        self.assertEqual(chosen["job_id"], "abc")

    def test_ki_result_not_auto_used(self):
        files = [{"type": "image", "url": "data:image/png;base64,xx"}]
        with self.assertRaises(ValueError):
            MODULE.choose_source_file(files, "Mach den Himmel blau.")


if __name__ == "__main__":
    unittest.main()
