from __future__ import annotations

import unittest
from pathlib import Path


class TelegramInboundInstallTests(unittest.TestCase):
    def test_legacy_installer_is_deprecated_and_cannot_start_a_second_poller(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "scripts" / "install_telegram_inbound_agent.py").read_text(encoding="utf-8")
        self.assertIn('LABEL = "com.narratiive.telegram-inbound"', text)
        self.assertIn('"status": "deprecated"', text)
        self.assertIn("OpenClaw now owns Telegram inbound", text)
        self.assertNotIn('"-m",\n            "openclaw.telegram_inbound"', text)
        self.assertNotIn('"KeepAlive": True', text)
        self.assertNotIn("launchctl", text)


if __name__ == "__main__":
    unittest.main()
