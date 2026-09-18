from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from runtime.models import ArtifactRef, StageRecord, WorkflowState, WorkflowStatus
from runtime.workflow_deliverable_persistence import (
    WorkflowDeliverablePersistenceError,
    WorkflowDeliverablePersistenceService,
)


class FakeRuns:
    def __init__(self, state: WorkflowState) -> None:
        self.state = state

    def record_external_action(self, run_id: str, *, idempotency_key: str, receipt: dict) -> None:
        self.state.external_action_receipts.append({"idempotency_key": idempotency_key, "receipt": receipt})


class FakeRuntime:
    def __init__(self, state: WorkflowState) -> None:
        self.runs = FakeRuns(state)


def approved_state(root: Path) -> WorkflowState:
    output_dir = root / "scope" / "deliverables" / "northstar"
    output_dir.mkdir(parents=True)
    pptx = output_dir / "Northstar-Growth-Blueprint.pptx"
    pdf = output_dir / "Northstar-Growth-Blueprint.pdf"
    pptx.write_bytes(b"PK\x03\x04 safe synthetic pptx")
    pdf.write_bytes(b"%PDF-1.7 safe synthetic pdf")
    output = {
        "editable_pptx": str(pptx),
        "review_pdf": str(pdf),
        "visual_qa": {"status": "passed", "checks": {"safe": True}},
    }
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
    artifact_path = root / "scope" / "artifacts" / "artifact.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(encoded + b"\n")
    stage = StageRecord(
        "produce_growth_blueprint_deliverable",
        "",
        output_artifacts=[
            ArtifactRef(
                "artifact-northstar-deliverable",
                "workflow_step_output",
                str(artifact_path),
                hashlib.sha256(encoded).hexdigest(),
            )
        ],
    )
    return WorkflowState(
        "growth_blueprint_deliverable_production",
        "northstar-deliverable-run",
        [stage],
        status=WorkflowStatus.COMPLETE,
        workspace_id="northstar-workspace",
        client_id="northstar-test-co",
        approval_required=True,
        approval_status="approved",
    )


class WorkflowDeliverablePersistenceTests(unittest.TestCase):
    def test_preview_and_exact_approval_persist_two_files_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = approved_state(root)
            calls: list[dict] = []

            def drive(contract):
                calls.append(contract)
                payload = contract["payload"]
                return {
                    "verified": True,
                    "file_id": f"drive-{len(calls)}",
                    "file_url": f"https://drive.invalid/{len(calls)}",
                    "checksum": payload["checksum"],
                    "duplicate_suppressed": False,
                }

            service = WorkflowDeliverablePersistenceService(root, drive)
            preview = service.preview(state, drive_folder_id="verified-folder-1")
            self.assertEqual(len(preview["files"]), 2)
            self.assertEqual(preview["sharing"], "not_authorised")
            self.assertFalse(preview["external_action_taken"])

            with self.assertRaisesRegex(WorkflowDeliverablePersistenceError, "stale"):
                service.execute(
                    FakeRuntime(state),
                    state,
                    drive_folder_id="verified-folder-1",
                    action_digest="0" * 64,
                    approver="telegram:matt",
                    rationale="Approve exact internal persistence",
                )

            result = service.execute(
                FakeRuntime(state),
                state,
                drive_folder_id="verified-folder-1",
                action_digest=preview["action_digest"],
                approver="telegram:matt",
                rationale="Approve exact internal persistence",
            )
            replay = service.execute(
                FakeRuntime(state),
                state,
                drive_folder_id="verified-folder-1",
                action_digest=preview["action_digest"],
                approver="telegram:matt",
                rationale="Retry after restart",
            )

            self.assertEqual(len(calls), 2)
            self.assertTrue(result["external_action_taken"])
            self.assertTrue(replay["duplicate_suppressed"])
            self.assertFalse(replay["external_action_taken"])
            self.assertTrue(all(call["approval_granted"] is True for call in calls))
            self.assertTrue(all(call["payload"]["kind"] == "reviewed_growth_blueprint_file" for call in calls))

    def test_preview_rejects_unapproved_or_out_of_root_deliverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            state = approved_state(root)
            state.approval_status = "pending"
            service = WorkflowDeliverablePersistenceService(root, None)
            with self.assertRaisesRegex(WorkflowDeliverablePersistenceError, "must be approved"):
                service.preview(state, drive_folder_id="folder")

            state.approval_status = "approved"
            output_artifact = state.stages[0].output_artifacts[0]
            output = json.loads(Path(output_artifact.location).read_text(encoding="utf-8"))
            outside_file = Path(outside) / "escaped.pptx"
            outside_file.write_bytes(b"PK\x03\x04 escaped")
            output["editable_pptx"] = str(outside_file)
            encoded = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
            Path(output_artifact.location).write_bytes(encoded + b"\n")
            state.stages[0].output_artifacts[0] = ArtifactRef(
                output_artifact.artifact_id,
                output_artifact.artifact_type,
                output_artifact.location,
                hashlib.sha256(encoded).hexdigest(),
            )
            with self.assertRaisesRegex(WorkflowDeliverablePersistenceError, "outside"):
                service.preview(state, drive_folder_id="folder")


if __name__ == "__main__":
    unittest.main()
