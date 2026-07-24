from __future__ import annotations

import unittest
from pathlib import Path

from runtime.mission_control import MissionControlBuilder, WorkstreamStatus
from runtime.progress_engine import RepositoryProgressEngine
from runtime.repository_validator import GrowthObjectValidator
from runtime.tony_command_service import TonyCommandService


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "shared" / "growth-object.schema.json"


def object_record() -> dict[str, object]:
    return {
        "id": "growth_specification:rave:launch",
        "object_type": "growth_specification",
        "version": "1.0",
        "client_id": "rave",
        "client_name": "Rave Coffee",
        "campaign_id": "launch",
        "campaign_name": "National Growth",
        "status": "approved",
        "created_at": "2026-07-22T20:00:00Z",
        "updated_at": "2026-07-22T20:00:00Z",
        "created_by": "tony",
        "approved_by": "matt",
        "approved_at": "2026-07-22T21:00:00Z",
        "parent_object_id": None,
        "source_object_ids": [],
        "child_object_ids": [],
        "repository_path": "clients/rave/launch/growth_specification.json",
        "commit_sha": None,
    }


class TonyMissionControlCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        validator = GrowthObjectValidator.from_path(SCHEMA_PATH)
        cls.progress_engine = RepositoryProgressEngine(validator)

    def snapshot(self):
        progress = self.progress_engine.build_snapshot([object_record()])
        return MissionControlBuilder().build(
            generated_at="2026-07-24T05:00:00Z",
            progress=progress,
            workstreams=(
                WorkstreamStatus(
                    workstream_id="tony-runtime",
                    title="Tony runtime",
                    state="functional",
                    owner="Tony",
                    next_action="Deploy latest runtime revision",
                ),
            ),
            connections={"telegram": {"state": "connected", "evidence": "n8n webhook"}},
            approvals_required=(),
        )

    def test_mission_returns_operator_snapshot(self):
        service = TonyCommandService(self.progress_engine, mission_control_loader=self.snapshot)
        response = service.execute("/mission", [])
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.command, "mission")
        self.assertEqual(response.data["summary"]["active_workstreams"], 1)
        self.assertEqual(response.data["connections"][0]["name"], "telegram")

    def test_brief_is_alias_for_mission_control(self):
        service = TonyCommandService(self.progress_engine, mission_control_loader=self.snapshot)
        response = service.execute("/brief", [])
        self.assertEqual(response.status, "healthy")
        self.assertIn("Mission Control", response.message)

    def test_mission_requires_configuration(self):
        service = TonyCommandService(self.progress_engine)
        response = service.execute("/mission", [])
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "mission_control_unavailable")

    def test_loader_failure_is_explicit(self):
        def broken_loader():
            raise RuntimeError("state source unavailable")

        service = TonyCommandService(self.progress_engine, mission_control_loader=broken_loader)
        response = service.execute("/mission_control", [])
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "mission_control_untrusted")
        self.assertIn("state source unavailable", response.message)

    def test_health_reports_mission_control_configuration(self):
        service = TonyCommandService(self.progress_engine, mission_control_loader=self.snapshot)
        response = service.execute("/health", [object_record()])
        self.assertTrue(response.data["mission_control_configured"])


if __name__ == "__main__":
    unittest.main()
