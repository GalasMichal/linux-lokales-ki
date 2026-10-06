from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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


class AgentBootProgressTests(unittest.TestCase):
    def test_phase_percents_only_rise_until_ready(self):
        order = ["stopping_images", "starting_qwen", "waiting_health", "ready"]
        percents = [MODULE.boot_payload(phase)["percent"] for phase in order]
        self.assertEqual(percents, sorted(percents))
        self.assertLess(MODULE.boot_payload("waiting_health")["percent"], MODULE.boot_payload("ready")["percent"])
        self.assertLess(MODULE.boot_payload("ready")["percent"], 100)

    def test_set_boot_stores_payload_on_app(self):
        app: dict = {}
        payload = MODULE.set_boot(app, "waiting_health")
        self.assertEqual(app["boot"]["phase"], "waiting_health")
        self.assertEqual(payload["percent"], 45)
        self.assertIn("4170", payload["detail"])

    def test_unknown_phase_falls_back_to_idle(self):
        payload = MODULE.boot_payload("not-a-phase")
        self.assertEqual(payload["phase"], "idle")
        self.assertEqual(payload["percent"], 0)


class QwenEmbedCorsTests(unittest.TestCase):
    def test_iframe_origin_is_allowed(self):
        self.assertEqual(MODULE.cors_allow_origin("http://127.0.0.1:8791"), "http://127.0.0.1:8791")
        self.assertEqual(MODULE.cors_allow_origin("http://127.0.0.1:8790"), "http://127.0.0.1:8790")
        self.assertIsNone(MODULE.cors_allow_origin("http://example.com"))

    def test_origin_is_not_forwarded_upstream(self):
        class Req:
            headers = {
                "Host": "127.0.0.1:8791",
                "Origin": "http://127.0.0.1:8791",
                "Referer": "http://127.0.0.1:8791/?theme=dark",
                "Accept": "text/javascript",
            }

        headers = MODULE.filtered_request_headers(Req())
        self.assertNotIn("Origin", headers)
        self.assertNotIn("Referer", headers)
        self.assertEqual(headers["Accept"], "text/javascript")


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
FLUX_WORKFLOW_SHA = "d9d752d52b1430bd3756908885146daea41279e29a7b6e3a9e05705572f39953"


def _write_png(path: Path) -> Path:
    path.write_bytes(TINY_PNG)
    return path


class EditRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ki-edit-"))
        self.png = _write_png(self.tmp / "input.png")
        self.ref = _write_png(self.tmp / "ref.png")

    def tearDown(self):
        for item in self.tmp.rglob("*"):
            if item.is_file():
                item.unlink()
        self.tmp.rmdir()

    def test_valid_edit_request(self):
        parsed = MODULE.parse_edit_request(
            {
                "instruction": "  Change only the apple from red to bright green. Keep everything else unchanged.  ",
                "input_path": str(self.png),
                "width": 1024,
                "height": 1024,
                "seed": 42,
            }
        )
        self.assertEqual(parsed["width"], 1024)
        self.assertEqual(parsed["resolution"], 1024)
        self.assertFalse(parsed["preserve_alpha"])
        self.assertEqual(parsed["input"]["name"], "input.png")
        self.assertIn(parsed["input"]["origin"], {"tmp", "var_tmp"})

    def test_preserve_alpha_prefixes_instruction(self):
        parsed = MODULE.parse_edit_request(
            {
                "instruction": "keep the cutout",
                "input_path": str(self.png),
                "preserve_alpha": True,
            }
        )
        self.assertTrue(parsed["composed_instruction"].startswith(MODULE.ALPHA_PROMPT_PREFIX))
        self.assertTrue(parsed["composed_instruction"].endswith(MODULE.ALPHA_PROMPT_SUFFIX))
        self.assertIn("keep the cutout", parsed["composed_instruction"])
        self.assertEqual(parsed["instruction"], "keep the cutout")

    def test_workflow_id_is_rejected(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.parse_edit_request(
                {
                    "instruction": "x",
                    "input_path": str(self.png),
                    "workflow_id": "anything",
                }
            )

    def test_graph_is_rejected(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.parse_edit_request(
                {
                    "instruction": "x",
                    "input_path": str(self.png),
                    "graph": {"1": {}},
                }
            )

    def test_path_outside_roots_is_rejected(self):
        with self.assertRaises(MODULE.AppError) as ctx:
            MODULE.parse_edit_request(
                {
                    "instruction": "x",
                    "input_path": "/etc/hostname",
                }
            )
        self.assertIn("außerhalb", str(ctx.exception))

    def test_url_is_rejected(self):
        with self.assertRaises(MODULE.AppError):
            MODULE.parse_edit_request(
                {
                    "instruction": "x",
                    "input_path": "https://example.invalid/a.png",
                }
            )

    def test_type_is_rejected(self):
        bad = self.tmp / "notes.txt"
        bad.write_text("not an image\n")
        with self.assertRaises(MODULE.AppError) as ctx:
            MODULE.parse_edit_request({"instruction": "x", "input_path": str(bad)})
        self.assertIn("PNG", str(ctx.exception))

    def test_size_is_rejected(self):
        huge = self.tmp / "huge.png"
        huge.write_bytes(TINY_PNG + b"\x00" * (25 * 1024 * 1024 + 1))
        with self.assertRaises(MODULE.AppError) as ctx:
            MODULE.parse_edit_request({"instruction": "x", "input_path": str(huge)})
        self.assertIn("25 MiB", str(ctx.exception))

    def test_too_many_references_are_rejected(self):
        extras = [_write_png(self.tmp / f"r{i}.png") for i in range(3)]
        with self.assertRaises(MODULE.AppError):
            MODULE.parse_edit_request(
                {
                    "instruction": "x",
                    "input_path": str(self.png),
                    "reference_paths": [str(path) for path in extras],
                }
            )


class EditWorkflowTests(unittest.TestCase):
    def setUp(self):
        workflow_file = SERVER.parent / "workflows" / "qwen-image-21-edit-v1.json"
        self.template = json.loads(workflow_file.read_text())
        flux_file = SERVER.parent / "workflows" / "flux2-klein-t2i-api-v1.json"
        self.flux = json.loads(flux_file.read_text())

    def test_frozen_edit_models(self):
        self.assertEqual(self.template["1"]["inputs"]["unet_name"], "qwen_image_2.1_int8_convrot.safetensors")
        self.assertEqual(self.template["2"]["inputs"]["clip_name"], "qwen3vl_8b_w4a8.safetensors")
        self.assertEqual(self.template["2"]["inputs"]["type"], "qwen_image")
        self.assertEqual(self.template["3"]["inputs"]["vae_name"], "qwen_image_2.1_vae_bf16.safetensors")
        self.assertEqual(self.template["4"]["inputs"]["device"], "cpu")
        self.assertEqual(self.template["4"]["inputs"]["dtype"], "int8")
        self.assertEqual(self.template["7"]["inputs"]["steps"], 25)
        self.assertEqual(self.template["7"]["inputs"]["cfg"], 1.0)
        self.assertEqual(self.template["7"]["inputs"]["sampler_name"], "euler")
        self.assertEqual(self.template["7"]["inputs"]["scheduler"], "simple")

    def test_multi_reference_adds_loadimage_nodes(self):
        request = {
            "composed_instruction": "use the style",
            "resolution": 1024,
            "seed": 7,
        }
        result = MODULE.build_edit_workflow(self.template, request, "job1", ["a.png", "b.png"])
        self.assertEqual(result["5"]["inputs"]["image"], "a.png")
        self.assertEqual(result["10"]["class_type"], "LoadImage")
        self.assertEqual(result["10"]["inputs"]["image"], "b.png")
        self.assertEqual(result["6"]["inputs"]["images.image_2"], ["10", 0])
        self.assertNotIn("images.image_3", result["6"]["inputs"])
        self.assertEqual(self.template["5"]["inputs"]["image"], "ki_edit_input.png")

    def test_flux_workflow_hash_unchanged(self):
        digest = MODULE.hashlib.sha256(MODULE.canonical_json(self.flux)).hexdigest()
        self.assertEqual(digest, FLUX_WORKFLOW_SHA)
        self.assertEqual(self.flux["1"]["inputs"]["unet_name"], "flux-2-klein-4b-fp8.safetensors")


class EditStoragePreflightTests(unittest.TestCase):
    def test_unmounted_archive_aborts(self):
        with mock.patch("os.path.ismount", return_value=False):
            with self.assertRaises(MODULE.AppError) as ctx:
                MODULE.preflight_edit_storage()
        self.assertIn("nicht eingehängt", str(ctx.exception))


class EditHttpGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp import ClientSession, test_utils

        self.session = ClientSession()
        self.app = MODULE.create_ui_app(self.session)
        self.server = test_utils.TestServer(self.app)
        await self.server.start_server()
        self.client = test_utils.TestClient(self.server)
        await self.client.start_server()
        self.started = []

        async def fake_service_action(action, unit):
            self.started.append((action, unit))
            raise AssertionError(f"Dienstaktion unerwartet: {action} {unit}")

        self.action_patch = mock.patch.object(MODULE, "service_action", fake_service_action)
        self.action_patch.start()

    async def asyncTearDown(self):
        self.action_patch.stop()
        await self.client.close()
        await self.server.close()
        await self.session.close()

    async def test_path_returns_400_without_starting_comfy(self):
        response = await self.client.post(
            "/api/images/edit",
            json={
                "instruction": "x",
                "input_path": "/etc/hostname",
            },
        )
        payload = await response.json()
        self.assertEqual(response.status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(self.started, [])

    async def test_cleanup_error_still_stops_gpu(self):
        tmp = Path(tempfile.mkdtemp(prefix="ki-edit-http-"))
        png = _write_png(tmp / "in.png")
        cleaned = {"called": False}

        async def fake_ensure(app):
            raise MODULE.AppError("simulierter GPU-Fehler")

        async def fake_cleanup(app):
            cleaned["called"] = True
            return {"ok": True}

        with (
            mock.patch.object(MODULE, "preflight_edit_storage", lambda: None),
            mock.patch.object(MODULE, "missing_edit_models", lambda: []),
            mock.patch.object(MODULE, "ensure_edit_image_mode", fake_ensure),
            mock.patch.object(MODULE, "cleanup_gpu", fake_cleanup),
        ):
            response = await self.client.post(
                "/api/images/edit",
                json={"instruction": "x", "input_path": str(png)},
            )
        payload = await response.json()
        png.unlink()
        tmp.rmdir()
        self.assertEqual(response.status, 500)
        self.assertFalse(payload["ok"])
        self.assertTrue(cleaned["called"])


class WorkplaceHtmlTests(unittest.TestCase):
    def setUp(self):
        self.html = (SERVER.parent / "www" / "index.html").read_text()

    def test_three_image_subviews_exist(self):
        self.assertIn('data-subview="simple"', self.html)
        self.assertIn(">Erzeugen<", self.html)
        self.assertIn('data-subview="edit"', self.html)
        self.assertIn(">Bearbeiten<", self.html)
        self.assertIn('data-subview="expert"', self.html)
        self.assertIn("Workflow (Experte)", self.html)

    def test_generate_form_unchanged_fields(self):
        self.assertIn('id="image-form"', self.html)
        self.assertIn("/api/images/generate", self.html)
        self.assertIn('id="generate-btn"', self.html)
        self.assertIn('id="prompt"', self.html)
        self.assertIn('id="width"', self.html)
        self.assertIn('id="seed"', self.html)

    def test_edit_form_has_no_path_or_workflow_fields(self):
        self.assertIn('id="edit-form"', self.html)
        self.assertIn("/api/images/edit", self.html)
        self.assertNotIn('id="edit-path"', self.html)
        self.assertNotIn("workflow_id", self.html)
        self.assertIn("maxlength=\"4000\"", self.html)
        self.assertEqual(self.html.count('class="edit-ref"'), 2)
        self.assertIn('id="preserve-alpha"', self.html)
        self.assertIn("/api/images/stage", self.html)
        self.assertIn("/api/images/jobs/", self.html)

    def test_edit_sizes_match_generate(self):
        for size in ("512", "768", "1024"):
            self.assertIn(f">{size}<", self.html)
        self.assertIn('id="edit-width"', self.html)
        self.assertIn('id="edit-seed"', self.html)


class StageAndOutputTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp import ClientSession, test_utils

        self.session = ClientSession()
        self.app = MODULE.create_ui_app(self.session)
        self.server = test_utils.TestServer(self.app)
        await self.server.start_server()
        self.client = test_utils.TestClient(self.server)
        await self.client.start_server()
        self.started = []

        async def fake_service_action(action, unit):
            self.started.append((action, unit))
            raise AssertionError(f"Dienstaktion unerwartet: {action} {unit}")

        self.action_patch = mock.patch.object(MODULE, "service_action", fake_service_action)
        self.action_patch.start()

    async def asyncTearDown(self):
        self.action_patch.stop()
        await self.client.close()
        await self.server.close()
        await self.session.close()
        if MODULE.UI_STAGE_DIR.is_dir():
            for path in MODULE.UI_STAGE_DIR.glob("ui_stage_*"):
                path.unlink(missing_ok=True)

    async def test_stage_png_gets_random_name(self):
        from aiohttp import FormData

        form = FormData()
        form.add_field("file", TINY_PNG, filename="apple.png", content_type="image/png")
        response = await self.client.post("/api/images/stage", data=form)
        payload = await response.json()
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        path = Path(payload["path"])
        self.assertTrue(path.name.startswith("ui_stage_"))
        self.assertEqual(path.suffix, ".png")
        self.assertTrue(str(path).startswith(str(MODULE.UI_STAGE_DIR)))
        self.assertEqual(payload["name"], "apple.png")
        self.assertEqual(self.started, [])
        path.unlink(missing_ok=True)

    async def test_stage_rejects_txt(self):
        from aiohttp import FormData

        form = FormData()
        form.add_field("file", b"not-an-image", filename="notes.txt", content_type="text/plain")
        response = await self.client.post("/api/images/stage", data=form)
        payload = await response.json()
        self.assertEqual(response.status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(self.started, [])

    async def test_job_output_rejects_bad_id(self):
        response = await self.client.get("/api/images/jobs/../secret/output")
        self.assertIn(response.status, {400, 404})
        self.assertEqual(self.started, [])

    async def test_edit_without_starting_comfy_on_empty_instruction_after_stage(self):
        from aiohttp import FormData

        form = FormData()
        form.add_field("file", TINY_PNG, filename="in.png", content_type="image/png")
        staged = await (await self.client.post("/api/images/stage", data=form)).json()
        response = await self.client.post(
            "/api/images/edit",
            json={"instruction": " ", "input_path": staged["path"]},
        )
        payload = await response.json()
        self.assertEqual(response.status, 400)
        self.assertEqual(self.started, [])
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
