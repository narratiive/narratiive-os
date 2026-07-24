from __future__ import annotations

import unittest

from runtime.mission_control import ConnectionStatus, MissionControlSnapshot, WorkstreamStatus
from runtime.tony_command_service import CommandResponse
from runtime.tony_executive_commands import TonyExecutiveCommandService


class StubCommandService:
    def __init__(self, loader=None) -> None:
        self.mission_control_loader = loader
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
                workstream_id="briefing",
                title="Executive briefing",
                state="functional",
                owner="Tony",
                next_action="Validate live command routing",
                evidence=("commit:dda5cd6",),
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


class TonyExecutiveCommandServiceTests(unittest.TestCase):
    def test_morning_command_builds_evidence_backed_brief(self):
        base = StubCommandService(snapshot)
        service = TonyExecutiveCommandService(base)

        response = service.execute("/morning", [])

        self.assertEqual(response.command, "morning")
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["period"], "morning")
        self.assertEqual(len(response.data["priorities"]), 2)
        self.assertIn("Morning brief", response.message)
        self.assertEqual(base.calls, [])

    def test_evening_command_separates_completed_and_open_work(self):
        base = StubCommandService(snapshot)
        service = TonyExecutiveCommandService(base)

        response = service.execute("/evening", [])

        self.assertEqual(response.command, "evening")
        self.assertEqual(response.data["period"], "evening")
        self.assertEqual(len(response.data["completed"]), 1)
        self.assertEqual(len(response.data["open_items"]), 1)
        self.assertIn("End-of-day review", response.message)

    def test_command_aliases_resolve_to_canonical_periods(self):
        base = StubCommandService(snapshot)
        service = TonyExecutiveCommandService(base)

        morning = service.execute("/standup", [])
        evening = service.execute("/end_of_day", [])

        self.assertEqual(morning.command, "morning")
        self.assertEqual(evening.command, "evening")

    def test_non_executive_commands_delegate_without_duplication(self):
        base = StubCommandService(snapshot)
        service = TonyExecutiveCommandService(base)

        response = service.execute("/health", [{"id": "one"}])

        self.assertEqual(response.command, "delegated")
        self.assertEqual(base.calls, [("/health", [{"id": "one"}])])

    def test_missing_mission_control_fails_closed(self):
        service = TonyExecutiveCommandService(StubCommandService())

        response = service.execute("/morning", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "mission_control_unavailable")

    def test_untrusted_snapshot_fails_closed(self):
        def broken_loader():
            raise ValueError("invalid snapshot")

        service = TonyExecutiveCommandService(StubCommandService(broken_loader))

        response = service.execute("/evening", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "executive_brief_untrusted")
        self.assertIn("invalid snapshot", response.message)


if __name__ == "__main__":
    unittest.main()
