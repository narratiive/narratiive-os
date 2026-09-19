from __future__ import annotations

import unittest

from runtime.creative_bible_triage_worker import CreativeBibleTriageWorker
from runtime.workflow_quality import creative_bible_triage_quality_gate
from tests.test_workflow_quality import creative_bible_output


class CreativeBibleTriageWorkerTests(unittest.TestCase):
    def test_complete_bible_is_forwarded_without_granting_approval(self) -> None:
        contract = creative_bible_output()
        contract["workflow_context"] = {"workflow_id": "campaign_world_to_creative_bible"}

        result = CreativeBibleTriageWorker()(contract)

        self.assertEqual(result["creative_bible_review"]["tony_disposition"], "forward")
        self.assertTrue(result["creative_bible_approval_brief"]["requires_matt"])
        self.assertFalse(result["creative_bible_approval_brief"]["auto_approval_authorised"])
        self.assertFalse(result["production_authorised"])
        self.assertFalse(result["publication_authorised"])
        self.assertFalse(result["media_spend_authorised"])
        self.assertTrue(creative_bible_triage_quality_gate(result)["passed"])

    def test_weak_bible_is_returned_and_quality_gate_blocks_it(self) -> None:
        contract = creative_bible_output()
        contract["workflow_context"] = {"workflow_id": "campaign_world_to_creative_bible"}
        contract["creative_directors_bible"]["camera_language"] = {}

        result = CreativeBibleTriageWorker()(contract)

        self.assertEqual(result["creative_bible_review"]["tony_disposition"], "return")
        self.assertFalse(result["creative_bible_approval_brief"]["requires_matt"])
        self.assertFalse(creative_bible_triage_quality_gate(result)["passed"])


if __name__ == "__main__":
    unittest.main()
