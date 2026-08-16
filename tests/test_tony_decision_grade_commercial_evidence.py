from __future__ import annotations

import unittest

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService


class TonyDecisionGradeCommercialEvidenceTests(unittest.TestCase):
    def test_commercial_gmail_read_requires_substantive_content(self):
        dispatch = {
            "worker": "Gmail",
            "execution_mode": "autonomous_read",
            "action": "check the verified email thread for a reply before Tony decides the next commercial move",
            "target": {"lead_id": "lead-1", "contact": "Lesley Harman"},
        }

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(
            dispatch,
            {"read_only": True, "thread_id": "thread-1"},
        )

        self.assertFalse(verified)
        self.assertIn("decision-grade commercial read content is missing", reason)

    def test_commercial_gmail_read_accepts_verified_summary(self):
        dispatch = {
            "worker": "Gmail",
            "execution_mode": "autonomous_read",
            "action": "retrieve the verified email thread for this lead so Tony can assess the response",
            "target": {"lead_id": "lead-1", "contact": "Lesley Harman"},
        }

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(
            dispatch,
            {
                "read_only": True,
                "thread_id": "thread-1",
                "summary": "Lesley replied positively and asked for times for a discovery call.",
            },
        )

        self.assertTrue(verified)
        self.assertEqual(reason, "verified read evidence")

    def test_noncommercial_read_still_only_requires_source_proof(self):
        dispatch = {
            "worker": "GitHub",
            "execution_mode": "autonomous_read",
            "action": "inspect the latest runtime validation",
            "target": {"item_id": "runtime-check"},
        }

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(
            dispatch,
            {"read_only": True, "commit_sha": "abc123"},
        )

        self.assertTrue(verified)
        self.assertEqual(reason, "verified read evidence")


if __name__ == "__main__":
    unittest.main()
