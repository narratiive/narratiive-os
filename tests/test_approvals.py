import tempfile
import unittest
from pathlib import Path

from runtime.approvals import ApprovalConflict, ApprovalStatus
from runtime.command_api import RuntimeCommandAPI
from runtime.composition import compose_local_runtime
from runtime.definitions import StageDefinition, WorkflowDefinition
from runtime.models import ArtifactRef, WorkflowStatus
from runtime.revision_graph import (
    RevisionCategory,
    RevisionIssue,
    RevisionOwner,
    RevisionSeverity,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STAGES = (
    "research_analyst",
    "strategy_director",
    "campaign_world_generator",
    "creative_director",
    "quality_reviewer",
)


class ApprovalRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = compose_local_runtime(
            Path(self.tmp.name) / "runtime",
            REPOSITORY_ROOT,
        )
        self.definition = WorkflowDefinition(
            workflow_id="client_ready_pipeline",
            stages=tuple(
                StageDefinition(stage_id, f"agents/{stage_id}.md")
                for stage_id in STAGES
            ),
            approval_required=True,
        )
        self._complete_for_review("run-1")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _complete_for_review(self, run_id: str) -> None:
        self.runtime.run_service.create_run(self.definition, run_id, ())
        for stage_id in STAGES:
            self.runtime.run_service.start_stage(run_id, stage_id)
            self.runtime.run_service.complete_stage(
                run_id,
                stage_id,
                [
                    ArtifactRef(
                        artifact_id=f"{run_id}-{stage_id}",
                        artifact_type=f"completed_{stage_id}",
                        location=f"artifacts/{run_id}/{stage_id}.md",
                    )
                ],
            )

    def test_client_ready_completion_waits_in_approval_queue(self) -> None:
        state = self.runtime.run_repository.load("run-1")
        queue = self.runtime.approval_service.queue()

        self.assertEqual(state.status, WorkflowStatus.AWAITING_APPROVAL)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0].status, ApprovalStatus.PENDING)
        self.assertEqual(queue[0].stage_id, "quality_reviewer")
        self.assertTrue(queue[0].requested_at)

    def test_approval_records_identity_timestamp_and_rationale(self) -> None:
        result = self.runtime.approval_service.approve(
            "run-1",
            "cmd-approve-1",
            "reviewer@example.com",
            "Quality and evidence are ready for the client.",
        )

        self.assertEqual(result.record.status, ApprovalStatus.APPROVED)
        self.assertEqual(result.record.reviewer_id, "reviewer@example.com")
        self.assertTrue(result.record.decided_at)
        self.assertEqual(
            result.record.rationale,
            "Quality and evidence are ready for the client.",
        )
        self.assertEqual(
            self.runtime.run_repository.load("run-1").status,
            WorkflowStatus.COMPLETE,
        )

    def test_comments_and_block_decision_are_immutable_events(self) -> None:
        self.runtime.approval_service.comment(
            "run-1",
            "cmd-comment-1",
            "reviewer@example.com",
            "Legal needs to confirm the evidence wording.",
        )
        result = self.runtime.approval_service.block(
            "run-1",
            "cmd-block-1",
            "reviewer@example.com",
            "Waiting for legal confirmation.",
        )

        self.assertEqual(result.record.status, ApprovalStatus.BLOCKED)
        self.assertEqual(len(result.record.comments), 1)
        self.assertEqual(
            result.record.comments[0].comment,
            "Legal needs to confirm the evidence wording.",
        )
        event_types = [
            event.event_type
            for event in self.runtime.event_log.read("run-1")
            if event.event_type.startswith("approval.")
        ]
        self.assertEqual(
            event_types,
            [
                "approval.requested",
                "approval.comment_added",
                "approval.blocked",
            ],
        )

    def test_revision_decision_routes_through_stack_18(self) -> None:
        issue = RevisionIssue(
            revision_id="revision-approval-1",
            run_id="run-1",
            source_stage_id="quality_reviewer",
            category=RevisionCategory.CREATIVE,
            severity=RevisionSeverity.MAJOR,
            reason="The production direction is ambiguous.",
            owner=RevisionOwner.CREATIVE_DIRECTOR,
        )

        result = self.runtime.approval_service.revise(
            issue,
            "cmd-revise-1",
            "reviewer@example.com",
            "Creative direction must be revised before release.",
        )
        state = self.runtime.run_repository.load("run-1")

        self.assertEqual(result.record.status, ApprovalStatus.REVISION_REQUESTED)
        self.assertEqual(result.record.revision_id, "revision-approval-1")
        self.assertEqual(result.revision_plan.owner_stage_id, "creative_director")
        self.assertEqual(
            result.revision_plan.invalidated_stage_ids,
            ("creative_director", "quality_reviewer"),
        )
        self.assertEqual(state.current_stage_id, "creative_director")
        self.assertEqual(state.status, WorkflowStatus.ACTIVE)
        self.assertIn(
            "revision.requested",
            [event.event_type for event in self.runtime.event_log.read("run-1")],
        )

    def test_duplicate_commands_are_idempotent(self) -> None:
        first = self.runtime.approval_service.approve(
            "run-1",
            "cmd-approve-duplicate",
            "reviewer@example.com",
            "Approved.",
        )
        second = self.runtime.approval_service.approve(
            "run-1",
            "cmd-approve-duplicate",
            "reviewer@example.com",
            "Approved.",
        )

        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        decisions = [
            event
            for event in self.runtime.event_log.read("run-1")
            if event.event_type == "approval.approved"
        ]
        self.assertEqual(len(decisions), 1)

        with self.assertRaises(ApprovalConflict):
            self.runtime.approval_service.block(
                "run-1",
                "cmd-approve-duplicate",
                "reviewer@example.com",
                "Blocked instead.",
            )

    def test_tony_n8n_command_api_exposes_queue_comment_and_approval(self) -> None:
        api = RuntimeCommandAPI(self.runtime)
        listed = api.handle({"command": "approvals.list"})
        commented = api.handle(
            {
                "command": "approvals.comment",
                "run_id": "run-1",
                "command_id": "cmd-api-comment",
                "reviewer_id": "tony-reviewer",
                "comment": "Ready for final decision.",
            }
        )
        approved = api.handle(
            {
                "command": "approvals.approve",
                "run_id": "run-1",
                "command_id": "cmd-api-approve",
                "reviewer_id": "tony-reviewer",
                "rationale": "Approved through the command gateway.",
            }
        )
        fetched = api.handle(
            {"command": "approvals.get", "run_id": "run-1"}
        )

        self._complete_for_review("run-2")
        blocked = api.handle(
            {
                "command": "approvals.block",
                "run_id": "run-2",
                "command_id": "cmd-api-block",
                "reviewer_id": "tony-reviewer",
                "rationale": "Client evidence is not releasable.",
            }
        )

        self._complete_for_review("run-3")
        revised = api.handle(
            {
                "command": "approvals.revise",
                "run_id": "run-3",
                "command_id": "cmd-api-revise",
                "reviewer_id": "tony-reviewer",
                "rationale": "Creative direction needs another pass.",
                "revision": {
                    "revision_id": "revision-api-1",
                    "run_id": "run-3",
                    "source_stage_id": "quality_reviewer",
                    "category": "creative",
                    "severity": "major",
                    "reason": "Creative direction needs another pass.",
                    "owner": "creative_director",
                    "affected_artifact_ids": [],
                    "blocking": False,
                },
            }
        )

        self.assertEqual(listed["data"]["count"], 1)
        self.assertEqual(
            commented["data"]["approval"]["comments"][0]["reviewer_id"],
            "tony-reviewer",
        )
        self.assertEqual(
            approved["data"]["approval"]["status"],
            "approved",
        )
        self.assertEqual(fetched["data"]["current"]["status"], "approved")
        self.assertEqual(blocked["data"]["approval"]["status"], "blocked")
        self.assertEqual(
            revised["data"]["revision_plan"]["owner_stage_id"],
            "creative_director",
        )


if __name__ == "__main__":
    unittest.main()
