from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.models import StageRecord, StageStatus, WorkflowStatus
from runtime.tony_command_service import CommandResponse
from runtime.tony_workflow_commands import FileWorkflowCommandBackend, TonyWorkflowCommandService
from runtime.tony_workflow_runtime import build_tony_workflow_runtime
from runtime.workflow_handoffs import build_next_workflow_inputs
from runtime.workflow_mission_control import WorkflowMissionControlProjector


def _output(company: str) -> dict:
    return {
        "blueprint_lite": f"A substantive approved manual Blueprint Lite for {company}.",
        "diagnostic_signals_used": ["overall score", "main blockage"],
        "diagnostic_input_coverage": {"complete": True},
        "source_backed_evidence": [
            {"source": "https://example.invalid/evidence", "fact": "SAFE synthetic evidence"}
        ],
        "evidence_gaps": ["Private commercial evidence is unavailable"],
        "fact_interpretation_hypothesis_lineage": {
            "fact": ["SAFE synthetic fact"],
            "interpretation": ["SAFE synthetic interpretation"],
            "hypothesis": ["SAFE synthetic hypothesis"],
        },
        "growth_tension": "Demand exists but the proposition is unclear.",
        "provisional_opportunity": "Clarify the category entry point.",
        "questions_to_answer_next": ["Who buys?", "Why now?", "Why this?"],
        "quality_gate": {"human_review_ready": True, "automated": False},
        "recommendation": "advance to governed Discovery preparation",
    }


def _checksum(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _approval(instruction: str) -> dict:
    return {
        "human_instruction": instruction,
        "human_instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
        "turn_run_id": "safe-current-human-turn",
        "authorisation_reference": "safe-founder-authorisation",
        "verbatim_current_human_instruction_verified": True,
        "explicit_decision_intent": "manual_recovery",
    }


def _lifecycle(client_id: str, company: str) -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id=client_id,
        client_name=company,
        stage=ClientLifecycleStage.BLUEPRINT_LITE,
        owner="Tony",
        next_action="Prepare internal work",
        evidence=("synthetic:test",),
    )


class _Fallback:
    def execute(self, command, objects):
        return CommandResponse("fallback", "healthy", "fallback", {})


