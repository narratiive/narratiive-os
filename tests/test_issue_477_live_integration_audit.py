from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.run_issue_477_live_integration_audit import _redacted_identifier, build_report


class Issue477LiveIntegrationAuditTests(unittest.TestCase):
    def test_identifiers_are_redacted_deterministically(self):
        value = _redacted_identifier("provider-record-123")
        self.assertRegex(value, r"^sha256:[0-9a-f]{12}$")
        self.assertEqual(value, _redacted_identifier("provider-record-123"))
        self.assertNotIn("provider-record", value)

    @patch("scripts.run_issue_477_live_integration_audit._activation_probe")
    @patch("scripts.run_issue_477_live_integration_audit._telegram_probe")
    @patch("scripts.run_issue_477_live_integration_audit._journey_reads")
    @patch("scripts.run_issue_477_live_integration_audit._business_adapter_probes")
    @patch("scripts.run_issue_477_live_integration_audit._health_checks")
    @patch("scripts.run_issue_477_live_integration_audit.build_http_dispatchers")
    def test_report_declares_zero_external_mutation(
        self,
        dispatchers,
        health,
        business,
        reads,
        telegram,
        activation,
    ):
        dispatchers.return_value = {}
        health.return_value = {}
        business.return_value = {}
        reads.return_value = {}
        telegram.return_value = {}
        activation.return_value = {}
        report = build_report({}, __import__("datetime").date(2026, 10, 16))
        self.assertEqual(report["safeguards"]["external_writes"], 0)
        self.assertFalse(report["safeguards"]["outreach_sent"])
        self.assertFalse(report["safeguards"]["campaigns_published"])
        self.assertFalse(report["safeguards"]["media_spend"])


if __name__ == "__main__":
    unittest.main()
