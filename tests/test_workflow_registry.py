from __future__ import annotations

import unittest

from runtime.definitions import ApprovalPolicy, InputContract, OutputContract, StageDefinition, WorkflowDefinition
from runtime.workflow_registry import (
    GROWTH_DIAGNOSTIC_TO_BLUEPRINT_LITE,
    WorkflowNotFound,
    WorkflowRegistry,
    build_narratiive_workflow_registry,
)


class WorkflowRegistryTests(unittest.TestCase):
    def test_all_principal_production_workflows_are_registered_and_resolvable(self) -> None:
        registry = build_narratiive_workflow_registry()
        expected = {
            "growth_diagnostic_to_blueprint_lite",
            "blueprint_lite_to_discovery_preparation",
            "discovery_evidence_to_growth_sprint_proposal",
            "growth_sprint_to_research_engine",
            "research_to_growth_blueprint",
            "growth_blueprint_to_campaign_world",
            "campaign_world_to_creative_bible",
            "creative_bible_to_asset_production",
            "asset_review_to_delivery_preparation",
            "delivery_to_follow_up_next_action",
        }
        self.assertEqual({item.workflow_id for item in registry.all()}, expected)
        for workflow_id in expected:
            self.assertEqual(registry.resolve(workflow_id).workflow_id, workflow_id)

    def test_every_registered_step_has_an_executable_fail_safe_contract(self) -> None:
        for definition in build_narratiive_workflow_registry().all():
            self.assertEqual(definition.failure_policy, "block_and_escalate")
            self.assertFalse(definition.autonomous_handoff)
            for step in definition.stages:
                self.assertTrue(step.capability)
                self.assertTrue(step.input_contract.required_fields)
                self.assertTrue(step.output_contract.required_fields)
                self.assertTrue(step.quality_contract)
                self.assertGreaterEqual(step.retry_policy.max_attempts, 1)
                self.assertEqual(step.side_effect_classification, "preparation")
                self.assertTrue(step.approval_policy.before_external_action)

    def test_blueprint_lite_and_consequential_preparation_contracts_remain_human_gated(self) -> None:
        registry = build_narratiive_workflow_registry()
        self.assertIs(registry.resolve("growth_diagnostic_to_blueprint_lite"), GROWTH_DIAGNOSTIC_TO_BLUEPRINT_LITE)
        self.assertTrue(GROWTH_DIAGNOSTIC_TO_BLUEPRINT_LITE.approval_required)
        step = GROWTH_DIAGNOSTIC_TO_BLUEPRINT_LITE.stages[0]
        self.assertEqual(step.capability, "strategic_reasoning")
        self.assertEqual(step.agent_ref, "")
        discovery = registry.resolve("blueprint_lite_to_discovery_preparation").stages[0]
        self.assertIn("suggested_meeting_objective", discovery.output_contract.required_fields)
        self.assertTrue(discovery.approval_policy.required)
        proposal = registry.resolve("discovery_evidence_to_growth_sprint_proposal").stages[0]
        self.assertIn("draft_client_communication", proposal.output_contract.required_fields)
        self.assertTrue(proposal.approval_policy.required)
        delivery = registry.resolve("asset_review_to_delivery_preparation").stages[0]
        self.assertIn("proposed_delivery_action", delivery.output_contract.required_fields)
        self.assertTrue(delivery.approval_policy.required)

    def test_research_and_growth_blueprint_contracts_preserve_required_strategy_and_lineage(self) -> None:
        registry = build_narratiive_workflow_registry()
        research = registry.resolve("growth_sprint_to_research_engine").stages[0]
        self.assertIn("source_provenance", research.output_contract.required_fields)
        blueprint = registry.resolve("research_to_growth_blueprint").stages[0]
        self.assertEqual(
            set(blueprint.output_contract.required_fields),
            {
                "market_category_diagnosis",
                "audience",
                "growth_barriers",
                "source_of_difference",
                "positioning",
                "narrative",
                "growth_opportunity",
                "activation_implications",
                "evidence_lineage",
            },
        )
        self.assertTrue(blueprint.approval_policy.required)

    def test_unknown_duplicate_and_unsafe_workflows_fail_closed(self) -> None:
        registry = WorkflowRegistry()
        with self.assertRaises(WorkflowNotFound):
            registry.resolve("missing")

        safe_step = StageDefinition(
            "prepare",
            "worker",
            capability="copy_drafting",
            input_contract=InputContract(("input",)),
            output_contract=OutputContract(("output",)),
            quality_contract="quality",
        )
        definition = WorkflowDefinition("one", (safe_step,))
        registry.register(definition)
        with self.assertRaisesRegex(ValueError, "duplicate workflow_id"):
            registry.register(definition)

        dangling = WorkflowRegistry((WorkflowDefinition("dangling", (safe_step,), next_workflow_id="missing"),))
        with self.assertRaisesRegex(ValueError, "unknown next workflow"):
            dangling.validate()

        unsafe_step = StageDefinition(
            "send",
            "worker",
            capability="email_sending",
            input_contract=InputContract(("draft",)),
            output_contract=OutputContract(("receipt",)),
            quality_contract="send_contract",
            approval_policy=ApprovalPolicy(required=False),
            side_effect_classification="external_write",
        )
        with self.assertRaisesRegex(ValueError, "external-write workflow steps require approval"):
            WorkflowRegistry((WorkflowDefinition("unsafe", (unsafe_step,)),))


if __name__ == "__main__":
    unittest.main()
