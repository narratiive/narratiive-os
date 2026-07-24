import unittest

from runtime.mission_control import MissionControlBuilder, WorkstreamStatus
from runtime.mission_control_service import MissionControlService
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationReport


class MissionControlServiceTests(unittest.TestCase):
    @staticmethod
    def progress(status="healthy"):
        return ProgressSnapshot(
            status=status,
            campaigns=(),
            validation=ValidationReport(
                status="pass",
                objects_validated=0,
                errors=(),
                warnings=(),
            ),
        )

    def setUp(self):
        self.builder = MissionControlBuilder()
        self.service = MissionControlService()

    def test_response_exposes_operator_summary_and_full_snapshot(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T00:30:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="runtime",
                    title="Tony runtime",
                    state="tested",
                    owner="Tony",
                    next_action="Run live acceptance",
                ),
            ),
            connections={"GitHub": {"state": "connected"}},
            approvals_required=("approve Rave Campaign World",),
        )
        response = self.service.respond(snapshot)
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["summary"]["active_workstreams"], 1)
        self.assertEqual(response.data["summary"]["approvals_required"], 1)
        self.assertEqual(response.to_dict()["command"], "mission_control")

    def test_telegram_reply_prioritises_blockers_approvals_and_next_work(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T00:30:00Z",
            progress=self.progress(),
            workstreams=(
                WorkstreamStatus(
                    workstream_id="telegram",
                    title="Telegram command path",
                    state="blocked",
                    owner="Tony",
                    next_action="Deploy latest revision",
                    blocker="live_runtime_stale",
                ),
            ),
            approvals_required=("approve deployment",),
        )
        reply = self.service.telegram_reply(snapshot)
        self.assertIn("Blockers:", reply)
        self.assertIn("workstream:telegram:live_runtime_stale", reply)
        self.assertIn("Approvals:", reply)
        self.assertIn("Next work:", reply)
        self.assertIn("Deploy latest revision", reply)

    def test_not_connected_connection_is_counted_as_issue_without_false_blocker(self):
        snapshot = self.builder.build(
            generated_at="2026-07-24T00:30:00Z",
            progress=self.progress(),
            connections={"Google Drive": {"state": "not_connected"}},
        )
        response = self.service.respond(snapshot)
        self.assertEqual(response.status, "partial")
        self.assertEqual(response.data["summary"]["connection_issues"], 1)
        self.assertEqual(response.data["blockers"], [])

    def test_telegram_reply_is_safely_bounded(self):
        workstreams = tuple(
            WorkstreamStatus(
                workstream_id=f"work-{index}",
                title="A" * 900,
                state="known",
                owner="Tony",
                next_action="B" * 900,
            )
            for index in range(6)
        )
        snapshot = self.builder.build(
            generated_at="2026-07-24T00:30:00Z",
            progress=self.progress(),
            workstreams=workstreams,
        )
        reply = self.service.telegram_reply(snapshot)
        self.assertLessEqual(len(reply), self.service.TELEGRAM_LIMIT)
        self.assertTrue(reply.endswith("…"))


if __name__ == "__main__":
    unittest.main()
