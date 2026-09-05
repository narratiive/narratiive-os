from __future__ import annotations

import json
import subprocess
import sys
import unittest
from unittest import mock

from scripts.validate_business_adapters import validate


class ValidateBusinessAdaptersTests(unittest.TestCase):
    def test_documented_script_entrypoint_loads_runtime_package(self):
        result = subprocess.run(
            [sys.executable, "scripts/validate_business_adapters.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("read-only provider", result.stdout)
        self.assertIn("operations", result.stdout)

    def test_unconfigured_adapters_fail_when_required_without_exposing_values(self):
        report = validate(
            {"TONY_DISPATCH_GMAIL_MODE": "google_api", "TONY_GOOGLE_CLIENT_ID": "secret-value"},
            required=("Gmail",),
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["checks"][0]["status"], "unconfigured")
        self.assertNotIn("secret-value", json.dumps(report))

    @mock.patch("scripts.validate_business_adapters.build_http_dispatchers")
    def test_each_configured_adapter_requires_read_only_probe_evidence(self, build_dispatchers):
        good = mock.Mock()
        good.probe.return_value = {
            "verified": True,
            "read_only": True,
            "mutation_count": 0,
            "source_id": "provider:synthetic",
        }
        bad = mock.Mock()
        bad.probe.return_value = {"verified": True, "mutation_count": 1, "source_id": "provider:synthetic"}
        build_dispatchers.return_value = {
            "Gmail": good,
            "Google Calendar": good,
            "Google Drive": good,
            "Notion": good,
            "Fireflies": bad,
        }
        env = {
            "TONY_DISPATCH_GMAIL_MODE": "google_api",
            "TONY_DISPATCH_GOOGLE_CALENDAR_MODE": "google_api",
            "TONY_DISPATCH_GOOGLE_DRIVE_MODE": "google_api",
            "TONY_GOOGLE_ACCESS_TOKEN": "synthetic",
            "TONY_DISPATCH_NOTION_MODE": "notion_api",
            "NARRATIIVE_NOTION_TOKEN": "synthetic",
            "TONY_DISPATCH_FIREFLIES_MODE": "fireflies_api",
            "TONY_FIREFLIES_API_KEY": "synthetic",
        }

        report = validate(env)

        self.assertFalse(report["ok"])
        self.assertEqual(report["checks"][-1]["status"], "unverified_response")
        self.assertEqual(good.probe.call_count, 4)

    def test_optional_unconfigured_workers_do_not_fail_selected_probe(self):
        with mock.patch("scripts.validate_business_adapters.build_http_dispatchers") as build_dispatchers:
            notion = mock.Mock()
            notion.probe.return_value = {
                "verified": True,
                "read_only": True,
                "mutation_count": 0,
                "source_id": "notion:data_source:synthetic",
            }
            build_dispatchers.return_value = {"Notion": notion}
            report = validate(
                {
                    "TONY_DISPATCH_NOTION_MODE": "notion_api",
                    "NARRATIIVE_NOTION_TOKEN": "synthetic",
                },
                required=("Notion",),
            )

        self.assertTrue(report["ok"])
        self.assertEqual(report["checks"][3]["status"], "verified_read_only")


if __name__ == "__main__":
    unittest.main()
