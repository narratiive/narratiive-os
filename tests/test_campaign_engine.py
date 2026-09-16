from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from runtime.campaign_engine import (
    CampaignEngine,
    CampaignEngineApplicationService,
    CampaignEngineError,
    CampaignEngineStage,
    CampaignEngineState,
    CampaignEngineStoreError,
    CampaignPortfolio,
    CampaignWorldSelectionBrief,
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
    blueprint = artifact("blueprint-1", "growth_blueprint", "blueprint-checksum")
    return CampaignEngineState(
        identity=CampaignIdentity(
            workspace_id="agency",
            client_id="safe-client",
            brand_id="safe-brand",
            market_ids=("uk",),
            product_ids=("safe-product",),
            campaign_id="safe-campaign",
        ),
        approved_blueprint=blueprint,
        blueprint_approval=HumanApproval(
            approver="matt",
            rationale="Approved strategy for campaign development.",
            artifact_id=blueprint.artifact_id,
            artifact_version=blueprint.version,
            artifact_checksum=blueprint.checksum,
        ),
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

    def test_campaign_bootstrap_requires_matt_blueprint_approval(self) -> None:
        current = state()
        delegated = HumanApproval(
            approver="tony",
            rationale="Tony cannot approve strategy.",
            artifact_id=current.approved_blueprint.artifact_id,
            artifact_version=current.approved_blueprint.version,
            artifact_checksum=current.approved_blueprint.checksum,
        )
        with self.assertRaisesRegex(CampaignEngineError, "Growth Blueprint approval requires Matt"):
            CampaignEngineState(
                identity=current.identity,
                approved_blueprint=current.approved_blueprint,
                blueprint_approval=delegated,
            )

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

    def test_tony_cannot_approve_campaign_world_selection_for_matt(self) -> None:
        current = self._world_review_state()
        for candidate_id, checksum in (("a", "checksum-a"), ("b", "checksum-b")):
            current = self.engine.review_campaign_world(
                current,
                candidate_id,
                quality_review=quality(checksum),
                tony_review=tony(checksum),
            )
        selected = current.campaign_world_candidates[0].artifact
        delegated = HumanApproval(
            "tony",
            "Tony recommends but may not select.",
            selected.artifact_id,
            selected.version,
            selected.checksum,
        )
        with self.assertRaisesRegex(CampaignEngineError, "Campaign World approval requires Matt"):
            self.engine.select_campaign_world(current, "a", delegated)

    def test_application_service_persists_idempotent_matt_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            service = CampaignEngineApplicationService(repository)
            current = self._world_review_state()
            for candidate_id, checksum in (("a", "checksum-a"), ("b", "checksum-b")):
                current = self.engine.review_campaign_world(
                    current,
                    candidate_id,
                    quality_review=quality(checksum),
                    tony_review=tony(checksum),
                )
            repository.save(current, transition_id="selection-ready")
            selected = current.campaign_world_candidates[0].artifact

            persisted = service.select_campaign_world(
                current,
                "a",
                approval(selected),
                transition_id="matt-selects-a",
            )
            replayed = service.select_campaign_world(
                current,
                "a",
                approval(selected),
                transition_id="matt-selects-a",
            )

            self.assertEqual(persisted, replayed)
            self.assertEqual(persisted.selected_campaign_world, selected)
            self.assertEqual(persisted.stage, CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT)

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
        self.assertEqual(current.creative_bible_source_world_id, selected.artifact_id)
        self.assertEqual(current.creative_bible_source_world_version, selected.version)
        self.assertEqual(current.creative_bible_source_world_checksum, selected.checksum)
        current = self.engine.review_creative_bible(
            current,
            quality_review=quality("bible-checksum"),
            tony_review=tony("bible-checksum"),
        )
        self.assertEqual(current.stage, CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED)
        self.assertTrue(current.requires_matt)
        current = self.engine.approve_creative_bible(current, approval(bible))
        self.assertEqual(current.stage, CampaignEngineStage.PRODUCTION_PLANNING)

    def test_creative_bible_lineage_cannot_be_detached_from_selected_world(self) -> None:
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

        with self.assertRaisesRegex(CampaignEngineStoreError, "lineage must match"):
            CampaignEngineState.from_dict(
                {
                    **current.to_dict(),
                    "creative_bible_source_world_checksum": "different-world-checksum",
                }
            )

    def test_revised_creative_bible_clears_prior_reviews_and_retains_world_lineage(self) -> None:
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
        first = artifact("bible-1", "creative_directors_bible", "bible-checksum-1")
        current = self.engine.submit_creative_bible(current, first)
        current = self.engine.review_creative_bible(
            current,
            quality_review=quality("bible-checksum-1", QualityVerdict.REVISE),
            tony_review=tony("bible-checksum-1", TonyDisposition.RETURN),
        )
        revised = VersionedArtifact(
            artifact_id="bible-1",
            artifact_type="creative_directors_bible",
            version="1.1",
            checksum="bible-checksum-2",
            location="drive://narratiive/bible-1-v1.1",
        )

        current = self.engine.submit_creative_bible(current, revised)

        self.assertIsNone(current.creative_bible_quality_review)
        self.assertIsNone(current.creative_bible_tony_review)
        self.assertIsNone(current.creative_bible_approval)
        self.assertEqual(current.creative_bible_source_world_checksum, selected.checksum)

    def test_legacy_creative_bible_state_derives_selected_world_lineage(self) -> None:
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
        current = self.engine.submit_creative_bible(
            current,
            artifact("bible-1", "creative_directors_bible", "bible-checksum"),
        )
        legacy = current.to_dict()
        legacy.pop("creative_bible_source_world_id")
        legacy.pop("creative_bible_source_world_version")
        legacy.pop("creative_bible_source_world_checksum")

        restored = CampaignEngineState.from_dict(legacy)

        self.assertEqual(restored.creative_bible_source_world_id, selected.artifact_id)
        self.assertEqual(restored.creative_bible_source_world_checksum, selected.checksum)

    def test_tony_cannot_approve_creative_bible_for_matt(self) -> None:
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
        delegated = HumanApproval(
            "tony",
            "Tony recommends but may not approve.",
            bible.artifact_id,
            bible.version,
            bible.checksum,
        )
        with self.assertRaisesRegex(CampaignEngineError, "Creative Director's Bible approval requires Matt"):
            self.engine.approve_creative_bible(current, delegated)

    def test_campaign_preparation_never_authorises_publication_or_spend(self) -> None:
        current = state()
        self.assertFalse(current.publication_authorised)
        self.assertFalse(current.media_spend_authorised)
        with self.assertRaisesRegex(CampaignEngineError, "cannot authorise"):
            CampaignEngineState(
                identity=current.identity,
                approved_blueprint=current.approved_blueprint,
                blueprint_approval=current.blueprint_approval,
                publication_authorised=True,
            )

    def test_campaign_bootstrap_requires_exact_blueprint_approval_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            service = CampaignEngineApplicationService(repository)
            proposed = state()
            created, replay = service.start_campaign(
                identity=proposed.identity,
                approved_blueprint=proposed.approved_blueprint,
                blueprint_approval=proposed.blueprint_approval,
                transition_id="campaign-start-1",
            )
            self.assertFalse(replay)
            self.assertEqual(created.stage, CampaignEngineStage.STRATEGY_APPROVED)
            replayed, replay = service.start_campaign(
                identity=proposed.identity,
                approved_blueprint=proposed.approved_blueprint,
                blueprint_approval=proposed.blueprint_approval,
                transition_id="campaign-start-retry",
            )
            self.assertTrue(replay)
            self.assertEqual(replayed, created)

    def test_campaign_bootstrap_rejects_stale_approval_and_conflicting_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            service = CampaignEngineApplicationService(repository)
            proposed = state()
            stale = HumanApproval(
                approver="matt",
                rationale="Stale approval.",
                artifact_id=proposed.approved_blueprint.artifact_id,
                artifact_version=proposed.approved_blueprint.version,
                artifact_checksum="stale-checksum",
            )
            with self.assertRaisesRegex(CampaignEngineError, "exact artefact version"):
                service.start_campaign(
                    identity=proposed.identity,
                    approved_blueprint=proposed.approved_blueprint,
                    blueprint_approval=stale,
                    transition_id="campaign-start-stale",
                )
            service.start_campaign(
                identity=proposed.identity,
                approved_blueprint=proposed.approved_blueprint,
                blueprint_approval=proposed.blueprint_approval,
                transition_id="campaign-start-1",
            )
            different_blueprint = artifact(
                "blueprint-2",
                "growth_blueprint",
                "blueprint-checksum-2",
            )
            with self.assertRaisesRegex(CampaignEngineStoreError, "already exists"):
                service.start_campaign(
                    identity=proposed.identity,
                    approved_blueprint=different_blueprint,
                    blueprint_approval=approval(different_blueprint),
                    transition_id="campaign-start-2",
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

    def test_application_service_persists_only_from_exact_current_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            service = CampaignEngineApplicationService(repository)
            current = state()
            repository.save(current, transition_id="campaign-start")
            commissioned = self.engine.commission_campaign_worlds(current)

            persisted = service.persist_transition(
                current,
                commissioned,
                transition_id="commission-worlds",
            )

            self.assertEqual(persisted, commissioned)
            self.assertEqual(repository.load("safe-client", "safe-campaign"), commissioned)
            with self.assertRaisesRegex(CampaignEngineStoreError, "stale"):
                service.persist_transition(
                    current,
                    commissioned,
                    transition_id="stale-commission",
                )

    def test_persisted_transition_rejects_stage_skips_and_blueprint_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            current = state()
            repository.save(current, transition_id="campaign-start")
            skipped = CampaignEngineState(
                identity=current.identity,
                approved_blueprint=current.approved_blueprint,
                blueprint_approval=current.blueprint_approval,
                stage=CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT,
            )
            skipped = self.engine.submit_campaign_worlds(
                skipped,
                (candidate("a", "checksum-a"), candidate("b", "checksum-b")),
            )
            with self.assertRaisesRegex(CampaignEngineStoreError, "illegal persisted"):
                repository.save_transition(current, skipped, transition_id="skip-quality")

            replacement = artifact("blueprint-2", "growth_blueprint", "checksum-2")
            replaced = CampaignEngineState(
                identity=current.identity,
                approved_blueprint=replacement,
                blueprint_approval=approval(replacement),
                stage=CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT,
            )
            with self.assertRaisesRegex(CampaignEngineStoreError, "Blueprint evidence"):
                repository.save_transition(current, replaced, transition_id="replace-blueprint")

    def test_competing_campaign_reviews_cannot_silently_overwrite_each_other(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repository = FileCampaignEngineRepository(tmp, workspace_id="agency")
            expected = self._world_review_state()
            repository.save(expected, transition_id="quality-review-start")
            proposed = (
                self.engine.review_campaign_world(
                    expected,
                    "a",
                    quality_review=quality("checksum-a"),
                    tony_review=tony("checksum-a"),
                ),
                self.engine.review_campaign_world(
                    expected,
                    "b",
                    quality_review=quality("checksum-b"),
                    tony_review=tony("checksum-b"),
                ),
            )

            def persist(index: int):
                try:
                    repository.save_transition(
                        expected,
                        proposed[index],
                        transition_id=f"candidate-review-{index}",
                    )
                except CampaignEngineStoreError as exc:
                    return str(exc)
                return "saved"

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = sorted(pool.map(persist, range(2)))

            self.assertEqual(outcomes, ["campaign transition expected state is stale", "saved"])

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

    def test_selection_brief_compares_exact_versions_without_selecting_for_matt(self) -> None:
        current = self._world_review_state()
        current = self.engine.review_campaign_world(
            current,
            "a",
            quality_review=quality("checksum-a"),
            tony_review=tony("checksum-a"),
        )
        current = self.engine.review_campaign_world(
            current,
            "b",
            quality_review=quality("checksum-b", QualityVerdict.REVISE),
            tony_review=tony("checksum-b", TonyDisposition.RETURN),
        )

        brief = CampaignWorldSelectionBrief.build(current)

        self.assertTrue(brief["selection_required"])
        self.assertFalse(brief["auto_selection_authorised"])
        self.assertEqual(brief["human_selector"], "matt")
        self.assertEqual(brief["ready_candidate_ids"], ["a"])
        self.assertEqual(brief["revision_candidate_ids"], ["b"])
        self.assertEqual(brief["candidates"][0]["artifact_checksum"], "checksum-a")
        self.assertEqual(brief["candidates"][0]["tony_disposition"], "forward")


if __name__ == "__main__":
    unittest.main()
