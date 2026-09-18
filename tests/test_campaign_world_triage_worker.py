from __future__ import annotations

import unittest

from runtime.campaign_world_triage_worker import CampaignWorldTriageWorker
from runtime.workflow_quality import campaign_world_triage_quality_gate
from tests.test_workflow_quality import campaign_world_candidates_output


class CampaignWorldTriageWorkerTests(unittest.TestCase):
    def test_tony_forwards_strong_distinct_routes_without_selecting(self) -> None:
        result = CampaignWorldTriageWorker()({
            **campaign_world_candidates_output(),
            "workflow_context": {
                "workflow_id": "growth_blueprint_to_campaign_world",
                "stage_id": "triage_campaign_world_candidates",
            },
        })

        self.assertTrue(campaign_world_triage_quality_gate(result)["passed"])
        self.assertEqual(len(result["selection_brief"]["ready_candidate_ids"]), 3)
        self.assertEqual(result["selection_brief"]["human_selector"], "matt")
        self.assertFalse(result["selection_brief"]["auto_selection_authorised"])
        self.assertFalse(result["publication_authorised"])
        self.assertFalse(result["media_spend_authorised"])

    def test_duplicate_route_is_returned_and_selection_gate_blocks_if_choice_is_too_narrow(self) -> None:
        payload = campaign_world_candidates_output()
        payload["campaign_world_candidates"][1]["campaign_world"] = payload["campaign_world_candidates"][0]["campaign_world"]
        payload["campaign_world_candidates"][2]["campaign_world"] = payload["campaign_world_candidates"][0]["campaign_world"]
        result = CampaignWorldTriageWorker()({
            **payload,
            "workflow_context": {"workflow_id": "growth_blueprint_to_campaign_world"},
        })

        self.assertEqual(result["campaign_world_reviews"][0]["tony_disposition"], "forward")
        self.assertEqual(result["campaign_world_reviews"][1]["tony_disposition"], "return")
        self.assertEqual(result["campaign_world_reviews"][2]["tony_disposition"], "return")
        self.assertFalse(campaign_world_triage_quality_gate(result)["passed"])


if __name__ == "__main__":
    unittest.main()
