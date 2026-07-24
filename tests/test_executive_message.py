import unittest

from runtime.executive_message import (
    EvidenceReference,
    ExecutiveConfidence,
    ExecutiveMessage,
    ExecutiveUrgency,
    build_executive_message,
)


class ExecutiveMessageTests(unittest.TestCase):
    def test_serializes_complete_evidence_linked_message(self):
        message = ExecutiveMessage(
            observation="Two approvals are waiting.",
            implication="Delivery cannot progress until they are reviewed.",
            recommendation="Review the oldest approval first.",
            human_effort="10 minutes",
            confidence=ExecutiveConfidence.HIGH,
            evidence=(EvidenceReference("approval:rave:17", "Rave approval"),),
            urgency=ExecutiveUrgency.TODAY,
            interruption_eligible=False,
        )

        self.assertEqual(
            message.to_dict(),
            {
                "observation": "Two approvals are waiting.",
                "implication": "Delivery cannot progress until they are reviewed.",
                "recommendation": "Review the oldest approval first.",
                "human_effort": "10 minutes",
                "confidence": "high",
                "evidence": [
                    {"reference": "approval:rave:17", "label": "Rave approval"}
                ],
                "urgency": "today",
                "interruption_eligible": False,
            },
        )

    def test_compact_render_uses_business_language_only(self):
        message = build_executive_message(
            observation="The Blueprint is ready for review.",
            implication="Client delivery is one decision away.",
            recommendation="Review and approve the Blueprint.",
            human_effort="15 minutes",
            evidence=["artifact:rave:blueprint:v3"],
        )

        rendered = message.render_compact()
        self.assertIn("Why it matters:", rendered)
        self.assertIn("Recommendation:", rendered)
        self.assertNotIn("Traceback", rendered)
        self.assertNotIn("provider", rendered.lower())

    def test_rejects_messages_without_recorded_evidence(self):
        with self.assertRaisesRegex(ValueError, "evidence"):
            ExecutiveMessage(
                observation="Work completed.",
                implication="The project advanced.",
                recommendation="Continue.",
                human_effort="None",
                confidence=ExecutiveConfidence.MEDIUM,
                evidence=(),
            )

    def test_rejects_routine_interruptions(self):
        with self.assertRaisesRegex(ValueError, "routine"):
            build_executive_message(
                observation="A routine update is available.",
                implication="No immediate decision is required.",
                recommendation="Read it when convenient.",
                human_effort="2 minutes",
                evidence=["event:123"],
                urgency=ExecutiveUrgency.ROUTINE,
                interruption_eligible=True,
            )

    def test_normalizes_mapping_evidence(self):
        message = build_executive_message(
            observation="A dependency is blocked.",
            implication="The live deployment cannot proceed.",
            recommendation="Reconnect the external service.",
            human_effort="5 minutes",
            evidence=[{"reference": "connection:drive", "label": "Drive status"}],
            confidence=ExecutiveConfidence.HIGH,
            urgency=ExecutiveUrgency.IMMEDIATE,
            interruption_eligible=True,
        )

        self.assertEqual(message.evidence[0].reference, "connection:drive")
        self.assertTrue(message.interruption_eligible)

    def test_rejects_blank_evidence_references(self):
        with self.assertRaisesRegex(ValueError, "evidence reference"):
            EvidenceReference("   ")


if __name__ == "__main__":
    unittest.main()
