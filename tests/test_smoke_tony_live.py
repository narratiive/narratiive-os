from __future__ import annotations

import unittest

from scripts.smoke_tony_live import evaluate_command, evaluate_health


class TonyLiveSmokeTests(unittest.TestCase):
    def test_health_requires_alive_success(self) -> None:
        self.assertTrue(evaluate_health({"ok": True, "status": "alive"}).ok)
        self.assertFalse(evaluate_health({"ok": True, "status": "starting"}).ok)
        self.assertFalse(evaluate_health({"ok": False, "status": "alive"}).ok)

    def test_command_requires_success_and_operator_reply(self) -> None:
        result = evaluate_command("/status", {"ok": True, "command": "status", "status": "healthy", "reply": "Ready"})
        self.assertTrue(result.ok)
        self.assertEqual(result.check, "status")
        self.assertIn("status=healthy", result.detail)

    def test_command_rejects_missing_reply(self) -> None:
        result = evaluate_command("/capabilities", {"ok": True, "command": "capabilities", "status": "healthy"})
        self.assertFalse(result.ok)

    def test_message_is_accepted_as_reply_contract(self) -> None:
        result = evaluate_command("/status", {"ok": True, "command": "status", "message": "Ready"})
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
