from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS_DIR = Path(__file__).resolve().parents[1] / "apps" / "local-tools"
sys.path.insert(0, str(TOOLS_DIR))

GATEWAY_FILE = TOOLS_DIR / "gateway.py"
SPEC = importlib.util.spec_from_file_location("local_tools_gateway", GATEWAY_FILE)
assert SPEC and SPEC.loader
GATEWAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATEWAY)


class ImageInputTests(unittest.TestCase):
    def test_valid_request_is_normalized(self):
        result = GATEWAY.parse_generate_image("  rote Katze  ", 1024, 768, 42, GATEWAY.WORKFLOW_ID)
        self.assertEqual(result["prompt"], "rote Katze")
        self.assertEqual(result["workflow_id"], "flux2-klein-t2i-v1")

    def test_unknown_workflow_is_rejected(self):
        with self.assertRaises(GATEWAY.ToolError):
            GATEWAY.parse_generate_image("Katze", 1024, 1024, 42, "anderer-workflow")

    def test_unknown_size_is_rejected(self):
        with self.assertRaises(GATEWAY.ToolError):
            GATEWAY.parse_generate_image("Katze", 2048, 1024, 42, GATEWAY.WORKFLOW_ID)

    def test_boolean_seed_is_rejected(self):
        with self.assertRaises(GATEWAY.ToolError):
            GATEWAY.parse_generate_image("Katze", 512, 512, True, GATEWAY.WORKFLOW_ID)

    def test_numeric_string_seed_is_accepted(self):
        result = GATEWAY.parse_generate_image("Katze", 512, 512, "20260821", GATEWAY.WORKFLOW_ID)
        self.assertEqual(result["seed"], 20260821)
        self.assertEqual(result["width"], 512)

    def test_seed_zero_is_accepted(self):
        result = GATEWAY.parse_generate_image("Katze", 512, 512, 0, GATEWAY.WORKFLOW_ID)
        self.assertEqual(result["seed"], 0)
        self.assertEqual(result["width"], 512)


class _Response:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, _: int):
        return self.payload


class WorkplaceAdapterTests(unittest.TestCase):
    def test_only_validated_fields_are_forwarded(self):
        observed = {"calls": []}

        def fake_urlopen(request, timeout):
            observed["calls"].append(
                {"url": request.full_url, "payload": json.loads(request.data), "timeout": timeout}
            )
            if request.full_url.endswith("/api/gpu/cleanup"):
                return _Response({"ok": True, "gpu": {"free_mib": 15000}})
            return _Response({"ok": True, "job_id": "abc", "outputs": ["/archive/image.png"]})

        with patch.object(GATEWAY, "urlopen", fake_urlopen):
            result = asyncio.run(
                GATEWAY.generate_image_via_workplace(
                    "Katze",
                    512,
                    768,
                    7,
                    GATEWAY.WORKFLOW_ID,
                )
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["gpu_cleanup"]["ok"])
        self.assertEqual(observed["calls"][0]["url"], "http://127.0.0.1:8790/api/images/generate")
        self.assertEqual(
            observed["calls"][0]["payload"],
            {"prompt": "Katze", "width": 512, "height": 768, "seed": 7},
        )
        self.assertEqual(observed["calls"][0]["timeout"], 300)
        self.assertEqual(observed["calls"][1]["url"], "http://127.0.0.1:8790/api/gpu/cleanup")
        self.assertEqual(observed["calls"][1]["payload"], {})


class EditImageInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path("/tmp/ki-edit-gateway-test")
        self.tmp.mkdir(exist_ok=True)
        self.png = self.tmp / "input.png"
        self.png.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def tearDown(self):
        if self.png.exists():
            self.png.unlink()
        if self.tmp.exists():
            self.tmp.rmdir()

    def test_valid_edit_is_normalized(self):
        result = GATEWAY.parse_edit_image("  gruen  ", str(self.png), [], 1024, 1024, 42, False)
        self.assertEqual(result["instruction"], "gruen")
        self.assertEqual(result["width"], 1024)
        self.assertFalse(result["preserve_alpha"])
        self.assertNotIn("workflow_id", result)

    def test_path_outside_roots_is_rejected(self):
        with self.assertRaises(GATEWAY.ToolError):
            GATEWAY.parse_edit_image("x", "/etc/hostname")

    def test_url_is_rejected(self):
        with self.assertRaises(GATEWAY.ToolError):
            GATEWAY.parse_edit_image("x", "https://example.invalid/a.png")

    def test_too_many_references(self):
        with self.assertRaises(GATEWAY.ToolError):
            GATEWAY.parse_edit_image("x", str(self.png), [str(self.png), str(self.png), str(self.png)])


class EditWorkplaceAdapterTests(unittest.TestCase):
    def test_only_validated_edit_fields_are_forwarded(self):
        observed = {"calls": []}

        def fake_urlopen(request, timeout):
            observed["calls"].append(
                {"url": request.full_url, "payload": json.loads(request.data), "timeout": timeout}
            )
            return _Response(
                {
                    "ok": True,
                    "job_id": "edit1",
                    "output_path": "/mnt/ai-archive/images/inbox/x/out.png",
                    "manifest_path": "/mnt/ai-archive/images/inbox/x/manifest.json",
                    "workflow_id": "qwen-image-21-edit-v1",
                }
            )

        png = Path("/tmp/ki-edit-gateway-test2.png")
        png.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        try:
            with patch.object(GATEWAY, "urlopen", fake_urlopen):
                result = asyncio.run(
                    GATEWAY.edit_image_via_workplace("mach gruen", str(png), [], 1024, 1024, 9, False)
                )
        finally:
            png.unlink(missing_ok=True)

        self.assertTrue(result["ok"])
        self.assertEqual(len(observed["calls"]), 1)
        self.assertEqual(observed["calls"][0]["url"], "http://127.0.0.1:8790/api/images/edit")
        payload = observed["calls"][0]["payload"]
        self.assertEqual(payload["instruction"], "mach gruen")
        self.assertEqual(payload["seed"], 9)
        self.assertNotIn("workflow_id", payload)
        self.assertEqual(observed["calls"][0]["timeout"], 480)


if __name__ == "__main__":
    unittest.main()
