#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
WORKFLOW = REPO / "apps" / "ki-workplace" / "workflows" / "flux2-klein-t2i-api-v1.json"
SERVER = REPO / "apps" / "ki-workplace" / "server.py"
OLD_TREE = Path("/srv/ai/apps/ComfyUI")
NEW_TREE = Path("/srv/ai/apps/ComfyUI-0.37.0")
MODELS = Path("/srv/ai/models/comfyui")
UNIT = Path.home() / ".config/systemd/user/comfyui.service"
WANT_033 = "cc0fc21fea7a6a82f568362b15b7fbd713b419c1"
WANT_037 = "73c9bad4d21e7addbe1d13bc92eee0f1431b017d"
WORKFLOW_SHA = "d9d752d52b1430bd3756908885146daea41279e29a7b6e3a9e05705572f39953"
MODEL_SHA = {
    MODELS / "diffusion_models/flux-2-klein-4b-fp8.safetensors": "97ed34fe0567e436200f2faee3939b88f2b5d99f8af2a4dc16532c4245c0ccb6",
    MODELS / "text_encoders/qwen_3_4b.safetensors": "6c671498573ac2f7a5501502ccce8d2b08ea6ca2f661c458e708f36b36edfc5a",
    MODELS / "vae/flux2-vae.safetensors": "868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


class ScriptTests(unittest.TestCase):
    def test_scripts_exist_and_parse(self):
        names = [
            "backup-comfyui-0.33.sh",
            "install-comfyui-0.37.0-isolated.sh",
            "prepare-comfyui-0.37-venv.sh",
            "start-comfyui-0.37-isolated.sh",
            "stop-comfyui-0.37-isolated.sh",
            "apply-comfyui-0.37.0.sh",
            "rollback-comfyui-0.33.0.sh",
        ]
        for name in names:
            path = SCRIPTS / name
            self.assertTrue(path.is_file(), name)
            subprocess.check_call(["bash", "-n", str(path)])

    def test_rollback_requires_backup(self):
        proc = subprocess.run(
            [str(SCRIPTS / "rollback-comfyui-0.33.0.sh")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage:", proc.stdout + proc.stderr)

    def test_apply_refuses_without_isolated_pass(self):
        marker = NEW_TREE / ".isolated-flux-pass.json"
        if NEW_TREE.is_dir() and marker.is_file():
            self.skipTest("isolated pass marker present; apply would cut over")
        proc = subprocess.run(
            [str(SCRIPTS / "apply-comfyui-0.37.0.sh")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("ABBRUCH", proc.stdout + proc.stderr)


class WorkflowAndModelTests(unittest.TestCase):
    def test_productive_workflow_hash_unchanged(self):
        data = json.loads(WORKFLOW.read_text())
        canon = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(canon).hexdigest(), WORKFLOW_SHA)
        self.assertEqual(data["2"]["inputs"]["type"], "flux2")
        self.assertEqual(data["1"]["inputs"]["unet_name"], "flux-2-klein-4b-fp8.safetensors")

    def test_workplace_still_points_at_flux_and_localhost(self):
        text = SERVER.read_text()
        self.assertIn('COMFY_URL = "http://127.0.0.1:8188"', text)
        self.assertIn('WORKFLOW_ID = "flux2-klein-t2i-v1"', text)
        self.assertIn("flux-2-klein-4b-fp8.safetensors", text)
        self.assertNotIn("edit_image", text)

    def test_model_hashes_unchanged(self):
        for path, digest in MODEL_SHA.items():
            self.assertTrue(path.is_file(), str(path))
            self.assertEqual(_sha256(path), digest)

    def test_no_qwen_image_21_weights(self):
        hits = list(MODELS.rglob("qwen_image_2.1*")) + list(MODELS.rglob("qwen3vl_8b*"))
        self.assertEqual(hits, [])


class LiveTreeTests(unittest.TestCase):
    def test_old_tree_is_0_33(self):
        self.assertTrue(OLD_TREE.is_dir())
        self.assertEqual(_git_head(OLD_TREE), WANT_033)
        version = tomllib.loads((OLD_TREE / "pyproject.toml").read_text())["project"]["version"]
        self.assertEqual(version, "0.33.0")

    def test_unit_localhost_bind(self):
        text = UNIT.read_text()
        self.assertIn("--listen 127.0.0.1 --port 8188", text)
        self.assertNotIn("0.0.0.0", text)

    @unittest.skipUnless(NEW_TREE.is_dir(), "0.37 tree not installed yet")
    def test_new_tree_is_0_37(self):
        self.assertEqual(_git_head(NEW_TREE), WANT_037)
        version = tomllib.loads((NEW_TREE / "pyproject.toml").read_text())["project"]["version"]
        self.assertEqual(version, "0.37.0")
        joined = ""
        for path in NEW_TREE.rglob("*.py"):
            if "custom_nodes" in path.parts:
                continue
            try:
                joined += path.read_text(errors="ignore")
            except OSError:
                continue
            if "TextEncodeQwenImage21" in joined and "EmptyFlux2LatentImage" in joined:
                break
        self.assertIn("TextEncodeQwenImage21", joined)
        self.assertIn("QwenImage21Cache", joined)
        self.assertIn("EmptyFlux2LatentImage", joined)


class CutoverStateTests(unittest.TestCase):
    @unittest.skipUnless(
        UNIT.is_file() and "ComfyUI-0.37.0" in UNIT.read_text(),
        "productive unit not on 0.37.0 yet",
    )
    def test_productive_unit_uses_037_tree(self):
        text = UNIT.read_text()
        self.assertIn("WorkingDirectory=/srv/ai/apps/ComfyUI-0.37.0", text)
        self.assertIn("--listen 127.0.0.1 --port 8188", text)
        self.assertIn("--output-directory /srv/ai/apps/ComfyUI/output", text)


if __name__ == "__main__":
    unittest.main()
