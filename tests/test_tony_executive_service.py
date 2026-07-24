from __future__ import annotations

import unittest

from runtime.mission_control import (
    ConnectionStatus,
    MissionControlSnapshot,
    WorkstreamStatus,
)
from runtime.tony_command_service import CommandResponse
from runtime.tony_executive_service import TonyExecutiveService


class FakeCommandService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, object]]]] = []

    def execute(self, command, objects):
        materialized = list(objects)
        self.calls.append((command, materialized))
        return CommandResponse(
            command="status",
            status="healthy",
            message="Delegated status.",
            data={"objects": len(materialized)},
        )


def mission_control_snapshot() -> MissionControlSnapshot:
    return MissionControlSnapshot(
        generated_at="2026-07-24T01:00:00Z",
        status="partial",
        progress={"status": "healthy", "campaigns": []},
        workstreams=(
            WorkstreamStatus(
                workstream_id="tony-executive-briefs",
                title="Tony executive briefs",
                state="tested",
                owner="Tony",
                next_action="Connect the brief renderer.",
                evidence=("commit:abc123",),
                last_updated_at="2026-07-24T00:55:00Z",
            ),
        ),
        connections=(
            ConnectionStatus(
                name="notion",
                state="not_connected",
                evidence="No live connector check recorded.",
            ),
        ),
        approvals_required=("Approve canonical proposition wording",),
        blockers=(),
    )


class TonyExecutiveServiceTests(unittest.TestCase):
    def setUp(self):
        self.command_service = FakeCommandService()
        self.service = TonyExecutiveService(self.command_service)

    def test_mission_control_returns_structured_snapshot(self):
        response = self.service.execute(
            "/mission_control",
            [],
            mission_control_snapshot=mission_control_snapshot(),
        )

        self.assertEqual(response.command, "mission_control")
        self.assertEqual(response.status, "partial")
        self.assertEqual(response.data["summary"]["active_workstreams"], 1)
        self.assertEqual(response.data["summary"]["connection_issues"], 1)
        self.assertEqual(response.data["approvals_required"], ["Approve canonical proposition wording"])
        self.assertEqual(self.command_service.calls, [])

    def test_mission_control_aliases_are_supported(self):
        for command in ("/mission", "/overview"):
            with self.subTest(command=command):
                response = self.service.execute(
                    command,
                    [],
                    mission_control_snapshot=mission_control_snapshot(),
                )
                self.assertEqual(response.command, "mission_control")

    def test_missing_snapshot_fails_closed(self):
        response = self.service.execute("/mission_control", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "mission_control_unavailable")
        self.assertEqual(self.command_service.calls, [])

    def test_existing_commands_delegate_without_changed_behaviour(self):
        response = self.service.execute("/status", [{"id": "one"}])

        self.assertEqual(response.message, "Delegated status.")
        self.assertEqual(self.command_service.calls, [("/status", [{"id": "one"}])])

    def test_telegram_reply_uses_compact_mission_control_format(self):
        reply = self.service.telegram_reply(
            "/overview",
            [],
            mission_control_snapshot=mission_control_snapshot(),
        )

        self.assertIn("Mission Control is partial", reply)
        self.assertIn("Approvals:", reply)
        self.assertIn("Next work:", reply)
        self.assertLessEqual(len(reply), 3500)


if __name__ == "__main__":
    unittest.main()
