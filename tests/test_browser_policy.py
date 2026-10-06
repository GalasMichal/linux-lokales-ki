from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "apps" / "local-tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("browser_policy", TOOLS / "browser_policy.py")
POLICY = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(POLICY)


class UrlTests(unittest.TestCase):
    def test_file_is_blocked(self):
        with self.assertRaises(POLICY.ToolError):
            POLICY.check_navigation_url("file:///etc/passwd")

    def test_javascript_is_blocked(self):
        with self.assertRaises(POLICY.ToolError):
            POLICY.check_navigation_url("javascript:alert(1)")

    def test_chrome_and_about_are_blocked(self):
        with self.assertRaises(POLICY.ToolError):
            POLICY.check_navigation_url("chrome://settings")
        with self.assertRaises(POLICY.ToolError):
            POLICY.check_navigation_url("about:config")

    def test_localhost_and_link_local_are_blocked(self):
        for url in (
            "http://127.0.0.1:11434",
            "http://localhost:8765/",
            "http://169.254.1.2/",
            "http://10.1.2.3/",
            "http://192.168.178.1/",
            "http://172.16.0.5/",
        ):
            with self.assertRaises(POLICY.ToolError, msg=url):
                POLICY.check_navigation_url(url)

    def test_data_and_ftp_are_blocked(self):
        with self.assertRaises(POLICY.ToolError):
            POLICY.check_navigation_url("data:text/html,hi")
        with self.assertRaises(POLICY.ToolError):
            POLICY.check_navigation_url("ftp://example.com/file")

    def test_blank_document_is_only_internal(self):
        self.assertTrue(POLICY.check_request_url("about:blank"))
        self.assertFalse(POLICY.check_request_url("javascript:alert(1)"))
        self.assertFalse(POLICY.check_request_url("file:///etc/passwd"))


class ActionTests(unittest.TestCase):
    def test_dangerous_names(self):
        self.assertTrue(POLICY.is_dangerous_action("Jetzt kaufen"))
        self.assertTrue(POLICY.is_dangerous_action("Submit order"))
        self.assertFalse(POLICY.is_dangerous_action("Learn more"))

    def test_executable_downloads(self):
        self.assertTrue(POLICY.is_executable_download("setup.sh"))
        self.assertTrue(POLICY.is_executable_download("tool.AppImage"))
        self.assertFalse(POLICY.is_executable_download("notes.txt"))

    def test_control_kinds(self):
        self.assertEqual(POLICY.classify_control("a", "", ""), "link")
        self.assertEqual(POLICY.classify_control("input", "", "password"), "input")
        self.assertEqual(POLICY.classify_control("input", "", "file"), None)


if __name__ == "__main__":
    unittest.main()
