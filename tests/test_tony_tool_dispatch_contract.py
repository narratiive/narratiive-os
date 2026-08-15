from __future__ import annotations

import unittest

from runtime.tony_tool_routing import TonyExecutiveToolRouter


class TonyToolDispatchContractTests(unittest.TestCase):
    def test_autonomous_gmail_read_is_ready_for_dispatch_with_evidence_contract(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "commercial",
                "label": "Check Lesley's reply",
                "action": "Retrieve the verified email thread and assess the reply.",
                "target": {"lead_id": "lesley"},
            }
        )

        dispatch = handoff["dispatch"]
        self.assertFalse(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "autonomous_read")
        self.assertTrue(dispatch["eligible"])
        self.assertEqual(dispatch["state"], "ready_for_autonomous_dispatch")
        self.assertEqual(dispatch["worker"], "Gmail")
        self.assertEqual(dispatch["target"]["lead_id"], "lesley")
        self.assertIn("verified read result", dispatch["expected_evidence"])
        self.assertEqual(dispatch["return_to"], "Tony")
        self.assertEqual(dispatch["execution_truth"], "not_dispatched")

    def test_claude_internal_work_is_ready_for_autonomous_dispatch(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "delivery",
                "label": "Client proposition",
                "action": "Develop the strategic recommendation and draft the client brief.",
            }
        )

        dispatch = handoff["dispatch"]
        self.assertEqual(handoff["execution_mode"], "autonomous_prepare")
        self.assertTrue(dispatch["eligible"])
        self.assertEqual(dispatch["state"], "ready_for_autonomous_dispatch")
        self.assertIn("internal work product", dispatch["expected_evidence"])

    def test_external_send_cannot_enter_autonomous_dispatch(self):
        handoff = TonyExecutiveToolRouter().route(
            {
                "area": "commercial",
                "label": "Reply to Lesley",
                "action": "Send the approved follow-up email.",
                "target": {"lead_id": "lesley"},
            }
        )

        dispatch = handoff["dispatch"]
        self.assertTrue(handoff["approval_required"])
        self.assertEqual(handoff["execution_mode"], "approval_gated_write")
        self.assertFalse(dispatch["eligible"])
        self.assertEqual(dispatch["state"], "awaiting_approval")
        self.assertIn("explicit approval", dispatch["expected_evidence"])
        self.assertEqual(dispatch["execution_truth"], "not_dispatched")

    def test_stateful_read_can_dispatch_but_stateful_write_cannot(self):
        router = TonyExecutiveToolRouter()
        inspect = router.route(
            {
                "area": "engineering",
                "label": "Repository health",
                "action": "Inspect the GitHub test suite and summarise the failing checks.",
            }
        )
        deploy = router.route(
            {
                "area": "engineering",
                "label": "Runtime deployment",
                "action": "Deploy the approved runtime change.",
            }
        )

        self.assertTrue(inspect["dispatch"]["eligible"])
        self.assertEqual(inspect["dispatch"]["state"], "ready_for_autonomous_dispatch")
        self.assertFalse(deploy["dispatch"]["eligible"])
        self.assertEqual(deploy["dispatch"]["state"], "awaiting_approval")


if __name__ == "__main__":
    unittest.main()
