from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from openclaw.tony_live_bridge import load_friday_review_records
from runtime.tony_command_service import CommandResponse
from runtime.tony_executive_commands import TonyExecutiveCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("delegated", "healthy", "delegated", {})


class FridayReviewLiveEvidenceTests(unittest.TestCase):
    def test_friday_review_fails_closed_without_dedicated_loader(self):
        service = TonyExecutiveCommandService(StubCommandService())

        response = service.execute("/friday", [{"id": "growth-object"}])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "friday_review_unavailable")

    def test_friday_review_uses_dedicated_records_not_growth_objects(self):
        record = {
            "record_id": "review-1",
            "occurred_at": "2026-07-24T12:00:00Z",
            "record_type": "completed",
            "summary": "Mission Control command path validated",
            "evidence": ["commit:abc123"],
            "workspace_id": "narratiive",
            "theme": "reliability",
        }
        service = TonyExecutiveCommandService(
            StubCommandService(),
            friday_record_loader=lambda: [record],
            clock=lambda: datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc),
        )

        response = service.execute("/friday", [{"id": "growth-object"}])

        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.command, "friday_review")
        self.assertIn("Mission Control command path validated", response.message)

    def test_loader_accepts_complete_explicit_review_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = {
                "record_id": "review-1",
                "occurred_at": "2026-07-24T12:00:00Z",
                "record_type": "completed",
                "summary": "Tony live bridge validated",
                "evidence": ["commit:def456"],
                "workspace_id": "narratiive",
            }
            (root / "records.json").write_text(
                json.dumps([valid]),
                encoding="utf-8",
            )

            records = load_friday_review_records(root)

        self.assertEqual(records, [valid])

    def test_loader_fails_closed_when_store_is_missing_or_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "contains no JSON records"):
                load_friday_review_records(root)
            with self.assertRaisesRegex(FileNotFoundError, "unavailable"):
                load_friday_review_records(root / "missing")

    def test_loader_fails_closed_on_malformed_or_unrelated_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "broken.json").write_text("{not-json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unreadable"):
                load_friday_review_records(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "growth-object.json").write_text(
                json.dumps({"id": "growth-object", "object_type": "campaign"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "record is invalid"):
                load_friday_review_records(root)

    def test_live_service_reports_untrusted_when_configured_store_fails(self):
        service = TonyExecutiveCommandService(
            StubCommandService(),
            friday_record_loader=lambda: (_ for _ in ()).throw(
                ValueError("evidence store invalid")
            ),
        )

        response = service.execute("/friday", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "friday_review_untrusted")
        self.assertIn("evidence store invalid", response.message)


if __name__ == "__main__":
    unittest.main()
