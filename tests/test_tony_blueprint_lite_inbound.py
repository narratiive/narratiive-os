from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.inbound_leads import InboundLead
from runtime.tony_blueprint_lite_inbound import (
    FileBlueprintLitePreparationStore,
    TonyInboundBlueprintLiteService,
)


class TonyInboundBlueprintLiteTests(unittest.TestCase):
    def _lead(self) -> InboundLead:
        return InboundLead.from_mapping(
            {
                "lead_id": "lead-1",
                "contact": "Jamie Example",
                "company": "Example Co",
                "email": "jamie@example.invalid",
                "source": "Growth Diagnostic",
                "status": "New",
            }
        )

    def _payload(self) -> dict:
        return {
            "lead_id": "lead-1",
            "contact": "Jamie Example",
            "company": "Example Co",
            "source": "Growth Diagnostic",
            "diagnostic": {
                "challenge": "Unclear positioning",
                "overall_score": 54,
                "category_scores": {"clarity": 42, "visibility": 61},
                "main_blockage": "The proposition is difficult to distinguish",
                "recommended_actions": ["Sharpen the positioning"],
                "answers": {"growth_priority": "Win more high-value customers"},
            },
        }

    @staticmethod
    def _good_evidence() -> dict:
        return {
            "verified": True,
            "work_product": "A substantive internal Blueprint Lite work product.",
            "blueprint_lite": "What we heard; what we see; the tension; the opportunity; what this could mean; questions; invitation.",
            "diagnostic_signals_used": ["Unclear positioning", "Overall score 54", "Clarity score 42"],
            "diagnostic_input_coverage": {"complete": True, "missing_inputs": []},
            "source_backed_evidence": ["https://example.com/about"],
            "evidence_gaps": ["Private customer conversion data is unavailable"],
            "fact_interpretation_hypothesis_lineage": {
                "fact": ["The prospect reported unclear positioning"],
                "interpretation": ["Message clarity appears to lag commercial ambition"],
                "hypothesis": ["A sharper category position may improve choice"],
            },
            "growth_tension": "The business wants faster growth while its proposition remains hard to distinguish.",
            "provisional_opportunity": "Test a clearer and more memorable growth position.",
            "questions_to_answer_next": [
                "Which customers are most valuable?",
                "What most strongly predicts choice?",
                "Where does the current story lose people?",
            ],
            "quality_gate": {"human_review_ready": True},
            "recommendation": "advance",
        }

    def test_missing_claude_dispatcher_fails_closed_and_persists_one_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = FileBlueprintLitePreparationStore(Path(tmp) / "blueprint-lite.json")
            service = TonyInboundBlueprintLiteService(store, dispatchers={})
            result = service.ingest(self._lead(), self._payload())
            self.assertEqual(result["state"], "dispatcher_unavailable")
            self.assertEqual(result["blocker"], "claude_dispatcher_not_configured")
            self.assertFalse(result["external_action_taken"])
            persisted = store.get("lead-1")
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted["state"], "dispatcher_unavailable")
            self.assertEqual(persisted["dispatch"]["worker"], "Claude")
            self.assertEqual(persisted["dispatch"]["execution_mode"], "autonomous_prepare")

    def test_verified_blueprint_lite_is_versioned_and_stops_at_human_review(self) -> None:
        calls: list[dict] = []

        def claude(dispatch: dict) -> dict:
            calls.append(dispatch)
            return self._good_evidence()

        with tempfile.TemporaryDirectory() as tmp:
            store = FileBlueprintLitePreparationStore(Path(tmp) / "blueprint-lite.json")
            service = TonyInboundBlueprintLiteService(store, dispatchers={"Claude": claude})
            result = service.ingest(self._lead(), self._payload())
            self.assertEqual(result["state"], "awaiting_review")
            self.assertEqual(result["current_version"], 1)
            self.assertTrue(result["approval_required"])
            self.assertFalse(result["external_action_taken"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["worker"], "Claude")
            self.assertEqual(calls[0]["execution_mode"], "autonomous_prepare")
            self.assertIn("diagnostic_input_package", calls[0]["target"])
            persisted = store.get("lead-1")
            self.assertEqual(len(persisted["versions"]), 1)
            self.assertEqual(persisted["versions"][0]["evidence"]["blueprint_lite"], self._good_evidence()["blueprint_lite"])

            replay = service.ingest(self._lead(), self._payload())
            self.assertEqual(replay["state"], "awaiting_review")
            self.assertTrue(replay["replay"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(store.get("lead-1")["versions"]), 1)

    def test_incomplete_diagnostic_coverage_is_blocked_not_promoted(self) -> None:
        evidence = self._good_evidence()
        evidence["diagnostic_input_coverage"] = {
            "complete": False,
            "missing_inputs": ["category scores", "full diagnostic answers"],
        }
        evidence["quality_gate"] = {"human_review_ready": False}
        evidence["recommendation"] = "revise"

        with tempfile.TemporaryDirectory() as tmp:
            store = FileBlueprintLitePreparationStore(Path(tmp) / "blueprint-lite.json")
            service = TonyInboundBlueprintLiteService(store, dispatchers={"Claude": lambda dispatch: evidence})
            result = service.ingest(self._lead(), self._payload())
            self.assertEqual(result["state"], "blocked")
            self.assertEqual(result["blocker"], "blueprint_lite_quality_gate")
            self.assertIn("diagnostic input coverage complete", result["failed_checks"])
            self.assertIsNone(result["current_version"])
            self.assertFalse(result["approval_required"])


if __name__ == "__main__":
    unittest.main()
