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

    def test_loader_accepts_only_explicit_review_records(self):
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
                json.dumps([valid, {"id": "growth-object", "object_type": "campaign"}]),
                encoding="utf-8",
            )
            (root / "broken.json").write_text("{not-json", encoding="utf-8")

            records = load_friday_review_records(root)

        self.assertEqual(records, [valid])


if __name__ == "__main__":
    unittest.main()
