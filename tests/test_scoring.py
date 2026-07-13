import tempfile
import unittest
from pathlib import Path

from runtime.artifact_catalog import FileArtifactCatalog
from runtime.dispatch import DispatchJob
from runtime.execution_package import ExecutionPackageBuilder
from runtime.scoring import (
    ArtifactSignal,
    ConfidenceEngine,
    EvidenceSignal,
    ScoreRecommendation,
    ScoringInput,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def complete_input():
    return ScoringInput(
        artifacts=(
            ArtifactSignal(
                artifact_id="research",
                stage_id="research_analyst",
            ),
            ArtifactSignal(
                artifact_id="strategy",
                stage_id="strategy_director",
                parent_artifact_ids=("research",),
                expected_parent_artifact_ids=("research",),
                strategic_checks={
                    "growth_problem": True,
                    "positioning": True,
                    "strategic_choice": True,
                },
            ),
            ArtifactSignal(
                artifact_id="campaign",
                stage_id="campaign_world_generator",
                parent_artifact_ids=("strategy",),
                expected_parent_artifact_ids=("strategy",),
                creative_checks={"campaign_translation": True},
            ),
            ArtifactSignal(
                artifact_id="creative",
                stage_id="creative_director",
                parent_artifact_ids=("campaign",),
                expected_parent_artifact_ids=("campaign",),
                creative_checks={
                    "distinctive_platform": True,
                    "production_guidance": True,
                },
            ),
        ),
        evidence=(
            EvidenceSignal(
                evidence_id="audience-need",
                supported=True,
                source_quality=90,
                source_artifact_ids=("research",),
            ),
            EvidenceSignal(
                evidence_id="product-proof",
                supported=True,
                source_quality=80,
                source_artifact_ids=("research",),
            ),
        ),
    )


def partial_input():
    return ScoringInput(
        artifacts=(
            ArtifactSignal(
                artifact_id="research",
                stage_id="research_analyst",
            ),
            ArtifactSignal(
                artifact_id="strategy",
                stage_id="strategy_director",
                parent_artifact_ids=("research",),
                expected_parent_artifact_ids=("research",),
                open_inputs=("competitor_validation",),
                strategic_checks={
                    "growth_problem": True,
                    "positioning": False,
                    "strategic_choice": True,
                },
            ),
            ArtifactSignal(
                artifact_id="campaign",
                stage_id="campaign_world_generator",
                parent_artifact_ids=(),
                expected_parent_artifact_ids=("strategy",),
                creative_checks={
                    "campaign_translation": True,
                    "distinctive_platform": False,
                    "production_guidance": True,
                },
            ),
        ),
        evidence=(
            EvidenceSignal(
                evidence_id="audience-need",
                supported=True,
                source_quality=70,
                source_artifact_ids=("research",),
            ),
            EvidenceSignal(
                evidence_id="product-proof",
                supported=False,
                source_quality=0,
            ),
        ),
    )


class ConfidenceEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = ConfidenceEngine()

    def test_complete_fixture_recommends_approve(self):
        scorecard = self.engine.score(complete_input())

        self.assertEqual(scorecard.evidence_coverage.value, 100)
        self.assertEqual(scorecard.source_quality.value, 85)
        self.assertEqual(scorecard.strategic_confidence.value, 100)
        self.assertEqual(scorecard.creative_confidence.value, 100)
        self.assertEqual(scorecard.overall_risk.value, 2)
        self.assertEqual(scorecard.recommendation, ScoreRecommendation.APPROVE)
        self.assertTrue(scorecard.policy_reasons)

    def test_partial_fixture_recommends_revision_with_explicit_reasons(self):
        scorecard = self.engine.score(partial_input())

        self.assertEqual(scorecard.evidence_coverage.value, 50)
        self.assertEqual(scorecard.strategic_confidence.value, 67)
        self.assertEqual(scorecard.creative_confidence.value, 67)
        self.assertEqual(scorecard.recommendation, ScoreRecommendation.REVISE)
        reasons = " ".join(scorecard.policy_reasons)
        self.assertIn("evidence coverage", reasons)
        self.assertIn("Open inputs", reasons)
        self.assertIn("lineage completeness", reasons)

    def test_unsupported_fixture_recommends_block(self):
        scoring_input = ScoringInput(
            artifacts=complete_input().artifacts,
            evidence=(
                EvidenceSignal(
                    evidence_id="fabricated-proof",
                    supported=False,
                    source_quality=0,
                ),
            ),
            unsupported_claims=("fabricated-proof",),
        )
        scorecard = self.engine.score(scoring_input)

        self.assertEqual(scorecard.recommendation, ScoreRecommendation.BLOCK)
        self.assertGreaterEqual(scorecard.overall_risk.value, 85)
        self.assertIn("fabricated-proof", " ".join(scorecard.policy_reasons))

    def test_missing_evidence_does_not_change_strategy_or_creative_scores(self):
        complete = self.engine.score(complete_input())
        missing = self.engine.score(
            ScoringInput(
                artifacts=complete_input().artifacts,
                evidence=(
                    complete_input().evidence[0],
                    EvidenceSignal(
                        evidence_id="product-proof",
                        supported=False,
                        source_quality=0,
                    ),
                ),
            )
        )

        self.assertLess(
            missing.evidence_coverage.value,
            complete.evidence_coverage.value,
        )
        self.assertGreater(
            missing.overall_risk.value,
            complete.overall_risk.value,
        )
        self.assertEqual(
            missing.strategic_confidence,
            complete.strategic_confidence,
        )
        self.assertEqual(
            missing.creative_confidence,
            complete.creative_confidence,
        )

    def test_same_inputs_produce_identical_auditable_scorecards(self):
        first = self.engine.score(complete_input())
        second = self.engine.score(complete_input())

        self.assertEqual(first, second)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertTrue(first.scorecard_id.startswith("score-"))
        self.assertEqual(len(first.input_checksum), 64)
        for dimension in (
            first.evidence_coverage,
            first.source_quality,
            first.strategic_confidence,
            first.creative_confidence,
            first.overall_risk,
        ):
            self.assertTrue(dimension.reasons)

    def test_rejects_non_boolean_check_markers(self):
        payload = complete_input().to_dict()
        payload["artifacts"][1]["strategic_checks"]["positioning"] = "yes"
        with self.assertRaises(ValueError):
            ScoringInput.from_dict(payload)

    def test_artifact_signal_uses_catalog_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = FileArtifactCatalog(Path(temporary))
            research = catalog.register(
                run_id="run-1",
                stage_id="research",
                artifact_type="research",
                content="research",
            )
            strategy = catalog.register(
                run_id="run-1",
                stage_id="strategy",
                artifact_type="strategy",
                content="strategy",
                parent_artifact_ids=(research.artifact.artifact_id,),
            )
            signal = ArtifactSignal.from_record(
                strategy,
                expected_parent_artifact_ids=(research.artifact.artifact_id,),
                open_inputs=("pricing",),
            )

        self.assertEqual(
            signal.parent_artifact_ids,
            (research.artifact.artifact_id,),
        )
        self.assertEqual(signal.open_inputs, ("pricing",))


class QualityReviewerScorecardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = ConfidenceEngine()
        self.builder = ExecutionPackageBuilder(
            REPOSITORY_ROOT,
            {
                "strategy_director": "completed_growth_blueprint",
                "quality_reviewer": "completed_quality_review",
            },
            confidence_engine=self.engine,
        )

    def test_only_quality_reviewer_receives_scorecard(self):
        context = {"scoring_input": complete_input().to_dict()}
        quality = self.builder.build(
            DispatchJob(
                job_id="run-1--quality_reviewer",
                run_id="run-1",
                stage_id="quality_reviewer",
                agent_ref="agents/quality_reviewer.md",
                payload=context,
            )
        )
        strategy = self.builder.build(
            DispatchJob(
                job_id="run-1--strategy_director",
                run_id="run-1",
                stage_id="strategy_director",
                agent_ref="agents/strategy_director.md",
                payload=context,
            )
        )

        self.assertEqual(
            quality.confidence_scorecard["recommendation"],
            "approve",
        )
        self.assertNotIn("verdict", quality.confidence_scorecard)
        self.assertIsNone(strategy.confidence_scorecard)


if __name__ == "__main__":
    unittest.main()
