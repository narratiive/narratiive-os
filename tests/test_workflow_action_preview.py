from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.tony_command_service import CommandResponse
from runtime.tony_workflow_commands import FileWorkflowCommandBackend, TonyWorkflowCommandService
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from tests.test_tony_internal_review_delivery import blueprint_output
from tests.test_workflow_quality import discovery_output, proposal_output


class Fallback:
    def execute(self, command, objects):
        return CommandResponse("fallback", "healthy", "fallback", {})


def lifecycle(client_id: str) -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id=client_id,
        client_name="SAFE KatKin",
        stage=ClientLifecycleStage.RESEARCH,
        owner="Tony",
        next_action="Continue authorised internal work.",
        evidence=("synthetic:test",),
    )


class WorkflowActionPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.gmail_calls: list[dict] = []

        def gmail(contract):
            self.gmail_calls.append(contract)
            index = len(self.gmail_calls)
            return {"verified": True, "sent": True, "message_id": f"gmail-{index}", "thread_id": f"thread-{index}"}

        def claude(contract):
            workflow_id = contract.get("target", {}).get("workflow_context", {}).get("workflow_id")
            if workflow_id == "growth_diagnostic_to_blueprint_lite":
                return blueprint_output()
            if workflow_id == "blueprint_lite_to_discovery_preparation":
                return discovery_output()
            if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
                return proposal_output()
            raise AssertionError(workflow_id)

        self.dispatchers = {"Claude": claude, "Gmail": gmail}
        self.runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="narratiive",
            client_id="safe-katkin",
            dispatchers=self.dispatchers,
            environ={},
        )
        self.runtime.enqueue(
            "growth_diagnostic_to_blueprint_lite",
            "safe-katkin-run",
            {
                "diagnostic_input_package": {"overall_score": 40},
                "company": "KatKin",
                "commercial_context": {"company": "KatKin"},
            },
            entity_id="safe-katkin",
            correlation_id="safe-katkin",
        )
        self.service = TonyWorkflowCommandService(
            Fallback(),
            FileWorkflowCommandBackend(self.root, dispatchers=self.dispatchers, environ={}),
        )
        self.runtime.advance("safe-katkin-run", lifecycle("safe-katkin"))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _proposal_run(self) -> str:
        token = self.service.execute("/workflow safe-katkin-run", []).data["approval_token"]
        self.service.execute(
            "/approve safe-katkin-run because approved Blueprint Lite",
            [], principal_id="telegram:123", inputs={"approval_token": token},
        )
        discovery = self.service.execute("/continue safe-katkin-run", []).data["run_id"]
        token = self.service.execute(f"/workflow {discovery}", []).data["approval_token"]
        self.service.execute(
            f"/approve {discovery} because approved Discovery preparation",
            [], principal_id="telegram:123", inputs={"approval_token": token},
        )
        return self.service.execute(
            f"/continue {discovery}",
            [],
            inputs={
                "discovery_evidence": {
                    "notes": "SAFE discovery evidence.",
                    "sources": [{"source_id": "safe", "source_type": "notes", "location": "safe:test"}],
                }
            },
        ).data["run_id"]

    def test_artifact_detail_preview_and_digest_bound_exactly_once_send(self):
        run_id = self._proposal_run()
        review = self.service.execute(f"/deliver-review {run_id}", [])
        self.assertTrue(review.data["delivered"])
        token = self.service.execute(f"/workflow {run_id}", []).data["approval_token"]
        self.service.execute(
            f"/approve {run_id} because approved Growth Sprint proposal",
            [], principal_id="telegram:123", inputs={"approval_token": token},
        )

        detail = self.service.execute(f"/artifact-detail {run_id}", [])
        missing_mode = self.service.execute(f"/action-preview {run_id}", [])
        preview = self.service.execute(
            f"/action-preview {run_id}",
            [],
            inputs={"simulation_mode": True, "delivery_override": "hello@narratiive.com"},
        )

        self.assertEqual(detail.data["approval_status"], "approved")
        self.assertEqual(missing_mode.data["error_code"], "simulation_mode_required")
        self.assertTrue(detail.data["draft_client_communication"])
        self.assertTrue(detail.data["commercial_proposal_inputs"])
        self.assertEqual(detail.data["human_review_artifact"]["mime_type"], "application/pdf")
        self.assertTrue(preview.data["simulation_mode"])
        self.assertEqual(preview.data["intended_client"], "KatKin")
        self.assertEqual(preview.data["delivery_override"], "hello@narratiive.com")
        self.assertEqual(preview.data["recipient_email"], "hello@narratiive.com")
        self.assertEqual(preview.data["source_artifact_version"], "v1")
        self.assertTrue(preview.data["full_body"])
        self.assertNotIn("[Founder name]", preview.data["full_body"])
        self.assertNotIn("DRAFT — INTERNAL", preview.data["full_body"])
        self.assertTrue(preview.data["attachments"][0]["filename"].endswith(".pdf"))

        stale = self.service.execute(
            f"/execute-action {run_id} because Matt approved the displayed simulation",
            [], principal_id="telegram:123", inputs={"action_digest": "0" * 64},
        )
        self.assertEqual(stale.status, "error")
        sent = self.service.execute(
            f"/execute-action {run_id} because Matt approved the displayed simulation",
            [], principal_id="telegram:123", inputs={"action_digest": preview.data["action_digest"]},
        )
        restarted = TonyWorkflowCommandService(
            Fallback(),
            FileWorkflowCommandBackend(self.root, dispatchers=self.dispatchers, environ={}),
        )
        replay = restarted.execute(
            f"/execute-action {run_id} because retry after restart",
            [], principal_id="telegram:123", inputs={"action_digest": preview.data["action_digest"]},
        )

        self.assertEqual(sent.data["execution_truth"], "verified_executed")
        self.assertEqual(sent.data["message_id"], "gmail-2")
        self.assertTrue(replay.data["duplicate_suppressed"])
        self.assertEqual(len(self.gmail_calls), 2)
        send_payload = self.gmail_calls[1]["payload"]
        self.assertEqual(send_payload["recipient_email"], "hello@narratiive.com")
        self.assertEqual(send_payload["body"], preview.data["full_body"])
        self.assertTrue(base64.b64decode(send_payload["attachments"][0]["content_base64"]).startswith(b"%PDF"))
        state = self.runtime.runs.load_run(run_id)
        self.assertNotEqual(state.input_payload.get("contact_email"), "hello@narratiive.com")


if __name__ == "__main__":
    unittest.main()
