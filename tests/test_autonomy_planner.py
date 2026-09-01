from __future__ import annotations

import unittest

from runtime.autonomy_planner import AutonomyAction, TonyAutonomyPlanner
from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage


def record(
    client_id: str,
    stage: ClientLifecycleStage,
    *,
    value: int | None = None,
    blocked: bool = False,
    blocker: str | None = None,
    requires_matt: bool = False,
) -> ClientLifecycleRecord:
    return ClientLifecycleRecord(
        client_id=client_id,
        client_name=f"Client {client_id}",
        stage=stage,
        owner="Tony",
        next_action=f"Next action for {client_id}",
        evidence=(f"evidence:{client_id}",),
        blocked=blocked,
        blocker=blocker,
        requires_matt=requires_matt,
        value_gbp=value,
    )


class TonyAutonomyPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = TonyAutonomyPlanner()

    def test_blocked_work_escalates_before_any_other_rule(self):
        decision = self.planner.decide(
            record(
                "blocked",
                ClientLifecycleStage.RESEARCH,
                blocked=True,
                blocker="Missing verified category evidence",
            )
        )
        self.assertEqual(decision.action, AutonomyAction.ESCALATE)
        self.assertTrue(decision.requires_human)
        self.assertEqual(decision.reason, "Missing verified category evidence")

    def test_explicit_matt_requirement_stops_internal_work(self):
        decision = self.planner.decide(
            record("decision", ClientLifecycleStage.BLUEPRINT_LITE, requires_matt=True)
        )
        self.assertEqual(decision.action, AutonomyAction.APPROVAL)
        self.assertTrue(decision.requires_human)

    def test_internal_preparation_stages_may_continue(self):
        for stage in (
            ClientLifecycleStage.LEAD,
            ClientLifecycleStage.RESEARCH,
            ClientLifecycleStage.BLUEPRINT_LITE,
            ClientLifecycleStage.COMPLETE,
        ):
            with self.subTest(stage=stage):
                decision = self.planner.decide(record(stage.value, stage))
                self.assertEqual(decision.action, AutonomyAction.CONTINUE)
                self.assertFalse(decision.requires_human)

    def test_consequence_stages_require_human_gate(self):
        for stage in (
            ClientLifecycleStage.OUTREACH,
            ClientLifecycleStage.MEETING,
            ClientLifecycleStage.PROPOSAL,
            ClientLifecycleStage.DELIVERY,
            ClientLifecycleStage.INVOICE,
        ):
            with self.subTest(stage=stage):
                decision = self.planner.decide(record(stage.value, stage))
                self.assertEqual(decision.action, AutonomyAction.APPROVAL)
                self.assertTrue(decision.requires_human)

    def test_decision_preserves_operational_context(self):
        source = record("context", ClientLifecycleStage.RESEARCH, value=8000)
        decision = self.planner.decide(source)
        self.assertEqual(decision.next_action, source.next_action)
        self.assertEqual(decision.evidence, source.evidence)
        self.assertEqual(decision.value_gbp, 8000)

    def test_plan_separates_autonomous_work_from_human_attention_deterministically(self):
        plan = self.planner.plan(
            (
                record("research-low", ClientLifecycleStage.RESEARCH, value=3000),
                record("proposal", ClientLifecycleStage.PROPOSAL, value=8000),
                record("blocked", ClientLifecycleStage.RESEARCH, value=1000, blocked=True, blocker="Need evidence"),
                record("blueprint", ClientLifecycleStage.BLUEPRINT_LITE, value=6000),
                record("invoice", ClientLifecycleStage.INVOICE, value=12000),
            )
        )
        self.assertEqual(
            [item.client_id for item in plan.autonomous_queue],
            ["blueprint", "research-low"],
        )
        self.assertEqual(
            [item.client_id for item in plan.human_queue],
            ["blocked", "invoice", "proposal"],
        )
        self.assertEqual(plan.human_queue[0].action, AutonomyAction.ESCALATE)


if __name__ == "__main__":
    unittest.main()
