from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from runtime.campaign_engine import (
    CampaignEngine,
    CampaignEngineError,
    CampaignEngineStage,
    CampaignEngineState,
    CampaignEngineStoreError,
    CampaignPortfolio,
    CampaignIdentity,
    CampaignWorldCandidate,
    HumanApproval,
    QualityReview,
    QualityVerdict,
    TonyDisposition,
    TonyTasteReview,
    VersionedArtifact,
    FileCampaignEngineRepository,
)


def artifact(artifact_id: str, artifact_type: str, checksum: str) -> VersionedArtifact:
    return VersionedArtifact(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        version="1.0",
        checksum=checksum,
        location=f"drive://narratiive/{artifact_id}",
    )


def state() -> CampaignEngineState:
    return CampaignEngineState(
        identity=CampaignIdentity(
            workspace_id="agency",
            client_id="safe-client",
            brand_id="safe-brand",
            market_ids=("uk",),
            product_ids=("safe-product",),
            campaign_id="safe-campaign",
        ),
        approved_blueprint=artifact("blueprint-1", "growth_blueprint", "blueprint-checksum"),
    )


def candidate(candidate_id: str, checksum: str) -> CampaignWorldCandidate:
    return CampaignWorldCandidate(
        candidate_id=candidate_id,
        artifact=artifact(f"world-{candidate_id}", "campaign_world", checksum),
    )


def quality(checksum: str, verdict: QualityVerdict = QualityVerdict.PASS) -> QualityReview:
    return QualityReview(
        verdict=verdict,
        reviewer="quality-reviewer",
        rationale="The candidate is strategically grounded, distinctive and executable.",
        reviewed_artifact_checksum=checksum,
    )


def tony(checksum: str, disposition: TonyDisposition = TonyDisposition.FORWARD) -> TonyTasteReview:
    return TonyTasteReview(
        disposition=disposition,
        rationale="This clears the Narratiive taste bar and is worth Matt's attention.",
        reviewed_artifact_checksum=checksum,
    )


def approval(item: VersionedArtifact) -> HumanApproval:
    return HumanApproval(
        approver="matt",
        rationale="Selected as the strongest strategic and creative route.",
        artifact_id=item.artifact_id,
        artifact_version=item.version,
        artifact_checksum=item.checksum,
    )


class CampaignEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CampaignEngine()

    def _world_review_state(self) -> CampaignEngineState:
        current = self.engine.commission_campaign_worlds(state())
        return self.engine.submit_campaign_worlds(
            current,
            (candidate("a", "checksum-a"), candidate("b", "checksum-b")),
        )

    def test_campaign_identity_requires_client_brand_market_product_and_campaign(self) -> None:
        with self.assertRaisesRegex(CampaignEngineError, "market_id"):
            CampaignIdentity("agency", "client", "brand", (), ("product",), "campaign")

    def test_multiple_campaign_worlds_are_required(self) -> None:
        current = self.engine.commission_campaign_worlds(state())
        with self.assertRaisesRegex(CampaignEngineError, "at least two"):
            self.engine.submit_campaign_worlds(current, (candidate("a", "checksum-a"),))

    def test_tony_cannot_forward_a_candidate_that_failed_quality_review(self) -> None:
        current = self._world_review_state()
        with self.assertRaisesRegex(CampaignEngineError, "failed independent quality review"):
            self.engine.review_campaign_world(
                current,
                "a",
                quality_review=quality("checksum-a", QualityVerdict.REVISE),
                tony_review=tony("checksum-a"),
            )

    def test_only_reviewed_candidates_reach_matt_selection(self) -> None:
        current = self._world_review_state()
        current = self.engine.review_campaign_world(
            current,
            "a",
            quality_review=quality("checksum-a"),
            tony_review=tony("checksum-a"),
        )
        self.assertEqual(current.stage, CampaignEngineStage.CAMPAIGN_WORLDS_IN_QUALITY_REVIEW)
        current = self.engine.review_campaign_world(
            current,
            "b",
            quality_review=quality("checksum-b"),
            tony_review=tony("checksum-b", TonyDisposition.RETURN),
        )
        self.assertEqual(current.stage, CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED)
        self.assertTrue(current.requires_matt)

    def test_all_rejected_candidates_return_to_development(self) -> None:
        current = self._world_review_state()
        for candidate_id, checksum in (("a", "checksum-a"), ("b", "checksum-b")):
            current = self.engine.review_campaign_world(
                current,
                candidate_id,
                quality_review=quality(checksum, QualityVerdict.REVISE),
                tony_review=tony(checksum, TonyDisposition.RETURN),
            )
        self.assertEqual(current.stage, CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT)

    def test_selection_is_bound_to_exact_candidate_version(self) -> None:
        current = self._world_review_state()
        for candidate_id, checksum in (("a", "checksum-a"), ("b", "checksum-b")):
            current = self.engine.review_campaign_world(
                current,
                candidate_id,
                quality_review=quality(checksum),
                tony_review=tony(checksum),
            )
        selected = current.campaign_world_candidates[0].artifact
        stale = HumanApproval("matt", "Approved", selected.artifact_id, selected.version, "stale")
        with self.assertRaisesRegex(CampaignEngineError, "exact artefact version"):
            self.engine.select_campaign_world(current, "a", stale)
        current = self.engine.select_campaign_world(current, "a", approval(selected))
        self.assertEqual(current.stage, CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT)
        self.assertEqual(current.selected_campaign_world, selected)

    def test_creative_bible_must_pass_quality_and_tony_before_matt(self) -> None:
        current = self._world_review_state()
        for candidate_id, checksum in (("a", "checksum-a"), ("b", "checksum-b")):
            current = self.engine.review_campaign_world(
                current,
                candidate_id,
                quality_review=quality(checksum),
                tony_review=tony(checksum),
            )
        selected = current.campaign_world_candidates[0].artifact
        current = self.engine.select_campaign_world(current, "a", approval(selected))
        bible = artifact("bible-1", "creative_directors_bible", "bible-checksum")
        current = self.engine.submit_creative_bible(current, bible)
        current = self.engine.review_creative_bible(
            current,
            quality_review=quality("bible-checksum"),
            tony_review=tony("bible-checksum"),
        )
        self.assertEqual(current.stage, CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED)
        self.assertTrue(current.requires_matt)
        current = self.engine.approve_creative_bible(current, approval(bible))
        self.assertEqual(current.stage, CampaignEngineStage.PRODUCTION_PLANNING)

    def test_campaign_preparation_never_authorises_publication_or_spend(self) -> None:
        current = state()
        self.assertFalse(current.publication_authorised)
        self.assertFalse(current.media_spend_authorised)
        with self.assertRaisesRegex(CampaignEngineError, "cannot authorise"):
            CampaignEngineState(
                identity=current.identity,
                approved_blueprint=current.approved_blueprint,
                publication_authorised=True,
            )

    def test_repository_persists_and_replays_workspace_scoped_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            current = self.engine.commission_campaign_worlds(state())
            repository.save(current, transition_id="commission-1")
            loaded = repository.load("safe-client", "safe-campaign")
            self.assertEqual(loaded, current)
            replayed = repository.save(current, transition_id="commission-1")
            self.assertEqual(replayed, current)

    def test_repository_rejects_conflicting_idempotency_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            repository.save(state(), transition_id="transition-1")
            changed = self.engine.commission_campaign_worlds(state())
            with self.assertRaisesRegex(CampaignEngineStoreError, "conflicts"):
                repository.save(changed, transition_id="transition-1")

    def test_repository_detects_tampered_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            repository.save(state(), transition_id="transition-1")
            path = Path(tmp) / "agency" / "safe-client" / "safe-campaign.jsonl"
            record = json.loads(path.read_text(encoding="utf-8"))
            record["state"]["stage"] = CampaignEngineStage.PRODUCTION_PLANNING.value
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(CampaignEngineStoreError, "hash mismatch"):
                repository.load("safe-client", "safe-campaign")

    def test_concurrent_transitions_preserve_one_valid_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            current = state()
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(
                    pool.map(
                        lambda index: repository.save(
                            current,
                            transition_id=f"transition-{index}",
                        ),
                        range(20),
                    )
                )
            self.assertEqual(repository.load("safe-client", "safe-campaign"), current)
            path = Path(tmp) / "agency" / "safe-client" / "safe-campaign.jsonl"
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 20)

    def test_portfolio_prioritises_human_gates_across_clients(self) -> None:
        base = state()
        current = self._world_review_state()
        current = self.engine.review_campaign_world(
            current,
            "a",
            quality_review=quality("checksum-a"),
            tony_review=tony("checksum-a"),
        )
        other = self.engine.review_campaign_world(
            current,
            "b",
            quality_review=quality("checksum-b"),
            tony_review=tony("checksum-b"),
        )
        snapshot = CampaignPortfolio.build((base, other))
        self.assertEqual(snapshot.human_gate_count, 1)
        self.assertEqual(snapshot.campaigns[0].client_id, "safe-client")
        self.assertTrue(snapshot.campaigns[0].requires_matt)


if __name__ == "__main__":
    unittest.main()
