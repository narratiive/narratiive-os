from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from runtime.human_review_artifacts import (
    BLUEPRINT_PRESENTATION_RENDERER_ID,
    HumanReviewArtifactError,
    HumanReviewArtifactStore,
    HumanReviewPresentationService,
    NarratiiveReviewPDFRenderer,
    build_fieldwork_proposal_draft,
    build_review_plan,
)
from runtime.fieldwork_proposal_pdf import (
    FieldworkProposalDraft,
    FieldworkProposalPDFRenderer,
    FieldworkProposalQualityGate,
    ProposalInsight,
)


def _assessment(reviewer: str, criteria: dict[str, str], source_checksum: str) -> dict[str, object]:
    record: dict[str, object] = {
        "reviewer": reviewer,
        "assessment_artifact_id": f"quality-assessment:{reviewer.casefold().replace(' ', '-')}:1",
        "recorded_at": "2026-10-30T00:00:00Z",
        "source_artifact_checksum": source_checksum,
        "criteria": criteria,
    }
    record["assessment_checksum"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return record


def passed_quality(source_checksum: str = "a" * 64) -> FieldworkProposalQualityGate:
    return FieldworkProposalQualityGate._from_append_only_history(
        source_artifact_checksum=source_checksum,
        strategy_director=_assessment("Strategy Director", {
            "business_specificity": "pass", "commercial_relevance": "pass", "evidence_quality": "pass",
            "insight_distinctiveness": "pass", "commercial_proposition": "pass",
        }, source_checksum),
        creative_director=_assessment("Creative Director", {
            "headline_quality": "pass", "copywriting": "pass", "visual_hierarchy": "pass",
            "brand_expression": "pass", "editorial_quality": "pass",
        }, source_checksum),
    )


def append_quality_history(
    proposal_state: WorkflowState,
    gate: FieldworkProposalQualityGate,
    *,
    roles: tuple[str, ...] = ("Strategy Director", "Creative Director"),
) -> None:
    assessment_stage = next((stage for stage in proposal_state.stages if stage.stage_id == "proposal_quality_assessment"), None)
    if assessment_stage is None:
        assessment_stage = StageRecord(stage_id="proposal_quality_assessment", agent_ref="quality")
        proposal_state.stages.append(assessment_stage)
    for assessment in (gate.strategy_director, gate.creative_director):
        if assessment["reviewer"] not in roles:
            continue
        content = json.dumps(assessment, sort_keys=True, separators=(",", ":")).encode("utf-8")
        artifact_checksum = hashlib.sha256(content).hexdigest()
        location = Path(tempfile.gettempdir()) / f"{artifact_checksum}.quality-assessment.json"
        location.write_bytes(content)
        assessment_stage.output_artifacts.append(ArtifactRef(
            str(assessment["assessment_artifact_id"]),
            "fieldwork_presentation_quality_assessment",
            str(location),
            artifact_checksum,
        ))
        proposal_state.approval_history.append({
            **assessment,
            "decision": "fieldwork_presentation_quality_assessment",
            "assessment_artifact_checksum": artifact_checksum,
            "workspace_id": proposal_state.workspace_id,
            "client_id": proposal_state.client_id,
            "run_id": proposal_state.run_id,
        })
from runtime.models import ArtifactRef, StageRecord, WorkflowState
from tests.test_tony_workflow_commands import blueprint_output
from tests.test_workflow_quality import (
    discovery_output,
    growth_blueprint_output,
    proposal_output,
    strategy_thesis_output,
    )


def with_three_source_insights(output: dict) -> dict:
    read = output.setdefault("commercial_read", [])
    titles = (
        "Demand quality before volume",
        "A sharper reason to choose",
        "Decide before investment",
    )
    for index, item in enumerate(read):
        item.setdefault("title", titles[index])
        item["evidence_refs"] = ["meeting:notes:1"]
    while len(read) < 3:
        read.append({
            "title": titles[len(read)],
            "observation": "The supplied Discovery evidence identifies an unresolved commercial choice.",
            "classification": "interpretation",
            "evidence_refs": ["meeting:notes:1"],
            "commercial_implication": "Resolving that choice before investment can protect the quality of the next decision.",
        })
    return output


def state(workflow_id: str) -> WorkflowState:
    return WorkflowState(
        workflow_id=workflow_id,
        run_id=f"safe-{workflow_id}",
        stages=[StageRecord(
            stage_id="discovery_evidence",
            agent_ref="test",
            output_artifacts=[ArtifactRef("meeting:notes:1", "discovery_evidence", "synthetic:meeting")],
        )],
        workspace_id="narratiive",
        client_id="safe-client",
        entity_id="safe-company",
        input_payload={"company": "SAFE Review Company", "discovery_evidence": {"sources": [{"source_id": "meeting:notes:1", "source_type": "notes", "location": "synthetic:meeting"}]}, "commercial_context": {"approved_fieldwork_fee": {"amount": 12000, "currency": "GBP", "approval_reference": {"approval_id": "synthetic-founder-fee-approval", "decision": "approved", "approved_by": "synthetic-founder", "recorded_at": "2026-10-30T00:00:00Z", "fee_checksum": "9a4cde75e37d0063f9b84b520b7ee72145129683e8d53c1854d73ca8bf6beeb4"}}}},
    )


def bound_source_and_state(output: dict, *, ensure_insights: bool = True) -> tuple[WorkflowState, ArtifactRef]:
    if ensure_insights:
        with_three_source_insights(output)
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
    checksum = hashlib.sha256(encoded).hexdigest()
    gate = passed_quality(checksum)
    source = ArtifactRef(
        "artifact-bound", "proposal", str(Path(tempfile.gettempdir()) / f"{checksum}.authoritative.json"), checksum,
        metadata={
            "proposal_presentation_quality": {
                "strategy_director_assessment_artifact_id": gate.strategy_director["assessment_artifact_id"],
                "creative_director_assessment_artifact_id": gate.creative_director["assessment_artifact_id"],
            }
        },
    )
    Path(source.location).write_bytes(encoded)
    proposal_state = state("discovery_evidence_to_growth_sprint_proposal")
    reference = proposal_state.input_payload["commercial_context"]["approved_fieldwork_fee"]["approval_reference"]
    reference.update({"workspace_id": proposal_state.workspace_id, "client_id": proposal_state.client_id, "run_id": proposal_state.run_id, "source_artifact_checksum": source.checksum})
    proposal_state.approval_history.append({"approval_id": reference["approval_id"], "decision": "approved_fieldwork_fee", "fee_checksum": reference["fee_checksum"], "source_artifact_checksum": source.checksum})
    append_quality_history(proposal_state, gate)
    return proposal_state, source


class HumanReviewArtifactContractTests(unittest.TestCase):
    def test_minimum_document_products_have_explicit_review_contracts(self) -> None:
        cases = (
            ("growth_diagnostic_to_blueprint_lite", blueprint_output(), "Blueprint Lite"),
            ("discovery_evidence_to_growth_sprint_proposal", proposal_output(), "Narratiive FIELDWORK Proposal"),
            ("blueprint_lite_to_discovery_preparation", discovery_output(), "Research and Strategy Review"),
            ("strategic_synthesis_to_strategy_thesis", strategy_thesis_output(), "Strategy Thesis"),
            ("strategy_thesis_to_growth_blueprint", growth_blueprint_output(), "Narratiive Growth Blueprint"),
            ("research_to_growth_blueprint", growth_blueprint_output(), "Narratiive Growth Blueprint"),
        )

        for workflow_id, output, product in cases:
            with self.subTest(workflow_id=workflow_id):
                plan = build_review_plan(state(workflow_id), output)
                self.assertEqual(plan.product, product)
                self.assertGreaterEqual(len(plan.sections), 4)
                self.assertTrue(plan.decision_prompt)
                self.assertTrue(plan.next_if_approved)

    def test_strategy_thesis_review_is_a_gate_three_decision_document(self) -> None:
        plan = build_review_plan(
            state("strategic_synthesis_to_strategy_thesis"),
            strategy_thesis_output(),
        )
        visible = " ".join(
            (
                plan.product,
                plan.gate_label,
                plan.decision_prompt,
                *(section.heading for section in plan.sections),
                *(text for section in plan.sections for text in section.body),
                *(text for section in plan.sections for text in section.items),
            )
        )
        self.assertEqual(plan.gate_label, "GATE 3")
        self.assertIn("Decisions requiring Matt", visible)
        self.assertIn("exact Strategy Thesis", plan.decision_prompt)

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

        self.assertIn("What we heard", visible)
        self.assertIn("The opportunity worth taking seriously", visible)
        self.assertIn("Introducing FIELDWORK", visible)
        self.assertNotIn("Growth Sprint", visible)
        self.assertIn("FIELDWORK fee: £12,000", visible)
        self.assertNotIn("internal-provider", visible)
        self.assertNotIn("internal-model", visible)
        self.assertNotIn("internal-message", visible)
        self.assertNotIn("internal-worker", visible)

    def test_fieldwork_internal_review_preserves_missing_fee_as_a_blocker(self) -> None:
        proposal_state = state("discovery_evidence_to_growth_sprint_proposal")
        proposal_state.input_payload = {"company": "SAFE Review Company"}
        plan = build_review_plan(proposal_state, proposal_output())
        self.assertIn("to be agreed", " ".join(text for section in plan.sections for text in section.body).casefold())

    def test_fieldwork_review_requires_fee_approval_bound_to_exact_fee(self) -> None:
        proposal_state = state("discovery_evidence_to_growth_sprint_proposal")
        proposal_state.input_payload["commercial_context"]["approved_fieldwork_fee"]["approval_reference"]["fee_checksum"] = "0" * 64
        with self.assertRaisesRegex(HumanReviewArtifactError, "does not bind"):
            build_review_plan(proposal_state, proposal_output())

    def test_fieldwork_client_presentation_refuses_unreconciled_evidence(self) -> None:
        output = proposal_output()
        output["proposal_evidence_readiness"] = {
            "client_facing_ready": False,
            "material_contradictions": ["Identity association is unresolved."],
            "missing_evidence": [],
            "required_clarification": ["Confirm the client identity."],
        }
        with self.assertRaisesRegex(HumanReviewArtifactError, "evidence approved"):
            build_fieldwork_proposal_draft(*bound_source_and_state(output), output)

    def test_fieldwork_client_presentation_has_fixed_two_page_contract(self) -> None:
        output = proposal_output()
        proposal_state, source = bound_source_and_state(output)
        with tempfile.TemporaryDirectory() as temporary:
            review = HumanReviewPresentationService(HumanReviewArtifactStore(Path(temporary) / "reviews")).produce(
                state=proposal_state, source=source, output=output,
            )
            rendered = Path(review.location).read_bytes()
        self.assertEqual(review.page_count, 2)
        visible = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(rendered)).pages)
        compact = " ".join(visible.split())
        self.assertIn("F I E L D W O R K P R O P O S A L", compact)
        self.assertIn("Approve FIELDWORK", compact)
        self.assertNotIn("Growth Sprint", visible)
        self.assertNotIn("workflow_id", visible)

    def test_fieldwork_fee_binding_cannot_be_replayed_to_another_source(self) -> None:
        output = proposal_output()
        proposal_state, source = bound_source_and_state(output)
        replay = ArtifactRef(source.artifact_id, source.artifact_type, source.location, "f" * 64)
        with self.assertRaisesRegex(HumanReviewArtifactError, "checksum does not match"):
            build_fieldwork_proposal_draft(proposal_state, replay, output)

    def test_fieldwork_presentation_refuses_missing_quality_record_and_generic_insight_fallback(self) -> None:
        output = proposal_output()
        proposal_state, source = bound_source_and_state(output)
        proposal_state.approval_history = proposal_state.approval_history[:1]
        with self.assertRaisesRegex(HumanReviewArtifactError, "not present in append-only workflow history"):
            build_fieldwork_proposal_draft(proposal_state, source, output)
        append_quality_history(proposal_state, passed_quality(source.checksum or ""))
        output = with_three_source_insights(proposal_output())
        output["commercial_read"] = output["commercial_read"][:2]
        proposal_state, source = bound_source_and_state(output, ensure_insights=False)
        with self.assertRaisesRegex(HumanReviewArtifactError, "three substantive"):
            build_fieldwork_proposal_draft(proposal_state, source, output)

    def test_fieldwork_presentation_refuses_unchecksummed_quality_record_and_foreign_insight_evidence(self) -> None:
        output = proposal_output()
        proposal_state, source = bound_source_and_state(output)
        proposal_state.approval_history = proposal_state.approval_history[:1]
        with self.assertRaisesRegex(HumanReviewArtifactError, "not present in append-only workflow history"):
            build_fieldwork_proposal_draft(proposal_state, source, output)
        append_quality_history(proposal_state, passed_quality(source.checksum or ""))
        output = proposal_output()
        output["commercial_read"][0]["evidence_refs"] = ["not-an-authoritative-source"]
        proposal_state, source = bound_source_and_state(output, ensure_insights=False)
        proposal_state.input_payload["_lineage"] = {"parent_artifact_ids": ["not-an-authoritative-source"]}
        with self.assertRaisesRegex(HumanReviewArtifactError, "outside the authoritative"):
            build_fieldwork_proposal_draft(proposal_state, source, output)

    def test_latest_persisted_quality_assessment_controls_the_gate(self) -> None:
        output = proposal_output()
        proposal_state, source = bound_source_and_state(output)
        failed_criteria = {
            "headline_quality": "pass", "copywriting": "fail", "visual_hierarchy": "pass",
            "brand_expression": "pass", "editorial_quality": "pass",
        }
        original_gate = passed_quality(source.checksum or "")
        failed_assessment = _assessment("Creative Director", failed_criteria, source.checksum or "")
        failed_assessment["assessment_artifact_id"] = "quality-assessment:creative-director:2"
        checksum_payload = {key: failed_assessment[key] for key in (
            "reviewer", "assessment_artifact_id", "recorded_at", "source_artifact_checksum", "criteria",
        )}
        failed_assessment["assessment_checksum"] = hashlib.sha256(
            json.dumps(checksum_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        append_quality_history(proposal_state, FieldworkProposalQualityGate._from_append_only_history(
            source_artifact_checksum=source.checksum or "",
            strategy_director=original_gate.strategy_director,
            creative_director=failed_assessment,
        ), roles=("Creative Director",))
        with self.assertRaisesRegex(HumanReviewArtifactError, "Creative Director quality gate"):
            build_fieldwork_proposal_draft(proposal_state, source, output)

    def test_raw_quality_gate_cannot_render_without_history_resolution(self) -> None:
        raw = FieldworkProposalQualityGate(
            source_artifact_checksum="a" * 64,
            strategy_director={},
            creative_director={},
        )
        with self.assertRaisesRegex(Exception, "not resolved from append-only workflow history"):
            raw.validate("a" * 64)

    def test_public_renderer_rejects_a_sealed_gate_without_the_authoritative_service(self) -> None:
        output = proposal_output()
        proposal_state, source = bound_source_and_state(output)
        draft = build_fieldwork_proposal_draft(proposal_state, source, output)
        with self.assertRaisesRegex(Exception, "authoritative HumanReviewPresentationService"):
            FieldworkProposalPDFRenderer().render(draft)

    def test_fieldwork_presentation_rejects_substituted_output_and_missing_assessment_artifact(self) -> None:
        output = proposal_output()
        proposal_state, source = bound_source_and_state(output)
        substituted = json.loads(json.dumps(output))
        substituted["commercial_read"][0]["observation"] = "Altered after the quality assessment."
        with self.assertRaisesRegex(HumanReviewArtifactError, "does not match the persisted"):
            build_fieldwork_proposal_draft(proposal_state, source, substituted)
        assessment_stage = proposal_state.stage("proposal_quality_assessment")
        assessment_stage.output_artifacts.pop()
        with self.assertRaisesRegex(HumanReviewArtifactError, "not present in persisted workflow lineage"):
            build_fieldwork_proposal_draft(proposal_state, source, output)

    def test_direct_renderer_rejects_unbound_investment_and_internal_language(self) -> None:
        draft = FieldworkProposalDraft(
            company="Safe", headline="A clear choice", introduction="A concise introduction.",
            opportunity_heading="A real opportunity", opportunity_body="A practical evidence-led commercial read.",
            opportunity_metric_label=None, opportunity_metric_value=None, opportunity_metric_basis=None,
            insights=(ProposalInsight("One", "A specific observation."),) * 3,
            deliverables=(ProposalInsight("One", "A focused output."),) * 3,
            closing_headline="A clearer path", closing_body="A useful next step.",
            timeline="Seven days", investment="£18,000", focus="Audience choice",
            internal_review_only=True,
            quality_gate=passed_quality(), source_artifact_checksum="a" * 64,
        )
        with self.assertRaisesRegex(Exception, "exact-fee binding"):
            draft.validate()
        forged_client_release = FieldworkProposalDraft(
            company="Safe", headline="A clear choice", introduction="A concise introduction.",
            opportunity_heading="A real opportunity", opportunity_body="A practical evidence-led commercial read.",
            opportunity_metric_label=None, opportunity_metric_value=None, opportunity_metric_basis=None,
            insights=(ProposalInsight("One", "A specific observation."),) * 3,
            deliverables=(ProposalInsight("One", "A focused output."),) * 3,
            closing_headline="A clearer path", closing_body="A useful next step.",
            timeline="Seven days", investment="GBP 1,000", focus="Audience choice",
            internal_review_only=False,
            verified_fee_binding={"approval_id": "forged-local-value", "fee_checksum": "a" * 64},
            quality_gate=passed_quality(), source_artifact_checksum="a" * 64,
        )
        with self.assertRaisesRegex(Exception, "review-only"):
            forged_client_release.validate()
        unsafe = FieldworkProposalDraft(
            company="Safe", headline="Gate 2 review", introduction="A concise introduction.",
            opportunity_heading="A real opportunity", opportunity_body="A practical evidence-led commercial read.",
            opportunity_metric_label=None, opportunity_metric_value=None, opportunity_metric_basis=None,
            insights=(ProposalInsight("One", "A specific observation."),) * 3,
            deliverables=(ProposalInsight("One", "A focused output."),) * 3,
            closing_headline="A clearer path", closing_body="A useful next step.",
            timeline="Seven days", investment=None, focus="Audience choice",
            quality_gate=passed_quality(), source_artifact_checksum="a" * 64,
        )
        with self.assertRaisesRegex(Exception, "internal workflow terminology"):
            unsafe.validate()

    def test_quality_gate_rejects_placeholder_copy_and_missing_specialist_review(self) -> None:
        placeholder = FieldworkProposalDraft(
            company="Safe", headline="An opportunity worth validating.",
            introduction="A concise introduction grounded in the supplied evidence.",
            opportunity_heading="A real opportunity", opportunity_body="A practical evidence-led commercial read.",
            opportunity_metric_label=None, opportunity_metric_value=None, opportunity_metric_basis=None,
            insights=(
                ProposalInsight("Distinct observation one", "This insight has enough distinct commercial detail to be reviewed carefully."),
                ProposalInsight("Distinct observation two", "This insight has enough distinct commercial detail to be reviewed carefully."),
                ProposalInsight("Distinct observation three", "This insight has enough distinct commercial detail to be reviewed carefully."),
            ),
            deliverables=(ProposalInsight("One", "A focused output."),) * 3,
            closing_headline="A clearer path", closing_body="A useful next step.",
            timeline="Seven days", investment=None, focus="Audience choice",
            quality_gate=passed_quality(), source_artifact_checksum="a" * 64,
        )
        with self.assertRaisesRegex(Exception, "generic placeholder"):
            placeholder.validate()
        missing_review = FieldworkProposalDraft(
            company="Safe", headline="A specific commercial choice", introduction="A concise introduction grounded in the supplied evidence.",
            opportunity_heading="A real opportunity", opportunity_body="A practical evidence-led commercial read.",
            opportunity_metric_label=None, opportunity_metric_value=None, opportunity_metric_basis=None,
            insights=placeholder.insights, deliverables=placeholder.deliverables,
            closing_headline="A clearer path", closing_body="A useful next step.",
            timeline="Seven days", investment=None, focus="Audience choice",
        )
        with self.assertRaisesRegex(Exception, "Strategy Director and Creative Director"):
            missing_review.validate()

    def test_legacy_proposal_schema_remains_renderable(self) -> None:
        legacy = proposal_output()
        legacy.pop("proposal_evidence_readiness")
        legacy.pop("fieldwork_offer")
        legacy_state = state("discovery_evidence_to_growth_sprint_proposal")
        plan = build_review_plan(legacy_state, legacy)
        self.assertEqual(plan.product, "Historical strategic proposal")

    def test_legacy_proposal_can_be_persisted_without_current_fee_lineage(self) -> None:
        """Historic records stay reviewable; they cannot become new quotations."""
        legacy = proposal_output()
        legacy.pop("proposal_evidence_readiness")
        legacy.pop("fieldwork_offer")
        legacy_state = state("discovery_evidence_to_growth_sprint_proposal")
        legacy_state.input_payload = {"company": "SAFE Review Company"}
        encoded = json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = ArtifactRef(
                "artifact-historical-proposal",
                "proposal",
                str(root / "historical.json"),
                hashlib.sha256(encoded).hexdigest(),
            )
            review = HumanReviewPresentationService(
                HumanReviewArtifactStore(root / "reviews")
            ).produce(state=legacy_state, source=source, output=legacy)

            self.assertEqual(review.product, "Historical strategic proposal")
            self.assertEqual(review.input_lineage, {})
            self.assertNotEqual(review.renderer_id, "fieldwork_proposal_pdf")

    def test_current_internal_fieldwork_draft_renders_without_an_unapproved_fee(self) -> None:
        output = with_three_source_insights(proposal_output())
        encoded = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        checksum = hashlib.sha256(encoded).hexdigest()
        gate = passed_quality(checksum)
        source = ArtifactRef(
            "artifact-current-internal", "proposal", str(Path(tempfile.gettempdir()) / f"{checksum}.current-internal.json"), checksum,
            metadata={"proposal_presentation_quality": {
                "strategy_director_assessment_artifact_id": gate.strategy_director["assessment_artifact_id"],
                "creative_director_assessment_artifact_id": gate.creative_director["assessment_artifact_id"],
            }},
        )
        Path(source.location).write_bytes(encoded)
        proposal_state = state("discovery_evidence_to_growth_sprint_proposal")
        proposal_state.input_payload["commercial_context"].pop("approved_fieldwork_fee")
        append_quality_history(proposal_state, gate)
        with tempfile.TemporaryDirectory() as temporary:
            review = HumanReviewPresentationService(
                HumanReviewArtifactStore(Path(temporary) / "reviews")
            ).produce(state=proposal_state, source=source, output=output)
            self.assertEqual(review.renderer_id, "narratiive-fieldwork-proposal-pdf")
            self.assertEqual(review.input_lineage, {})
            visible = "\n".join(page.extract_text() or "" for page in PdfReader(review.location).pages)
            self.assertIn("No quantified opportunity stated", visible)
            self.assertNotIn("To validate", visible)

    def test_fieldwork_review_rejects_monetary_estimate_outside_discovery_lineage(self) -> None:
        proposal_state = state("discovery_evidence_to_growth_sprint_proposal")
        proposal_state.input_payload["discovery_evidence"] = {
            "notes": "Synthetic notes",
            "sources": [{"source_id": "meeting:notes:1", "source_type": "notes", "location": "synthetic:meeting"}],
        }
        output = proposal_output()
        output["commercial_opportunity"]["monetary_estimate"] = {
            "amount": 120000,
            "currency": "GBP",
            "basis": "The supplied Discovery notes describe the opportunity in enough detail.",
            "evidence_refs": ["forged:source"],
        }
        with self.assertRaisesRegex(HumanReviewArtifactError, "supplied Discovery evidence"):
            build_review_plan(proposal_state, output)

    def test_review_pdf_is_immutable_derived_output_and_excludes_runtime_metadata(self) -> None:
        output = with_three_source_insights(proposal_output())
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
            source_path.write_bytes(encoded)
            source = ArtifactRef(
                artifact_id="artifact-safe-source",
                artifact_type="growth_sprint_proposal",
                location=str(source_path),
                checksum=hashlib.sha256(encoded).hexdigest(),
                metadata={
                    "proposal_presentation_quality": {
                        "strategy_director_assessment_artifact_id": passed_quality(hashlib.sha256(encoded).hexdigest()).strategy_director["assessment_artifact_id"],
                        "creative_director_assessment_artifact_id": passed_quality(hashlib.sha256(encoded).hexdigest()).creative_director["assessment_artifact_id"],
                    }
                },
            )
            proposal_state = state("discovery_evidence_to_growth_sprint_proposal")
            reference = proposal_state.input_payload["commercial_context"]["approved_fieldwork_fee"]["approval_reference"]
            reference.update({"workspace_id": proposal_state.workspace_id, "client_id": proposal_state.client_id, "run_id": proposal_state.run_id, "source_artifact_checksum": source.checksum})
            proposal_state.approval_history.append({"approval_id": reference["approval_id"], "decision": "approved_fieldwork_fee", "fee_checksum": reference["fee_checksum"], "source_artifact_checksum": source.checksum})
            gate = passed_quality(source.checksum or "")
            append_quality_history(proposal_state, gate)
            review = HumanReviewPresentationService(
                HumanReviewArtifactStore(root / "reviews")
            ).produce(
                state=proposal_state,
                source=source,
                output=output,
            )

            self.assertEqual(source_path.read_bytes(), encoded)
            self.assertEqual(review.mime_type, "application/pdf")
            self.assertEqual(review.page_count, 2)
            visible = "\n".join(
                page.extract_text() or "" for page in PdfReader(review.location).pages
            )
            self.assertIn("F I E L D W O R K   P R O P O S A L", visible)
            self.assertIn("Approve\nFIELDWORK", visible)
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
            self.assertEqual(manifest["evidence_record"]["opportunity"]["classification"], "interpretation")
            self.assertIn("meeting:notes:1", manifest["evidence_record"]["opportunity"]["source_refs"])

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
