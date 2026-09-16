from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from runtime.human_review_artifacts import (
    BLUEPRINT_PRESENTATION_RENDERER_ID,
    HumanReviewArtifactStore,
    HumanReviewPresentationService,
    NarratiiveReviewPDFRenderer,
    build_review_plan,
)
from runtime.models import ArtifactRef, WorkflowState
from tests.test_tony_workflow_commands import blueprint_output
from tests.test_workflow_quality import discovery_output, growth_blueprint_output, proposal_output


def state(workflow_id: str) -> WorkflowState:
    return WorkflowState(
        workflow_id=workflow_id,
        run_id=f"safe-{workflow_id}",
        stages=[],
        workspace_id="narratiive",
        client_id="safe-client",
        entity_id="safe-company",
        input_payload={"company": "SAFE Review Company"},
    )


class HumanReviewArtifactContractTests(unittest.TestCase):
    def test_minimum_document_products_have_explicit_review_contracts(self) -> None:
        cases = (
            ("growth_diagnostic_to_blueprint_lite", blueprint_output(), "Blueprint Lite"),
            ("discovery_evidence_to_growth_sprint_proposal", proposal_output(), "Growth Sprint Proposal"),
            ("blueprint_lite_to_discovery_preparation", discovery_output(), "Research and Strategy Review"),
            ("research_to_growth_blueprint", growth_blueprint_output(), "Narratiive Growth Blueprint"),
        )

        for workflow_id, output, product in cases:
            with self.subTest(workflow_id=workflow_id):
                plan = build_review_plan(state(workflow_id), output)
                self.assertEqual(plan.product, product)
                self.assertGreaterEqual(len(plan.sections), 4)
                self.assertTrue(plan.decision_prompt)
                self.assertTrue(plan.next_if_approved)

    def test_growth_sprint_plan_is_editorial_not_a_field_dump(self) -> None:
        output = proposal_output()
        output.update(
            {
                "provider": "internal-provider",
                "model": "internal-model",
                "provider_message_id": "internal-message",
                "worker_execution": {"worker_id": "internal-worker"},
            }
        )

        plan = build_review_plan(state("discovery_evidence_to_growth_sprint_proposal"), output)
        visible = " ".join(
            (
                plan.product,
                plan.subtitle,
                plan.decision_prompt,
                *(section.heading for section in plan.sections),
                *(text for section in plan.sections for text in section.body),
                *(text for section in plan.sections for text in section.items),
            )
        )

        self.assertIn("The situation / what we heard", visible)
        self.assertIn("Our strategic hypothesis", visible)
        self.assertIn("Investment / commercial status", visible)
        self.assertNotIn("internal-provider", visible)
        self.assertNotIn("internal-model", visible)
        self.assertNotIn("internal-message", visible)
        self.assertNotIn("internal-worker", visible)

    def test_review_pdf_is_immutable_derived_output_and_excludes_runtime_metadata(self) -> None:
        output = proposal_output()
        output.update(
            {
                "provider": "DO-NOT-SHOW-PROVIDER",
                "model": "DO-NOT-SHOW-MODEL",
                "provider_message_id": "DO-NOT-SHOW-MESSAGE",
                "stop_reason": "DO-NOT-SHOW-STOP",
                "worker_execution": {
                    "worker_id": "DO-NOT-SHOW-WORKER",
                    "policy_id": "DO-NOT-SHOW-POLICY",
                    "selection_reason": "DO-NOT-SHOW-SELECTION",
                },
                "work_product": '{"raw_json":"DO-NOT-SHOW-RAW"}',
            }
        )
        encoded = json.dumps(output, sort_keys=True, separators=(",", ":")).encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "authoritative.json"
            source_path.write_bytes(encoded + b"\n")
            source = ArtifactRef(
                artifact_id="artifact-safe-source",
                artifact_type="growth_sprint_proposal",
                location=str(source_path),
                checksum=hashlib.sha256(encoded).hexdigest(),
            )
            review = HumanReviewPresentationService(
                HumanReviewArtifactStore(root / "reviews")
            ).produce(
                state=state("discovery_evidence_to_growth_sprint_proposal"),
                source=source,
                output=output,
            )

            self.assertEqual(source_path.read_bytes(), encoded + b"\n")
            self.assertEqual(review.mime_type, "application/pdf")
            self.assertGreaterEqual(review.page_count, 3)
            visible = "\n".join(
                page.extract_text() or "" for page in PdfReader(review.location).pages
            )
            self.assertIn("Growth Sprint Proposal", visible)
            self.assertIn("Proposed workstreams", visible)
            for internal_value in (
                "DO-NOT-SHOW-PROVIDER",
                "DO-NOT-SHOW-MODEL",
                "DO-NOT-SHOW-MESSAGE",
                "DO-NOT-SHOW-STOP",
                "DO-NOT-SHOW-WORKER",
                "DO-NOT-SHOW-POLICY",
                "DO-NOT-SHOW-SELECTION",
                "DO-NOT-SHOW-RAW",
            ):
                self.assertNotIn(internal_value, visible)
            manifest = json.loads((Path(review.location).parent / "manifest.json").read_text())
            self.assertEqual(manifest["source_artifact_id"], source.artifact_id)
            self.assertEqual(manifest["source_artifact_checksum"], source.checksum)
            self.assertEqual(manifest["checksum"], hashlib.sha256(Path(review.location).read_bytes()).hexdigest())

    def test_produced_growth_blueprint_reuses_qa_passed_presentation_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_plan = build_review_plan(
                state("research_to_growth_blueprint"), growth_blueprint_output()
            )
            produced_pdf, _ = NarratiiveReviewPDFRenderer().render(source_plan)
            produced_path = root / "deliverables" / "growth-blueprint.pdf"
            produced_path.parent.mkdir(parents=True)
            produced_path.write_bytes(produced_pdf)
            output = {
                "presentation_specification": {
                    "slides": [
                        {"takeaway": "The strategic source is approved for presentation production."},
                        {"takeaway": "The activation choices remain bounded by human review."},
                    ]
                },
                "editable_pptx": str(root / "deliverables" / "growth-blueprint.pptx"),
                "review_pdf": str(produced_path),
                "visual_qa": {
                    "status": "passed",
                    "checks": {"no_visible_machine_runtime_artefacts": True},
                },
                "proposed_client_release": {"status": "not_approved"},
                "approval_status": "pending",
                "external_action_taken": False,
            }
            encoded = json.dumps(output, sort_keys=True, separators=(",", ":")).encode("utf-8")
            source_path = root / "artifacts" / "deliverable-output.json"
            source_path.parent.mkdir(parents=True)
            source_path.write_bytes(encoded + b"\n")
            source = ArtifactRef(
                artifact_id="artifact-safe-blueprint-deliverable",
                artifact_type="workflow_step_output",
                location=str(source_path),
                checksum=hashlib.sha256(encoded).hexdigest(),
            )

            review = HumanReviewPresentationService(
                HumanReviewArtifactStore(root / "human-review-artifacts"),
                allowed_source_root=root,
            ).produce(
                state=state("growth_blueprint_deliverable_production"),
                source=source,
                output=output,
            )

            self.assertEqual(Path(review.location).read_bytes(), produced_pdf)
            self.assertEqual(review.renderer_id, BLUEPRINT_PRESENTATION_RENDERER_ID)
            self.assertEqual(review.product, "Narratiive Growth Blueprint")
            self.assertEqual(output["approval_status"], "pending")
            self.assertFalse(output["external_action_taken"])


if __name__ == "__main__":
    unittest.main()
