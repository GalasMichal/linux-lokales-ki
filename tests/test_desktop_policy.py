from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "apps" / "local-tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("desktop_policy", TOOLS / "desktop_policy.py")
POLICY = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(POLICY)


class DesktopPolicyTests(unittest.TestCase):
    def test_terminal_and_browser_are_blocked(self):
        terminal = POLICY.classify_window("org.kde.konsole", "konsole", "Konsole")
        self.assertTrue(terminal["terminal"])
        self.assertIn("Terminal", str(terminal["input_block_reason"]))
        browser = POLICY.classify_window("brave-browser", "brave", "Example")
        self.assertTrue(browser["browser"])
        self.assertIn("browser_", str(browser["input_block_reason"]))
        mail = POLICY.classify_window("Chatgpt", "chatgpt", "ChatGPT")
        self.assertIn("Messenger", str(mail["input_block_reason"]))

    def test_password_dialog_is_blocked(self):
        window = POLICY.classify_window(
            "org.kde.polkit-kde-authentication-agent-1",
            "",
            "Authentifizierung erforderlich",
        )
        self.assertTrue(window["auth"])
        self.assertIn("Passwort", str(window["input_block_reason"]))
        self.assertTrue(POLICY.is_password_role("password text"))

    def test_key_allowlist_rejects_shell_shortcuts(self):
        self.assertEqual(POLICY.normalize_key("Strg+A"), "ctrl+a")
        self.assertEqual(POLICY.normalize_key("Shift+Tab"), "shift+tab")
        for key in ("super+enter", "alt+f2", "ctrl+alt+f1", "alt+f4", "ctrl+shift+t"):
            with self.assertRaises(POLICY.ToolError):
                POLICY.normalize_key(key)

    def test_delete_pay_and_send_are_blocked(self):
        self.assertIn("Löschen", POLICY.blocked_control_reason("Endgültig löschen") or "")
        self.assertIn("Bezahlen", POLICY.blocked_control_reason("Jetzt bezahlen") or "")
        self.assertIn("Senden", POLICY.blocked_control_reason("Nachricht senden") or "")
        self.assertIsNone(POLICY.blocked_control_reason("Info"))

    def test_click_must_stay_inside_the_window(self):
        POLICY.require_point_inside(0, 0, 100, 40)
        with self.assertRaises(POLICY.ToolError):
            POLICY.require_point_inside(100, 0, 100, 40)
        with self.assertRaises(POLICY.ToolError):
            POLICY.require_point_inside(-1, 2, 100, 40)

    def test_type_text_rejects_control_characters(self):
        self.assertEqual(POLICY.check_type_text("Desktop Agent Test"), "Desktop Agent Test")
        with self.assertRaises(POLICY.ToolError):
            POLICY.check_type_text("rm\x1b[A")
        with self.assertRaises(POLICY.ToolError):
            POLICY.check_type_text("")


if __name__ == "__main__":
    unittest.main()
