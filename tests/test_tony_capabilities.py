from __future__ import annotations

import unittest

from runtime.tony_capabilities import TonyCapability, TonyCapabilityRegistry


class TonyCapabilityRegistryTests(unittest.TestCase):
    def test_snapshot_reports_partial_configuration(self):
        snapshot = TonyCapabilityRegistry().snapshot({"mission_control"})
        self.assertEqual(snapshot["status"], "partial")
        mission = next(item for item in snapshot["capabilities"] if item["command"] == "/mission")
        morning = next(item for item in snapshot["capabilities"] if item["command"] == "/morning")
        evening = next(item for item in snapshot["capabilities"] if item["command"] == "/evening")
        friday = next(item for item in snapshot["capabilities"] if item["command"] == "/friday")
        vocabulary = next(item for item in snapshot["capabilities"] if item["command"] == "/vocabulary")
        history = next(item for item in snapshot["capabilities"] if item["command"] == "/history [filter]")
        self.assertTrue(mission["available"])
        self.assertTrue(morning["available"])
        self.assertTrue(evening["available"])
        self.assertTrue(friday["available"])
        self.assertTrue(vocabulary["available"])
        self.assertFalse(history["available"])
        self.assertEqual(history["missing_requirements"], ["execution_journal"])

    def test_snapshot_is_ready_when_optional_features_are_configured(self):
        snapshot = TonyCapabilityRegistry().snapshot(
            {"mission_control", "execution_journal", "diagnostics", "github"}
        )
        self.assertEqual(snapshot["status"], "ready")
        self.assertEqual(snapshot["available_count"], snapshot["total_count"])

    def test_executive_capabilities_publish_canonical_aliases(self):
        snapshot = TonyCapabilityRegistry().snapshot({"mission_control"})
        entries = {item["command"]: item for item in snapshot["capabilities"]}
        self.assertEqual(entries["/morning"]["aliases"], ["/morning_brief", "/standup"])
        self.assertEqual(entries["/evening"]["aliases"], ["/evening_review", "/end_of_day"])
        self.assertEqual(
            entries["/friday"]["aliases"],
            ["/friday_review", "/weekly_review", "/executive_review"],
        )
        self.assertEqual(entries["/vocabulary"]["aliases"], ["/terminology", "/canon"])

    def test_telegram_summary_exposes_commands_and_availability(self):
        summary = TonyCapabilityRegistry().telegram_summary({"mission_control"})
        self.assertIn("Tony capabilities:", summary)
        self.assertIn("/mission", summary)
        self.assertIn("/morning", summary)
        self.assertIn("/evening", summary)
        self.assertIn("/friday", summary)
        self.assertIn("/vocabulary", summary)
        self.assertIn("/github", summary)
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
