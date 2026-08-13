from __future__ import annotations

import unittest
from pathlib import Path


class TelegramInboundInstallTests(unittest.TestCase):
    def test_installer_exists_and_targets_expected_label(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "scripts" / "install_telegram_inbound_agent.py").read_text(encoding="utf-8")
        self.assertIn('LABEL = "com.narratiive.telegram-inbound"', text)
        self.assertIn('"-m",\n            "openclaw.telegram_inbound"', text)
        self.assertIn('"KeepAlive": True', text)


if __name__ == "__main__":
    unittest.main()
