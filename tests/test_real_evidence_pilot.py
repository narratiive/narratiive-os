from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runtime.models import ArtifactRef, StageStatus, WorkflowStatus
from runtime.real_evidence_pilot import (
    PILOT_APPROVAL_GATES,
    PILOT_WORKFLOWS,
    PilotAuditLedger,
    PilotManifest,
    PilotValidationError,
    inspect_pilot,
)
from runtime.workflow_registry import build_narratiive_workflow_registry


def manifest_payload() -> dict:
    return {
        "schema_version": 1,
        "pilot_id": "safe-real-evidence-pilot-001",
        "workspace_id": "agency",
        "client_id": "safe-real-evidence-client",
        "label": "AUTHORISED REAL-EVIDENCE PILOT SAFE TEST ONLY",
        "synthetic_contact_email": "safe-real-evidence-pilot@acceptance.invalid",
        "authorisation": {
            "status": "approved",
            "approved_by": "authorised-test-owner",
            "approved_at": "2026-09-05T12:00:00Z",
            "purpose": "Validate one controlled Narratiive production journey safely.",
        },
        "external_actions_allowed": False,
        "workflow_ids": list(PILOT_WORKFLOWS),
        "approval_gates": list(PILOT_APPROVAL_GATES),
        "evidence_sources": [
            {
                "source_id": "safe-authorised-notes",
                "source_type": "notes",
                "location": "private-workspace:discovery-notes",
                "policy": {"approved": True},
                "provenance": {
                    "origin": "authorised synthetic fixture",
                    "captured_at": "2026-09-05T12:00:00Z",
                    "permitted_use": "Narratiive real-evidence pilot only",
                },
            }
        ],
    }


def accepted_state(workflow_id: str, *, awaiting: bool = False):
    definition = build_narratiive_workflow_registry().resolve(workflow_id)
    state = definition.new_state(
        f"safe-{workflow_id}",
        workspace_id="agency",
        client_id="safe-real-evidence-client",
    )
    stage = state.stages[-1]
    stage.status = StageStatus.COMPLETED
    stage.quality_result = {"passed": True, "failed_checks": []}
    stage.output_artifacts.append(
        ArtifactRef(
            artifact_id=f"artifact-{workflow_id}",
            artifact_type="workflow_step_output",
            location=f"/synthetic/{workflow_id}.json",
        )
    )
    state.current_stage_id = None
    if workflow_id in PILOT_APPROVAL_GATES:
        if awaiting:
            state.status = WorkflowStatus.AWAITING_APPROVAL
            state.approval_status = "pending"
            state.proposed_next_action = f"Review {workflow_id}"
        else:
            state.status = WorkflowStatus.COMPLETE
            state.approval_status = "approved"
            state.approval_history.append(
                {
                    "approver": "authorised-test-owner",
                    "rationale": "SAFE internal review",
                    "proposed_next_action": f"Review {workflow_id}",
                }
            )
    else:
        state.status = WorkflowStatus.COMPLETE
    return state


class RealEvidencePilotTests(unittest.TestCase):
    def test_manifest_requires_invalid_contact_authorisation_provenance_and_gates(self):
        manifest = PilotManifest.from_mapping(manifest_payload())
        self.assertEqual(manifest.workflow_ids, PILOT_WORKFLOWS)

        unsafe = manifest_payload()
        unsafe["synthetic_contact_email"] = "real-person@example.com"
        with self.assertRaisesRegex(PilotValidationError, "invalid_domain"):
            PilotManifest.from_mapping(unsafe)

        secret = manifest_payload()
        secret["api_key"] = "must-not-be-accepted"
        with self.assertRaisesRegex(PilotValidationError, "contains_secret_field"):
            PilotManifest.from_mapping(secret)

        ungated = manifest_payload()
        ungated["approval_gates"] = []
        with self.assertRaisesRegex(PilotValidationError, "approval_gates_invalid"):
            PilotManifest.from_mapping(ungated)

    def test_preflight_ledger_is_scoped_append_only_and_idempotent(self):
        manifest = PilotManifest.from_mapping(manifest_payload())
        with tempfile.TemporaryDirectory() as tmp:
            ledger = PilotAuditLedger(tmp)
            first = ledger.record_preflight(manifest)
            replay = ledger.record_preflight(manifest)
            path = Path(first["ledger"])

            self.assertEqual(first["status"], "recorded")
            self.assertEqual(replay["status"], "duplicate_suppressed")
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("company_label", stored)
            self.assertFalse(stored["external_actions_allowed"])

            path.write_text(path.read_text(encoding="utf-8").replace("pilot.preflight_passed", "tampered"), encoding="utf-8")
            with self.assertRaisesRegex(PilotValidationError, "integrity_failed"):
                ledger.record_preflight(manifest)

    def test_acceptance_reports_only_persisted_quality_gates_and_external_action_truth(self):
        manifest = PilotManifest.from_mapping(manifest_payload())
        states = [
            accepted_state(workflow_id, awaiting=workflow_id == "research_to_growth_blueprint")
            for workflow_id in PILOT_WORKFLOWS
        ]

        report = inspect_pilot(manifest, states)

        self.assertTrue(report["ready"])
        self.assertFalse(report["external_action_taken"])
        self.assertEqual(len(report["workflows"]), 5)
        self.assertNotIn("company_label", json.dumps(report))

        states[3].external_action_taken = True
        failed = inspect_pilot(manifest, states)
        self.assertFalse(failed["ready"])
        self.assertTrue(failed["external_action_taken"])

    def test_missing_or_failed_workflow_cannot_pass_acceptance(self):
        manifest = PilotManifest.from_mapping(manifest_payload())
        states = [accepted_state(workflow_id) for workflow_id in PILOT_WORKFLOWS[:-1]]
        states[0].stages[-1].quality_result = {"passed": False}

        report = inspect_pilot(manifest, states)

        self.assertFalse(report["ready"])
        self.assertFalse(report["workflows"][0]["quality_passed"])
        self.assertFalse(report["workflows"][-1]["present"])

    def test_documented_cli_entrypoint_loads(self):
        result = subprocess.run(
            [sys.executable, "scripts/real_evidence_pilot.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("controlled real-evidence", result.stdout)


if __name__ == "__main__":
    unittest.main()
