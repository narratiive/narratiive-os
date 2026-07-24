from __future__ import annotations

import unittest

from runtime.tony_capabilities import TonyCapability, TonyCapabilityRegistry


class TonyCapabilityRegistryTests(unittest.TestCase):
    def test_snapshot_reports_partial_configuration(self):
        snapshot = TonyCapabilityRegistry().snapshot({"mission_control"})
        self.assertEqual(snapshot["status"], "partial")
        mission = next(item for item in snapshot["capabilities"] if item["command"] == "/mission")
        history = next(item for item in snapshot["capabilities"] if item["command"] == "/history [filter]")
        self.assertTrue(mission["available"])
        self.assertFalse(history["available"])
        self.assertEqual(history["missing_requirements"], ["execution_journal"])

    def test_snapshot_is_ready_when_optional_features_are_configured(self):
        snapshot = TonyCapabilityRegistry().snapshot({"mission_control", "execution_journal", "diagnostics"})
        self.assertEqual(snapshot["status"], "ready")
        self.assertEqual(snapshot["available_count"], snapshot["total_count"])

    def test_telegram_summary_exposes_commands_and_availability(self):
        summary = TonyCapabilityRegistry().telegram_summary({"mission_control"})
        self.assertIn("Tony capabilities:", summary)
        self.assertIn("/mission", summary)
        self.assertIn("/history [filter]", summary)
        self.assertIn("/client <name>", summary)

    def test_duplicate_commands_are_rejected(self):
        duplicate = TonyCapability("/health", "Duplicate", "system")
        with self.assertRaisesRegex(ValueError, "unique"):
            TonyCapabilityRegistry((duplicate, duplicate))

    def test_capability_payload_is_json_compatible(self):
        payload = TonyCapabilityRegistry().snapshot()
        self.assertIsInstance(payload["capabilities"], list)
        self.assertIsInstance(payload["capabilities"][0]["aliases"], list)
        self.assertIsInstance(payload["capabilities"][0]["requires"], list)


if __name__ == "__main__":
    unittest.main()
