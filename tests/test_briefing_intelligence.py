import tempfile
import unittest
from pathlib import Path

from runtime.agency_executive_brief import AgencyExecutiveBriefService
from runtime.agency_state import AgencyArea, AgencyItem, AgencyState
from runtime.agency_state_projection import AgencyStateProjector
from runtime.briefing_intelligence import (
    BriefingDecision,
    BriefingDecisionType,
    ExecutiveBriefingPipeline,
    FileBriefingBaselineStore,
    FileBriefingDecisionRegister,
)
from runtime.inbound_leads import InboundLead
from runtime.mission_control import MissionControlSnapshot, WorkstreamStatus


def snapshot(*, workstreams=(), approvals=(), workflow_runs=()):
    return MissionControlSnapshot(
        generated_at="2026-10-22T08:00:00Z",
        status="healthy",
        progress={"status": "healthy"},
        workstreams=tuple(workstreams),
        connections=(),
        approvals_required=tuple(approvals),
        blockers=(),
        workflow_runs=tuple(workflow_runs),
    )


def item(
    entity_id="entity-1",
    *,
    significance="P3",
    area=AgencyArea.DELIVERY,
    title="Current delivery status",
    blocked=False,
    blocks_agency_outcome=False,
):
    return AgencyItem(
        item_id=f"item-{entity_id}",
        entity_id=entity_id,
        area=area,
        title=title,
        status="blocked" if blocked else "active",
        next_action="Resolve the verified current exception before Friday.",
        owner="Tony",
        evidence=("workflow:current",),
        blocked=blocked,
        blocks_agency_outcome=blocks_agency_outcome,
        classification="operational_exception",
        significance=significance,
        why_matters="The current delivery commitment is at risk.",
    )


class BriefingIntelligenceFailureCaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.decisions_path = root / "decisions.jsonl"
        self.baseline_path = root / "baseline.json"
        self.register = FileBriefingDecisionRegister(self.decisions_path)
        self.baseline = FileBriefingBaselineStore(self.baseline_path)
        self.pipeline = ExecutiveBriefingPipeline(
            decision_register=self.register,
            baseline_store=self.baseline,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_01_suspicious_warm_submission_is_not_a_briefing_opportunity(self):
        lead = InboundLead(
            "lead-suspicious",
            "Unknown sender",
            company="Backlink Services",
            email="pitch@example.com",
            source="Growth Diagnostic",
            status="New",
            pipeline_stage="New Diagnostic",
            lead_temperature="Warm",
        )
        state = AgencyStateProjector().project(
            snapshot(), (lead,), lead_source_available=True
        )

        self.assertEqual(lead.briefing_classification(), "suspicious_or_unverified")
        self.assertFalse(any("Unknown sender" in value.title for value in self.pipeline.refine(state).items))

    def test_02_internal_correspondence_is_not_a_commercial_opportunity(self):
        lead = InboundLead(
            "lead-internal",
            "Operations",
            email="ops@narratiive.com",
            source="Gmail administrative",
            status="Qualified",
            pipeline_stage="Qualified",
        )

        self.assertEqual(lead.briefing_classification(), "internal_or_administrative")
        self.assertEqual(self.pipeline.refine(AgencyState.from_items("now", (lead.to_agency_item(),))).items, ())

    def test_03_multiple_workflow_attempts_collapse_to_current_authoritative_run(self):
        runs = (
            {"run_id": "old", "entity_id": "delivery-account", "workflow_id": "blueprint", "updated_at": "2026-10-20T10:00:00Z"},
            {"run_id": "current", "entity_id": "delivery-account", "workflow_id": "blueprint", "updated_at": "2026-10-21T10:00:00Z"},
        )
        state = AgencyStateProjector().project(snapshot(
            workstreams=(
                WorkstreamStatus("workflow:old", "Old blueprint attempt", "functional", "Tony", "Ignore superseded work"),
                WorkstreamStatus("workflow:current", "Current blueprint attempt", "functional", "Tony", "Complete current artefact"),
            ),
            workflow_runs=runs,
        ))

        titles = {value.title for value in state.items}
        self.assertNotIn("Old blueprint attempt", titles)
        self.assertIn("Current blueprint attempt", titles)

    def test_04_historical_versions_do_not_generate_duplicate_approvals(self):
        runs = (
            {"run_id": "old", "entity_id": "delivery-account", "company": "Account", "workflow_id": "blueprint", "updated_at": "2026-10-20T10:00:00Z"},
            {"run_id": "current", "entity_id": "delivery-account", "company": "Account", "workflow_id": "blueprint", "updated_at": "2026-10-21T10:00:00Z", "proposed_next_action": "Approve the current evidence-backed blueprint."},
        )
        state = AgencyStateProjector().project(snapshot(
            approvals=("workflow:old:approval", "workflow:current:approval"),
            workflow_runs=runs,
        ))

        approvals = tuple(value for value in state.items if value.requires_matt)
        self.assertEqual(len(approvals), 1)
        self.assertIn("Approve the current evidence-backed blueprint", approvals[0].next_action)

    def test_05_same_blocker_is_not_repeated_across_sections(self):
        blocker = item(
            "lead-capture",
            significance="P0",
            area=AgencyArea.AUTOMATION,
            title="Lead capture unavailable",
            blocked=True,
            blocks_agency_outcome=True,
        )
        output = AgencyExecutiveBriefService().build(
            AgencyState.from_items("now", (blocker,))
        ).render_compact()

        self.assertEqual(output.count("Lead capture unavailable"), 1)

    def test_06_suppression_survives_a_new_pipeline_instance(self):
        self.register.append(BriefingDecision.create(
            entity_id="dismissed-entity",
            aliases=("Dismissed item",),
            decision_type=BriefingDecisionType.SUPPRESS,
            reason="Founder instructed Tony to stop reporting this.",
            source="telegram",
        ))
        restarted = ExecutiveBriefingPipeline(
            decision_register=FileBriefingDecisionRegister(self.decisions_path),
            baseline_store=FileBriefingBaselineStore(self.baseline_path),
        )

        result = restarted.refine(AgencyState.from_items("later", (item("dismissed-entity"),)))
        self.assertEqual(result.items, ())

    def test_07_unchanged_issue_is_not_repeated(self):
        state = AgencyState.from_items("first", (item(),))
        first = self.pipeline.refine(state)
        self.baseline.store(self.pipeline.snapshot(first, period="morning"))

        self.assertEqual(self.pipeline.refine(AgencyState.from_items("later", (item(),))).items, ())

    def test_08_new_critical_issue_overrides_prior_suppression(self):
        self.register.append(BriefingDecision.create(
            entity_id="entity-1",
            decision_type=BriefingDecisionType.SUPPRESS,
            reason="Routine updates are not useful.",
        ))
        critical = item(
            significance="P0",
            title="Critical delivery outage",
            blocked=True,
            blocks_agency_outcome=True,
        )

        self.assertEqual(self.pipeline.refine(AgencyState.from_items("now", (critical,))).items, (critical,))

    def test_09_no_material_changes_produces_an_explicit_short_result(self):
        brief = AgencyExecutiveBriefService().build(AgencyState.from_items("now", ()))

        self.assertIn("Material changes: none", brief.render_compact())
        self.assertEqual(brief.recommended_actions, ())

    def test_10_blocked_workflow_does_not_mark_whole_agency_blocked(self):
        state = AgencyStateProjector().project(snapshot(workstreams=(
            WorkstreamStatus(
                "workflow:blocked",
                "Blueprint revision",
                "blocked",
                "Tony",
                "Correct the current source lineage",
                blocker="Source lineage needs revision",
            ),
        )))
        brief = AgencyExecutiveBriefService().build(state)

        self.assertEqual(brief.status, "healthy")
        self.assertIn("agency is operational", brief.render_compact())

    def test_generic_founder_recommendation_fails_quality_validation(self):
        generic = AgencyItem(
            "approval-1",
            AgencyArea.DELIVERY,
            "Founder approval required",
            "decision_required",
            "Review and decide this item.",
            owner="Matt",
            evidence=("workflow:approval",),
            requires_matt=True,
            significance="P1",
            why_matters="The current delivery cannot progress without a decision.",
        )

        with self.assertRaisesRegex(ValueError, "generic founder recommendation"):
            self.pipeline.validate(AgencyState.from_items("now", (generic,)))


if __name__ == "__main__":
    unittest.main()
