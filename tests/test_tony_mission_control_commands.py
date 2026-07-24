from __future__ import annotations

import unittest
from pathlib import Path

from runtime.github_work import GitHubWorkItem, GitHubWorkSnapshot
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
        pull = GitHubWorkItem(
            kind="pull_request",
            number=66,
            title="GitHub awareness",
            url="https://github.test/pull/66",
            state="open",
            author="codex",
            created_at="2026-07-24T04:00:00Z",
            updated_at="2026-07-24T05:00:00Z",
            head_sha="abc",
            requested_reviewers=("matt",),
        )
        github = GitHubWorkSnapshot(
            repository="narratiive/narratiive-os",
            workspace_id="agency",
            observed_at="2026-07-24T05:00:00Z",
            baseline_status="unavailable",
            baseline_artifact_id="",
            open_pull_requests=(pull,),
            active_issues=(),
            blocked=(),
            matt_approval_required=(pull,),
            changes_since_previous_brief=(),
        )
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
            connections={
                "telegram": {"state": "connected", "evidence": "n8n webhook"},
                "GitHub": {"state": "connected", "evidence": "api observation"},
            },
            approvals_required=(),
            github_work=github,
        )

    def test_mission_returns_operator_snapshot(self):
        service = TonyCommandService(self.progress_engine, mission_control_loader=self.snapshot)
        response = service.execute("/mission", [])
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.command, "mission")
        self.assertEqual(response.data["summary"]["active_workstreams"], 1)
        self.assertEqual(
            [item["name"] for item in response.data["connections"]],
            ["GitHub", "telegram"],
        )

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

    def test_github_returns_live_repository_work(self):
        service = TonyCommandService(
            self.progress_engine,
            mission_control_loader=self.snapshot,
            github_configured=True,
        )

        response = service.execute("/github", [])

        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["summary"]["open_pull_requests"], 1)
        self.assertEqual(response.data["matt_approval_required"][0]["number"], 66)

    def test_github_fails_closed_when_snapshot_is_unavailable(self):
        progress = self.progress_engine.build_snapshot([object_record()])

        def unavailable():
            return MissionControlBuilder().build(
                generated_at="2026-07-24T05:00:00Z",
                progress=progress,
                connections={
                    "GitHub": {
                        "state": "degraded",
                        "evidence": "HTTP 403",
                    }
                },
            )

        service = TonyCommandService(
            self.progress_engine,
            mission_control_loader=unavailable,
            github_configured=True,
        )

        response = service.execute("/github", [])

        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "github_unavailable")
        self.assertEqual(response.data["connection_state"], "degraded")


if __name__ == "__main__":
    unittest.main()
