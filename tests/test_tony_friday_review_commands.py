from __future__ import annotations

import unittest
from datetime import datetime

from runtime.tony_command_service import CommandResponse
from runtime.tony_executive_commands import TonyExecutiveCommandService


class StubCommandService:
    mission_control_loader = None
    github_configured = False

    def __init__(self):
        self.calls = []

    def execute(self, command, objects):
        self.calls.append((command, list(objects)))
        return CommandResponse("delegated", "healthy", "delegated", {})


class TonyFridayReviewCommandTests(unittest.TestCase):
    def setUp(self):
        self.base = StubCommandService()
        self.service = TonyExecutiveCommandService(
            self.base,
            clock=lambda: datetime.fromisoformat("2026-07-24T18:00:00+01:00"),
        )
        self.records = [{
            "record_id": "commit-1",
            "occurred_at": "2026-07-23T09:00:00+01:00",
            "record_type": "completed",
            "summary": "Unified Tony command surface merged",
            "evidence": ["commit:8bead45"],
            "workspace_id": "narratiive",
        }]

    def test_friday_command_returns_evidence_backed_review(self):
        response = self.service.execute("/friday", self.records)
        self.assertEqual(response.command, "friday_review")
        self.assertEqual(response.status, "healthy")
        self.assertIn("Unified Tony command surface merged", response.message)
        self.assertEqual(response.data["completed_outputs"], ["Unified Tony command surface merged — commit:8bead45"])
        self.assertEqual(self.base.calls, [])

    def test_aliases_resolve_to_friday_review(self):
        for command in ("/weekly_review", "/executive_review", "/friday_review"):
            with self.subTest(command=command):
                self.assertEqual(self.service.execute(command, self.records).command, "friday_review")

    def test_malformed_record_fails_closed(self):
        response = self.service.execute("/friday", [{"summary": "missing evidence fields"}])
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "friday_review_untrusted")

    def test_non_review_command_still_delegates(self):
        response = self.service.execute("/health", [{"id": "one"}])
        self.assertEqual(response.command, "delegated")
        self.assertEqual(self.base.calls, [("/health", [{"id": "one"}])])


if __name__ == "__main__":
    unittest.main()
