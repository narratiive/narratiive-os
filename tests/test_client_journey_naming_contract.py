from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from runtime.workflow_registry import build_narratiive_workflow_registry


ROOT = Path(__file__).resolve().parents[1]


class ClientJourneyNamingContractTests(unittest.TestCase):
    def test_customer_names_are_versioned_and_map_to_existing_products(self) -> None:
        contract = (ROOT / "docs/product/CLIENT_JOURNEY_NAMING_CANON_V1.md").read_text(encoding="utf-8")
        self.assertIn("Version: 1.0.0", contract)
        self.assertIn("Decision: Matt, 22 October 2026", contract)
        for customer_name, implementation in (
            ("`Groundwork`", "Blueprint Lite pre-sales assessment"),
            ("`Fieldwork`", "The paid strategic engagement"),
            ("`Sketchbook`", "The existing Campaign World"),
            ("`Activation`", "Downstream campaign execution"),
        ):
            self.assertRegex(
                contract,
                rf"\| {re.escape(customer_name)} \| {re.escape(implementation)}",
            )
        self.assertIn("Activation is outside", contract)

    def test_terminology_policy_approves_customer_names_without_losing_internal_terms(self) -> None:
        policy = json.loads((ROOT / "knowledge/proposition/terminology.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["version"], "1.2.0")
        approved = {item["term"]: item["use"] for item in policy["approved_terms"]}
        for term in ("Groundwork", "Fieldwork", "Sketchbook", "Activation"):
            self.assertIn(term, approved)
        for term in ("Growth Sprint", "Growth Blueprint", "Campaign World", "Creative Bible"):
            self.assertIn(term, approved)
        retired = {item["term"]: item for item in policy["retired_terms"]}
        self.assertNotIn("Growth Sprint", retired)
        self.assertIn("use Fieldwork", approved["Growth Sprint"])
        aliases = {item["term"]: item["replacement"] for item in policy["customer_facing_aliases"]}
        self.assertEqual(aliases, {"Blueprint Lite": "Groundwork", "Growth Sprint": "Fieldwork"})

    def test_customer_names_do_not_rename_executable_workflows(self) -> None:
        workflow_ids = {item.workflow_id for item in build_narratiive_workflow_registry().all()}
        self.assertIn("growth_diagnostic_to_blueprint_lite", workflow_ids)
        self.assertIn("growth_sprint_to_research_engine", workflow_ids)
        self.assertIn("growth_blueprint_to_campaign_world", workflow_ids)
        self.assertIn("campaign_world_to_creative_bible", workflow_ids)
        self.assertNotIn("groundwork", workflow_ids)
        self.assertNotIn("fieldwork", workflow_ids)
        self.assertNotIn("sketchbook", workflow_ids)
        self.assertNotIn("activation", workflow_ids)


if __name__ == "__main__":
    unittest.main()
