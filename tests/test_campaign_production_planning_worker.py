from __future__ import annotations

import hashlib
import json
import unittest

from runtime.campaign_production_planning_worker import (
    CampaignProductionPlanningError,
    CampaignProductionPlanningWorker,
)
from runtime.workflow_quality import production_planning_quality_gate
from tests.test_workflow_quality import campaign_identity, creative_bible_output


def planning_contract() -> dict:
    bible = creative_bible_output()["creative_directors_bible"]
    checksum = hashlib.sha256(
        json.dumps(bible, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "campaign_identity": campaign_identity(),
        "approved_creative_bible": bible,
        "creative_bible_approval": {
            "decision": "creative_bible_approval",
            "approver": "telegram:matt",
            "rationale": "Approved exact version.",
            "creative_bible_checksum": checksum,
        },
        "production_constraints": ["No publication", "Human review required"],
        "workflow_context": {"workflow_id": "creative_bible_to_asset_production"},
    }


class CampaignProductionPlanningWorkerTests(unittest.TestCase):
    def test_approved_bible_generates_versioned_non_executing_production_pack(self) -> None:
        result = CampaignProductionPlanningWorker()(planning_contract())

        self.assertEqual(len(result["channel_asset_specifications"]), 18)
        self.assertEqual(len(result["production_tasks"]), 18)
        self.assertEqual(len(result["asset_manifest"]["assets"]), 18)
        self.assertTrue(all(task["human_review_required"] for task in result["production_tasks"]))
        self.assertTrue(all(not task["execution_authorised"] for task in result["production_tasks"]))
        self.assertFalse(result["production_executed"])
        self.assertFalse(result["publication_authorised"])
        self.assertFalse(result["media_spend_authorised"])
        self.assertTrue(production_planning_quality_gate(result)["passed"])

    def test_stale_bible_approval_is_rejected_before_planning(self) -> None:
        contract = planning_contract()
        contract["creative_bible_approval"]["creative_bible_checksum"] = "0" * 64

        with self.assertRaisesRegex(CampaignProductionPlanningError, "checksum"):
            CampaignProductionPlanningWorker()(contract)


if __name__ == "__main__":
    unittest.main()
