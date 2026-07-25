from __future__ import annotations

import unittest
from dataclasses import replace

from runtime.mission_control import ConnectionStatus, MissionControlSnapshot, WorkstreamStatus
from runtime.terminology_policy import TerminologyPolicy
from runtime.tony_command_service import CommandResponse
from runtime.tony_executive_commands import TonyExecutiveCommandService


class StubCommandService:
    def __init__(self, loader) -> None:
        self.mission_control_loader = loader
        self.github_configured = False

    def execute(self, command, objects):
        return CommandResponse("delegated", "healthy", "delegated", {})


def snapshot() -> MissionControlSnapshot:
    return MissionControlSnapshot(
        generated_at="2026-07-25T15:00:00Z",
        status="healthy",
        progress={"status": "healthy"},
        workstreams=(
            WorkstreamStatus(
                workstream_id="briefing",
                title="Executive briefing",
                state="functional",
                owner="Tony",
                next_action="Validate canonical language",
                evidence=("commit:test",),
            ),
        ),
        connections=(
            ConnectionStatus(
                name="telegram-bridge",
                state="connected",
                evidence="health check passed",
            ),
        ),
        approvals_required=(),
        blockers=(),
    )


def policy() -> TerminologyPolicy:
    return TerminologyPolicy(
        {
            "status": "active",
            "version": "2026.07-test",
            "approved_terms": [
                {"term": "Growth Blueprint", "use": "Canonical product name."}
            ],
            "unsettled_terms": [],
            "retired_terms": [
                {
                    "term": "strategy session",
                    "replacement": "Growth Blueprint",
                    "rationale": "Retired commercial language.",
                }
            ],
        }
    )


class TonyExecutiveTerminologyTests(unittest.TestCase):
    def test_daily_brief_reports_the_canonical_policy_version(self):
        service = TonyExecutiveCommandService(
            StubCommandService(snapshot),
            terminology_policy_loader=policy,
        )

        response = service.execute("/morning", [])

        self.assertEqual(response.status, "healthy")
        self.assertEqual(
            response.data["terminology_policy_version"], "2026.07-test"
        )

    def test_retired_language_fails_closed_before_archive(self):
        base_snapshot = snapshot()
        unsafe_workstream = replace(
            base_snapshot.workstreams[0],
            title="Strategy session",
        )
        unsafe_snapshot = replace(base_snapshot, workstreams=(unsafe_workstream,))

        class RecordingArchive:
            def __init__(self) -> None:
                self.briefs = []

            def store(self, brief) -> None:
                self.briefs.append(brief)

        archive = RecordingArchive()
        service = TonyExecutiveCommandService(
            StubCommandService(lambda: unsafe_snapshot),
            brief_archive=archive,
            terminology_policy_loader=policy,
        )

        response = service.execute("/morning", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "executive_brief_untrusted")
        self.assertIn("strategy session", response.message.lower())
        self.assertEqual(archive.briefs, [])

    def test_unavailable_policy_fails_closed(self):
        def broken_policy_loader():
            raise ValueError("policy checksum mismatch")

        service = TonyExecutiveCommandService(
            StubCommandService(snapshot),
            terminology_policy_loader=broken_policy_loader,
        )

        response = service.execute("/evening", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "executive_brief_untrusted")
        self.assertIn("policy checksum mismatch", response.message)


if __name__ == "__main__":
    unittest.main()
