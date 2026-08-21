from __future__ import annotations

import asyncio
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


GATEWAY_FILE = Path(__file__).parents[1] / "apps" / "local-tools" / "gateway.py"
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


if __name__ == "__main__":
    unittest.main()
