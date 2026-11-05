"""Synthetic regression of the Telegram incident: audit rows are not decisions."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
import tempfile
from pathlib import Path
from runtime.briefing_intelligence import ExecutiveBriefingPipeline, FileBriefingBaselineStore

from runtime.agency_state_projection import AgencyStateProjector
from runtime.founder_brief import decision_ready_items, decision_ready_materials, render_material_update
from runtime.proactive_executive_delivery import MaterialEscalationService
from runtime.policy_governed_escalation import PolicyGovernedMaterialEscalationService
from runtime.mission_control import MissionControlSnapshot, WorkstreamStatus
from runtime.tony_promised_work import TonyPromisedWorkWorker


def snapshot(**changes):
    return replace(MissionControlSnapshot(
        generated_at="2026-11-05T08:00:00Z", status="blocked", progress={},
        workstreams=(), connections=(), approvals_required=(), blockers=(),
    ), **changes)


class COOAttentionTests(unittest.TestCase):
    def test_screenshot_noise_and_unresolved_legacy_approvals_are_not_founder_decisions(self):
        source = snapshot(
            blockers=tuple(f"github:pull_request:{n}:merge_conflict" for n in range(494, 525)),
            approvals_required=("workflow:31:Approve Blueprint Lite", "workflow:old-v3:Approve completed work"),
        )
        self.assertEqual(decision_ready_materials(source), ())
        self.assertEqual(len(source.blockers), 31)  # projection never mutates evidence

    def test_current_review_is_named_and_old_versions_do_not_recur(self):
        source = snapshot(
            approvals_required=("workflow:old:Approve", "workflow:current:Approve"),
            workflow_runs=(
                {"run_id": "old", "entity_id": "synthetic-company", "company": "Example Coffee",
                 "workflow_id": "growth_blueprint_deliverable_production", "updated_at": "2026-11-04"},
                {"run_id": "current", "entity_id": "synthetic-company", "company": "Example Coffee",
                 "workflow_id": "growth_blueprint_deliverable_production", "updated_at": "2026-11-05"},
            ),
        )
        materials = decision_ready_materials(source)
        self.assertEqual(len(materials), 1)
        text = render_material_update(materials)
        self.assertIn("Example Coffee", text)
        self.assertIn("Growth Blueprint", text)
        self.assertIn("Recommended next step", text)
        self.assertNotIn("workflow:", text)
        self.assertNotIn("old", text)

    def test_business_continuity_failure_is_retained_but_routine_engineering_is_quiet(self):
        source = snapshot(workstreams=(
            WorkstreamStatus("engineering-maintenance", "Repository checks", "blocked", "Codex",
                             "Repair the checks", blocker="failed_check"),
            WorkstreamStatus("email-continuity", "Client email delivery unavailable", "blocked", "Engineering",
                             "Restore the email connection before retrying client delivery", blocker="connection_failed"),
        ))
        materials = decision_ready_materials(source)
        self.assertEqual(len(materials), 1)
        self.assertIn("Client email delivery", materials[0])

    def test_long_queue_retains_complete_items_and_explicit_access_to_the_remainder(self):
        materials = tuple(f"Client {i}. " + "A concrete business consequence. " * 15 + "Next step: review the schedule." for i in range(20))
        text = render_material_update(materials)
        self.assertLessEqual(len(text), 3500)
        self.assertIn("Ask me for the remaining decisions and delivery risks", text)
        self.assertNotIn("...and", text)
        self.assertIn(materials[0], text)
        self.assertNotIn(materials[-1], text)
        self.assertTrue(text.endswith("full queue."))

    def test_new_review_version_changes_identity_even_when_prose_is_identical(self):
        def source(run_id):
            return snapshot(
                approvals_required=(f"workflow:{run_id}:Approve",),
                workflow_runs=({"run_id": run_id, "entity_id": "example-coffee", "company": "Example Coffee",
                    "workflow_id": "growth_blueprint_deliverable_production", "updated_at": "2026-11-05"},),
            )
        first = decision_ready_items(source("version-one"))
        second = decision_ready_items(source("version-two"))
        self.assertEqual(str(first[0]), str(second[0]))
        self.assertNotEqual(first[0].key, second[0].key)
        for service in (MaterialEscalationService, PolicyGovernedMaterialEscalationService):
            self.assertNotEqual(
                service.build_digest_key(workspace_id="synthetic", materials=first),
                service.build_digest_key(workspace_id="synthetic", materials=second),
            )
            self.assertEqual(
                service.build_digest_key(workspace_id="synthetic", materials=first),
                service.build_digest_key(workspace_id="synthetic", materials=decision_ready_items(source("version-one"))),
            )
        self.assertNotIn("version-one", render_material_update(first))

    def test_same_run_new_artefact_changes_delivery_identity(self):
        source = snapshot(
            approvals_required=("workflow:one-run:Approve",),
            workflow_runs=({"run_id": "one-run", "entity_id": "example-coffee", "company": "Example Coffee",
                "workflow_id": "growth_blueprint_deliverable_production", "updated_at": "2026-11-05",
                "latest_artefact": {"artifact_id": "synthetic-artifact", "checksum": "version-one"}},),
        )
        revised = replace(source, workflow_runs=({**source.workflow_runs[0],
            "latest_artefact": {"artifact_id": "synthetic-artifact", "checksum": "version-two"}},))
        first, second = decision_ready_items(source), decision_ready_items(revised)
        self.assertEqual(first[0].text, second[0].text)
        self.assertNotEqual(first[0].key, second[0].key)

    def test_scheduled_baseline_does_not_hide_revised_gate_on_the_same_run(self):
        source = snapshot(
            approvals_required=("workflow:one-run:Approve",),
            workflow_runs=({"run_id": "one-run", "entity_id": "example-coffee", "company": "Example Coffee",
                "workflow_id": "growth_blueprint_deliverable_production", "updated_at": "2026-11-05",
                "approval_token": "token-one", "latest_artefact": {"checksum": "version-one"}},),
        )
        revised = replace(source, workflow_runs=({**source.workflow_runs[0],
            "approval_token": "token-two", "latest_artefact": {"checksum": "version-two"}},))
        with tempfile.TemporaryDirectory() as directory:
            pipeline = ExecutiveBriefingPipeline(baseline_store=FileBriefingBaselineStore(Path(directory) / "baseline.json"))
            state = pipeline.refine(AgencyStateProjector().project(source))
            pipeline.record_delivered(pipeline.snapshot(state, period="morning"))
            self.assertEqual(decision_ready_items(source, pipeline=pipeline), ())
            self.assertEqual(len(decision_ready_items(revised, pipeline=pipeline)), 1)

    def test_failure_with_sanitized_identity_still_names_the_work(self):
        state = SimpleNamespace(
            workflow_id="growth_blueprint_deliverable_production", run_id="synthetic-run",
            client_id="growth_blueprint_deliverable", entity_id="growth_blueprint_deliverable",
            input_payload={}, blocker="quality_failed:synthetic_gate",
        )
        text = TonyPromisedWorkWorker._failure_message(state)
        self.assertTrue(text.startswith("The current client — Growth Blueprint is paused."))

    def test_opaque_company_fallback_is_not_presented_as_a_client_name(self):
        label = AgencyStateProjector._company_label({"company": "origin-coffee-fictional-e2e-20261103", "entity_id": "origin-coffee-fictional-e2e-20261103"})
        self.assertEqual(label, "Client work (company name not recorded)")

    def test_quality_failure_explains_correction_without_fabricating_a_retry(self):
        state = SimpleNamespace(
            workflow_id="growth_blueprint_deliverable_production", run_id="synthetic-run",
            client_id="synthetic-client", entity_id="synthetic-entity",
            input_payload={"company": "Example Coffee"}, blocker="quality_failed:growth_blueprint_quality_gate",
        )
        text = TonyPromisedWorkWorker._failure_message(state)
        self.assertIn("Example Coffee — Growth Blueprint is paused", text)
        self.assertIn("responsible specialist correct", text)
        self.assertIn("Recovery has not yet been verified", text)
        self.assertNotIn("quality_failed", text)
        self.assertNotIn("underway", text)


if __name__ == "__main__":
    unittest.main()
