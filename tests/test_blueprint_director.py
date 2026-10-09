from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.blueprint_director import (
    BlueprintDirectorCommissionBuilder,
    BlueprintDirectorLearningStore,
    RAVE_CALIBRE_STANDARD,
)


class BlueprintDirectorTests(unittest.TestCase):
    def test_commission_receives_checksum_verified_canonical_guidance(self) -> None:
        commission = BlueprintDirectorCommissionBuilder().enrich(
            {"approved_strategy_thesis": {"thesis_statement": "Synthetic thesis"}},
            workspace_id="workspace-safe",
            client_id="client-safe",
        )

        guidance = commission["canonical_blueprint_guidance"]
        self.assertEqual(guidance["bundle"]["bundle_id"], "blueprint-canon-v1")
        self.assertIn("NARRATIIVE BLUEPRINT POPULATION SYSTEM", guidance["population_guidance"])
        self.assertEqual(len(guidance["slide_architecture"]["slides"]), 30)

    def test_rave_is_calibre_only_and_does_not_supply_rave_content(self) -> None:
        commission = BlueprintDirectorCommissionBuilder().enrich(
            {}, workspace_id="workspace-safe", client_id="client-safe"
        )

        reference = commission["rave_calibre_reference"]
        self.assertEqual(reference["standard"], RAVE_CALIBRE_STANDARD)
        self.assertIs(reference["content_template"], False)
        self.assertIn("Do not copy Rave", reference["prohibition"])
        self.assertNotIn("RAVE should be positioned", reference["presentation_guidance"])

    def test_only_matt_approved_work_can_become_a_positive_exemplar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = BlueprintDirectorLearningStore(Path(temporary) / "learning.jsonl", retrieval_limit=3)
            quality = {"passed": True, "axis_checks": {"strategic_coherence": True}}
            store.record_review(
                workspace_id="workspace-safe",
                client_id="client-safe",
                reviewer="Matt",
                accepted_strengths=["One coherent argument"],
                rejected_weaknesses=[],
                revision_reason="Approved after review",
                final_approved_artifact_reference={"artifact_id": "artifact-safe", "checksum": "a" * 64},
                quality_review_result=quality,
                approved=True,
            )
            retrieved = store.retrieve(workspace_id="workspace-safe", client_id="client-safe")
            self.assertEqual(len(retrieved["positive_exemplars"]), 1)
            self.assertEqual(
                retrieved["positive_exemplars"][0]["approved_artifact_reference"]["artifact_id"],
                "artifact-safe",
            )
            self.assertIs(retrieved["canonical_prompt_rewrite_allowed"], False)

    def test_rejected_work_is_failure_learning_never_a_positive_exemplar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = BlueprintDirectorLearningStore(Path(temporary) / "learning.jsonl", retrieval_limit=3)
            store.record_review(
                workspace_id="workspace-safe",
                client_id="client-safe",
                reviewer="Matt",
                accepted_strengths=["Useful diagnosis"],
                rejected_weaknesses=["Generic narrative"],
                revision_reason="The argument needs a more specific commercial choice",
                final_approved_artifact_reference=None,
                quality_review_result={"passed": False, "failed_checks": ["client specificity"]},
                approved=False,
            )
            retrieved = store.retrieve(workspace_id="workspace-safe", client_id="client-safe")
            self.assertEqual(retrieved["positive_exemplars"], [])
            self.assertEqual(len(retrieved["failure_patterns"]), 1)
            self.assertNotIn("approved_artifact_reference", retrieved["failure_patterns"][0])

    def test_retrieval_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = BlueprintDirectorLearningStore(Path(temporary) / "learning.jsonl", retrieval_limit=3)
            for index in range(6):
                store.record_review(
                    workspace_id="workspace-safe",
                    client_id="client-safe",
                    reviewer="Matt",
                    accepted_strengths=[],
                    rejected_weaknesses=[f"Weakness {index}"],
                    revision_reason=f"Revision {index}",
                    final_approved_artifact_reference=None,
                    quality_review_result={"passed": False, "failed_checks": [f"failure-{index}"]},
                    approved=False,
                )
            retrieved = store.retrieve(workspace_id="workspace-safe", client_id="client-safe")
            self.assertLessEqual(
                len(retrieved["positive_exemplars"]) + len(retrieved["failure_patterns"]),
                3,
            )


if __name__ == "__main__":
    unittest.main()