class WorkflowManualRecoveryTests(unittest.TestCase):
    def _blocked(self, runtime, run_id: str, entity_id: str, company: str):
        runtime.enqueue(
            "growth_diagnostic_to_blueprint_lite",
            run_id,
            {
                "diagnostic_input_package": {"overall_score": 40, "synthetic": True},
                "company": company,
            },
            entity_id=entity_id,
            correlation_id=f"{run_id}-correlation",
        )
        outcome = runtime.advance(run_id, _lifecycle("safe-client", company))
        self.assertEqual(outcome.status, "blocked")
        return runtime.runs.load_run(run_id)

    def _recover(self, runtime, run_id: str, company: str, recovery_id: str):
        output = _output(company)
        instruction = f"Recover the existing fictional {company} workflow using its approved version 1 artefact."
        return runtime.recover_with_approved_artifact(
            run_id,
            recovery_id=recovery_id,
            artifact_title=f"{company} Groundwork Review",
            artifact_version="v1",
            source_uri=f"https://drive.example.invalid/{run_id}/v1",
            artifact_checksum=_checksum(output),
            output=output,
            approver="telegram:matt",
            rationale="Use the exact approved manual artefact without claiming automated completion.",
            approval_evidence=_approval(instruction),
        )

    def test_origin_recovery_becomes_authoritative_and_commissions_only_next_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notion_calls = []

            def notion(dispatch):
                notion_calls.append(dispatch)
                return {
                    "external_action_taken": True,
                    "record_id": "safe-origin-notion-record",
                    "projection_key": dispatch["idempotency_key"],
                }

            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="narratiive",
                client_id="safe-client",
                dispatchers={"Notion": notion},
                environ={},
            )
            blocked = self._blocked(
                runtime,
                "origin-fictional-recovery",
                "origin-fictional-entity",
                "TEST / FICTIONAL — Origin Coffee",
            )
            original_blocker = blocked.blocker

            recovered, replay = self._recover(
                runtime,
                blocked.run_id,
                "TEST / FICTIONAL — Origin Coffee",
                "origin-groundwork-v1-recovery",
            )
            self.assertFalse(replay)
            self.assertEqual(recovered.status.value, "complete")
            self.assertEqual(recovered.approval_status, "approved")
            decision = recovered.approval_history[-1]
            self.assertEqual(decision["decision"], "manual_recovery_approved")
            self.assertEqual(decision["prior_blocker"], original_blocker)
            self.assertFalse(decision["automated_completion"])
            self.assertEqual(recovered.stages[0].output_artifacts[-1].artifact_type, "manual_recovery_artifact")
            self.assertFalse(recovered.external_action_taken)

            mission = WorkflowMissionControlProjector(workspace_id="narratiive").project((recovered,))
            self.assertEqual(mission.runs[0]["execution_mode"], "manual_recovery")
            self.assertFalse(mission.runs[0]["automated_completion"])
            notion = runtime.business_projection.prepare(recovered)
            self.assertEqual(notion["execution_mode"], "manual_recovery")
            self.assertEqual(notion["manual_recovery"]["prior_blocker"], original_blocker)

            commissioned, commission_replay = runtime.commission(
                recovered.run_id,
                "blueprint_lite_to_discovery_preparation",
                {
                    "diagnostic_evidence": {"source": "approved manual recovery"},
                    "company_context": {"name": "TEST / FICTIONAL — Origin Coffee"},
                },
                commitment_id="origin-discovery-after-recovery-v1",
            )
            self.assertFalse(commission_replay)
            self.assertEqual(commissioned.workflow_id, "blueprint_lite_to_discovery_preparation")
            self.assertFalse(commissioned.external_action_taken)
            self.assertFalse(commissioned.input_payload["_lineage"]["manual_recovery"]["automated_completion"])
            continued_inputs = build_next_workflow_inputs(commissioned, {}, {})
            self.assertEqual(
                continued_inputs["_lineage"]["manual_recovery"]["recovery_id"],
                "origin-groundwork-v1-recovery",
            )

            # A later explicit commission must retain the same recovery
            # provenance rather than relabelling the chain as fully automated.
            commissioned.status = WorkflowStatus.COMPLETE
            commissioned.current_stage_id = None
            commissioned.approval_status = "approved"
            commissioned.stages[0].status = StageStatus.COMPLETED
            commissioned.stages[0].output_artifacts = recovered.stages[0].output_artifacts.copy()
            runtime.runs.repository.save(commissioned)
            proposal, _ = runtime.commission(
                commissioned.run_id,
                "discovery_evidence_to_growth_sprint_proposal",
                {
                    "discovery_evidence": {
                        "source": "synthetic completed Discovery",
                        "notes": "Bounded fictional Discovery notes for lineage verification.",
                        "sources": [
                            {
                                "source_id": "fictional-discovery-notes-v1",
                                "source_type": "internal_test_notes",
                                "location": "workflow-test:origin-discovery-v1",
                            }
                        ],
                    },
                    "commercial_context": {"company": "TEST / FICTIONAL — Origin Coffee"},
                },
                commitment_id="origin-proposal-after-recovery-v1",
            )
            self.assertEqual(
                proposal.input_payload["_lineage"]["manual_recovery"]["recovery_id"],
                "origin-groundwork-v1-recovery",
            )
            proposal_projection = runtime.business_projection.prepare(proposal)
            self.assertEqual(
                proposal_projection["execution_mode"],
                "workflow_automation_after_manual_recovery",
            )

            replayed, replay = runtime.commission(
                recovered.run_id,
                "blueprint_lite_to_discovery_preparation",
                {
                    "diagnostic_evidence": {"source": "approved manual recovery"},
                    "company_context": {"name": "TEST / FICTIONAL — Origin Coffee"},
                },
                commitment_id="origin-discovery-after-recovery-v1",
            )
            self.assertTrue(replay)
            self.assertEqual(replayed.run_id, commissioned.run_id)
            with self.assertRaisesRegex(ValueError, "immediate downstream"):
                runtime.commission(
                    recovered.run_id,
                    "discovery_evidence_to_growth_sprint_proposal",
                    {},
                    commitment_id="unsafe-skip",
                )

            states = (runtime.runs.load_run(recovered.run_id), runtime.runs.load_run(commissioned.run_id))
            current = WorkflowMissionControlProjector(workspace_id="narratiive").project(states).runs[0]
            self.assertEqual(current["workflow_id"], "blueprint_lite_to_discovery_preparation")
            self.assertIsNone(current["blocker"])
            self.assertEqual(current["execution_mode"], "workflow_automation_after_manual_recovery")
            self.assertFalse(current["automated_completion"])
            self.assertEqual(current["manual_recovery"]["artifact_version"], "v1")
            projection = runtime.business_projection.prepare(states[1])
            self.assertEqual(projection["lifecycle_stage"], "discovery")
            self.assertEqual(projection["blocker"], current["blocker"])
            self.assertEqual(projection["execution_mode"], current["execution_mode"])
            self.assertEqual(projection["manual_recovery"], current["manual_recovery"])
            synced = runtime.sync_business_projection(
                states[1].run_id,
                approver="telegram:matt",
                rationale="Reconcile Notion to canonical recovered workflow state.",
            )
            self.assertEqual(synced["projection_status"], "verified")
            self.assertEqual(notion_calls[0]["payload"]["lifecycle_stage"], "discovery")
            self.assertEqual(notion_calls[0]["payload"]["workflow_status"], current["status"])
            self.assertEqual(notion_calls[0]["payload"]["blocker"], current["blocker"])
            self.assertEqual(
                notion_calls[0]["payload"]["proposed_next_action"],
                current["proposed_next_action"],
            )

            restarted = build_tony_workflow_runtime(
                tmp,
                workspace_id="narratiive",
                client_id="safe-client",
                dispatchers={"Notion": notion},
                environ={},
            )
            durable = restarted.runs.load_run(recovered.run_id)
            self.assertEqual(durable.approval_history[-1]["recovery_id"], "origin-groundwork-v1-recovery")
            self.assertEqual(durable.stages[0].output_artifacts[-1].checksum, decision["artifact_checksum"])

    def test_manual_recovery_cannot_skip_a_later_workflow_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = build_tony_workflow_runtime(
                tmp,
                workspace_id="narratiive",
                client_id="safe-client",
                dispatchers={},
                environ={},
            )
            blocked = self._blocked(
                runtime,
                "multi-stage-recovery-denied",
                "multi-stage-entity",
                "TEST / FICTIONAL — Multi Stage",
            )
            blocked.stages.append(
                StageRecord(
                    stage_id="later_human_gate",
                    agent_ref="matt",
                    step_approval_required=True,
                    side_effect_classification="preparation",
                )
            )
            runtime.runs.repository.save(blocked)

            with self.assertRaisesRegex(ValueError, "cannot bypass later workflow stages"):
                self._recover(
                    runtime,
                    blocked.run_id,
                    "TEST / FICTIONAL — Multi Stage",
                    "unsafe-multi-stage-recovery",
                )
            unchanged = runtime.runs.load_run(blocked.run_id)
            self.assertEqual(unchanged.status.value, "blocked")
            self.assertFalse(unchanged.approval_history)
            self.assertFalse(unchanged.stages[0].output_artifacts)

    def test_second_fictional_prospect_fails_recovers_and_tony_suppresses_replays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = build_tony_workflow_runtime(
                root,
                workspace_id="narratiive",
                client_id="safe-client",
                dispatchers={},
                environ={},
            )
            blocked = self._blocked(
                runtime,
                "second-fictional-recovery",
                "second-fictional-entity",
                "TEST / FICTIONAL — Second Prospect",
            )
            output = _output("TEST / FICTIONAL — Second Prospect")
            instruction = "Recover the existing fictional Second Prospect workflow using its approved version 1 artefact."
            recovery = {
                "recovery_id": "second-prospect-v1-recovery",
                "artifact_title": "Second Prospect Groundwork Review",
                "artifact_version": "v1",
                "source_uri": "https://drive.example.invalid/second/v1",
                "artifact_checksum": _checksum(output),
                "output": output,
            }
            service = TonyWorkflowCommandService(
                _Fallback(),
                FileWorkflowCommandBackend(root, dispatchers={}, environ={}),
            )

            alias_denied = service.execute(
                "/manual-recovery TEST / FICTIONAL — Second Prospect because approved synthetic recovery",
                [],
                principal_id="telegram:matt",
                inputs={"manual_recovery": recovery, "recovery_approval_evidence": _approval(instruction)},
            )
            self.assertEqual(alias_denied.status, "error")
            self.assertEqual(alias_denied.data["error_code"], "exact_run_id_required")

            denied = service.execute(
                f"/manual-recovery {blocked.run_id} because approved synthetic recovery",
                [],
                inputs={"manual_recovery": recovery, "recovery_approval_evidence": _approval(instruction)},
            )
            self.assertEqual(denied.status, "error")

            forged = _approval(instruction)
            forged["human_instruction_sha256"] = "0" * 64
            rejected = service.execute(
                f"/manual-recovery {blocked.run_id} because approved synthetic recovery",
                [],
                principal_id="telegram:matt",
                inputs={"manual_recovery": recovery, "recovery_approval_evidence": forged},
            )
            self.assertEqual(rejected.status, "error")

            recovered = service.execute(
                f"/manual-recovery {blocked.run_id} because approved synthetic recovery",
                [],
                principal_id="telegram:matt",
                inputs={"manual_recovery": recovery, "recovery_approval_evidence": _approval(instruction)},
            )
            replay = service.execute(
                f"/manual-recovery {blocked.run_id} because approved synthetic recovery",
                [],
                principal_id="telegram:matt",
                inputs={"manual_recovery": recovery, "recovery_approval_evidence": _approval(instruction)},
            )
            self.assertTrue(recovered.data["manual_recovery"])
            self.assertFalse(recovered.data["automated_completion"])
            self.assertFalse(recovered.data["replay"])
            self.assertTrue(replay.data["replay"])

            commissioned = service.execute(
                f"/commission {blocked.run_id} because approved next-stage recovery test",
                [],
                principal_id="telegram:matt",
                inputs={
                    "target_workflow_id": "blueprint_lite_to_discovery_preparation",
                    "commitment_id": "second-prospect-discovery-v1",
                    "diagnostic_evidence": {"source": "approved manual recovery"},
                    "company_context": {"name": "TEST / FICTIONAL — Second Prospect"},
                },
            )
            duplicate = service.execute(
                f"/commission {blocked.run_id} because approved next-stage recovery test",
                [],
                principal_id="telegram:matt",
                inputs={
                    "target_workflow_id": "blueprint_lite_to_discovery_preparation",
                    "commitment_id": "second-prospect-discovery-v1",
                    "diagnostic_evidence": {"source": "approved manual recovery"},
                    "company_context": {"name": "TEST / FICTIONAL — Second Prospect"},
                },
            )
            self.assertTrue(commissioned.data["commissioned"])
            self.assertFalse(commissioned.data["replay"])
            self.assertTrue(duplicate.data["replay"])
            self.assertFalse(commissioned.data["external_action_taken"])

            review = service.execute(f"/deliver-review {commissioned.data['run_id']}", [])
            self.assertIn(review.status, {"blocked", "error"})
            self.assertFalse(runtime.runs.load_run(commissioned.data["run_id"]).external_action_taken)


if __name__ == "__main__":
    unittest.main()
