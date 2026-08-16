from __future__ import annotations

import unittest

from runtime.mission_control import ConnectionStatus, MissionControlSnapshot, WorkstreamStatus
from runtime.tony_command_service import CommandResponse
from runtime.tony_executive_commands import TonyExecutiveCommandService


class StubCommandService:
    def __init__(self, loader=None) -> None:
        self.mission_control_loader = loader
        self.github_configured = False
        self.calls: list[tuple[str, list[dict[str, object]]]] = []

    def execute(self, command, objects):
        records = list(objects)
        self.calls.append((command, records))
        return CommandResponse("delegated", "healthy", "delegated", {"records": records})


def snapshot() -> MissionControlSnapshot:
    return MissionControlSnapshot(
        generated_at="2026-07-24T10:00:00Z",
        status="healthy",
        progress={"status": "healthy"},
        workstreams=(
            WorkstreamStatus(
                workstream_id="outreach",
                title="Founder outreach",
                state="functional",
                owner="Tony",
                next_action="Send five tailored introductions",
                evidence=("crm:outreach",),
            ),
            WorkstreamStatus(
                workstream_id="mission-control",
                title="Mission Control",
                state="tested",
                owner="Tony",
                next_action="Use the recorded snapshot",
                evidence=("commit:61ed83d",),
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


def executive_service(base, **kwargs) -> TonyExecutiveCommandService:
    """Build an isolated executive-command service for unit tests.

    These tests exercise command behaviour, not the machine's live inbound-lead
    store. Supplying an explicit empty lead loader keeps local runtime data from
    changing deterministic unit-test outcomes.
    """
    return TonyExecutiveCommandService(base, inbound_lead_loader=lambda: (), **kwargs)


class TonyExecutiveCommandServiceTests(unittest.TestCase):
    def test_morning_command_builds_agency_first_brief(self):
        base = StubCommandService(snapshot)
        service = executive_service(base)

        response = service.execute("/morning", [])

        self.assertEqual(response.command, "morning")
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["period"], "morning")
        self.assertIn("Morning agency brief", response.message)
        self.assertIn("Commercial:", response.message)
        self.assertIn("Founder outreach", response.message)
        self.assertNotIn("Mission Control —", response.message)
        self.assertIn("agency_state", response.data)
        self.assertEqual(base.calls, [])

    def test_evening_command_uses_agency_renderer(self):
        service = executive_service(StubCommandService(snapshot))

        response = service.execute("/evening", [])

        self.assertEqual(response.command, "evening")
        self.assertEqual(response.data["period"], "evening")
        self.assertIn("End-of-day agency review", response.message)
        self.assertIn("Commercial:", response.message)

    def test_command_aliases_resolve_to_canonical_periods(self):
        service = executive_service(StubCommandService(snapshot))

        morning = service.execute("/standup", [])
        evening = service.execute("/end_of_day", [])

        self.assertEqual(morning.command, "morning")
        self.assertEqual(evening.command, "evening")

    def test_non_executive_commands_delegate_without_duplication(self):
        base = StubCommandService(snapshot)
        service = executive_service(base)

        response = service.execute("/health", [{"id": "one"}])

        self.assertEqual(response.command, "delegated")
        self.assertEqual(base.calls, [("/health", [{"id": "one"}])])

    def test_missing_mission_control_fails_closed(self):
        service = executive_service(StubCommandService())

        response = service.execute("/morning", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "mission_control_unavailable")

    def test_untrusted_snapshot_fails_closed(self):
        def broken_loader():
            raise ValueError("invalid snapshot")

        service = executive_service(StubCommandService(broken_loader))
        response = service.execute("/evening", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "executive_brief_untrusted")
        self.assertIn("invalid snapshot", response.message)

    def test_successful_brief_preserves_legacy_archive(self):
        class RecordingArchive:
            def __init__(self):
                self.briefs = []

            def store(self, brief):
                self.briefs.append(brief)

        archive = RecordingArchive()
        service = executive_service(
            StubCommandService(snapshot),
            brief_archive=archive,
        )

        response = service.execute("/morning", [])

        self.assertEqual(response.status, "healthy")
        self.assertEqual(len(archive.briefs), 1)
        self.assertEqual(archive.briefs[0].period.value, "morning")

    def test_archive_failure_fails_closed(self):
        class BrokenArchive:
            def store(self, brief):
                raise ValueError("archive integrity failure")

        service = executive_service(
            StubCommandService(snapshot),
            brief_archive=BrokenArchive(),
        )
        response = service.execute("/morning", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "executive_brief_untrusted")
        self.assertIn("archive integrity failure", response.message)

    def test_github_unavailable_does_not_replace_agency_brief(self):
        base = StubCommandService(snapshot)
        base.github_configured = True
        service = executive_service(base)

        response = service.execute("/morning", [])

        self.assertEqual(response.status, "healthy")
        self.assertIn("Founder outreach", response.message)
        self.assertNotIn("GitHub state is unavailable", response.message)


if __name__ == "__main__":
    unittest.main()
