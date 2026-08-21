from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SERVER = Path(__file__).parents[1] / "apps" / "ki-workplace" / "server.py"
SPEC = importlib.util.spec_from_file_location("ki_workplace_server", SERVER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ImageRequestTests(unittest.TestCase):
    def test_valid_request(self):
        parsed = MODULE.parse_image_request(
            {"prompt": "  eine rote Katze  ", "width": 1024, "height": 768, "seed": 42}
        )
        self.assertEqual(parsed["prompt"], "eine rote Katze")
        self.assertEqual(parsed["width"], 1024)

    def test_empty_prompt_is_rejected(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.parse_image_request({"prompt": " ", "width": 1024, "height": 1024, "seed": 42})

    def test_unknown_resolution_is_rejected(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.parse_image_request({"prompt": "x", "width": 2048, "height": 1024, "seed": 42})

    def test_negative_seed_is_rejected(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.parse_image_request({"prompt": "x", "width": 512, "height": 512, "seed": -1})


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        workflow_file = SERVER.parent / "workflows" / "flux2-klein-t2i-api-v1.json"
        self.template = json.loads(workflow_file.read_text())

    def test_workflow_uses_flux2_encoder_type(self):
        self.assertEqual(self.template["2"]["inputs"]["type"], "flux2")

    def test_only_controlled_fields_change(self):
        request = {"prompt": "Test", "width": 768, "height": 512, "seed": 123}
        result = MODULE.build_workflow(self.template, request, "abc123")
        self.assertEqual(result["4"]["inputs"]["text"], "Test")
        self.assertEqual(result["6"]["inputs"]["width"], 768)
        self.assertEqual(result["9"]["inputs"]["height"], 512)
        self.assertEqual(result["7"]["inputs"]["noise_seed"], 123)
        self.assertEqual(result["1"]["inputs"]["unet_name"], "flux-2-klein-4b-fp8.safetensors")
        self.assertEqual(result["8"]["inputs"]["sampler_name"], "euler")
        self.assertEqual(self.template["4"]["inputs"]["text"], "a red apple on a wooden table, photorealistic, studio light")


class QwenProviderPolicyTests(unittest.TestCase):
    def test_cloud_provider_is_removed(self):
        payload = {
            "current": {
                "authType": "openai",
                "modelId": "local-quality(openai)",
                "baseUrl": "http://127.0.0.1:11434/v1",
            },
            "providers": [
                {"authType": "qwen-oauth", "models": [{"modelId": "coder-model(qwen-oauth)"}]},
                {
                    "authType": "openai",
                    "models": [
                        {
                            "modelId": "local-quality(openai)",
                            "baseUrl": "http://127.0.0.1:11434/v1",
                        },
                        {"modelId": "remote(openai)", "baseUrl": "https://example.invalid/v1"},
                    ],
                },
            ],
        }
        filtered = MODULE.filter_local_qwen_providers(payload)
        self.assertEqual(len(filtered["providers"]), 1)
        self.assertEqual([m["modelId"] for m in filtered["providers"][0]["models"]], ["local-quality(openai)"])

    def test_cloud_model_switch_is_blocked(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.validate_qwen_proxy_mutation(
                "/session/abc/model",
                "POST",
                json.dumps({"modelId": "coder-model(qwen-oauth)"}).encode(),
            )

    def test_local_model_switch_is_allowed(self):
        MODULE.validate_qwen_proxy_mutation(
            "/session/abc/model",
            "POST",
            json.dumps({"modelId": "local-fast(openai)"}).encode(),
        )

    def test_auth_provider_install_is_blocked(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.validate_qwen_proxy_mutation("/workspace/auth/provider", "POST", b"{}")


if __name__ == "__main__":
    unittest.main()
