from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from runtime import (
    CommandError,
    EvidencePack,
    EvidencePackStore,
    EvidenceRecord,
    FakeOpportunityCardEngine,
    FakeSpeculativeAssetProvider,
    FileOpportunityCardStore,
    OpportunityCardBlockedError,
    OpportunityCardEngineResponse,
    OpportunityCardRequest,
    OpportunityCardService,
    ResearchEngine,
    ResearchJob,
    ResearchRun,
    RuntimeCommandAPI,
    compose_local_runtime,
)
from runtime.research_engine import EvidenceSource, EvidenceSourcePolicy, LocalDocumentIngestionAdapter, WebRetrievalAdapter


REPO_ROOT = Path(__file__).resolve().parents[1]


class StaticResearchEngine:
    def __init__(self, run: ResearchRun) -> None:
        self._run = run

    def run(self, job: ResearchJob) -> ResearchRun:  # type: ignore[override]
        return self._run


class FailingResearchEngine:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def run(self, job: ResearchJob) -> ResearchRun:  # type: ignore[override]
        raise self.exc


class OpportunityCardPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = compose_local_runtime(self.root / "state", REPO_ROOT)
        self.company_url = "https://testgrowth.co"
        self.company_name = "Test Growth Co"
        self.workspace_id = "rave"
        self.client_id = "rave"

        def fetcher(url: str, timeout_seconds: int):
            return (
                (
                    "<html><body>"
                    "<h1>Test Growth Co</h1>"
                    "<p>We help teams grow with clearer positioning and a better conversion story.</p>"
                    "<p>Category: strategic growth services.</p>"
                    "</body></html>"
                ).encode("utf-8"),
                url,
            )

        research_root = self.root / "research"
        self.research_engine = ResearchEngine(
            research_root,
            adapters=[WebRetrievalAdapter(fetcher=fetcher), LocalDocumentIngestionAdapter(research_root)],
            store=EvidencePackStore(research_root),
        )
        self.service = OpportunityCardService(
            artifact_catalog=self.runtime.artifact_catalog,
            prompt_registry=self.runtime.prompt_registry,
            research_engine=self.research_engine,
            engine=FakeOpportunityCardEngine(),
            asset_provider=FakeSpeculativeAssetProvider(),
            store=FileOpportunityCardStore(self.root / "opportunity_cards"),
        )
        self.api = RuntimeCommandAPI(self.runtime, opportunity_card_service=self.service)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _request(self, **kwargs):
        return OpportunityCardRequest.from_company_url(
            self.company_url,
            company_name=self.company_name,
            workspace_id=self.workspace_id,
            client_id=self.client_id,
            metadata={"source": "test"},
            **kwargs,
        )

    def _duplicate_research_run(self) -> ResearchRun:
        evidence_root = self.root / "evidence"
        evidence_root.mkdir(parents=True, exist_ok=True)
        record_a = EvidenceRecord(
            evidence_id="ev_alpha",
            workspace_id=self.workspace_id,
            source_id="source-alpha",
            source_type="web",
            uri=self.company_url,
            title="Test Growth Co",
            content="Test Growth Co helps teams grow with a clearer promise.",
            excerpt="Test Growth Co helps teams grow with a clearer promise.",
            published_at=None,
            retrieved_at="2026-07-14T00:00:00+00:00",
            content_hash="hash-alpha",
            provenance=[{"adapter": "fake", "source_id": "source-alpha", "uri": self.company_url}],
            source_ids=["source-alpha"],
            aliases=["ev_beta"],
        )
        record_b = EvidenceRecord(
            evidence_id="ev_beta",
            workspace_id=self.workspace_id,
            source_id="source-beta",
            source_type="web",
            uri=self.company_url,
            title="Test Growth Co",
            content="Test Growth Co helps teams grow with a clearer promise.",
            excerpt="Test Growth Co helps teams grow with a clearer promise.",
            published_at=None,
            retrieved_at="2026-07-14T00:00:00+00:00",
            content_hash="hash-alpha",
            provenance=[{"adapter": "fake", "source_id": "source-beta", "uri": self.company_url}],
            source_ids=["source-beta"],
            aliases=[],
        )
        job = ResearchJob(
            job_id="opportunity_rave_dup--research",
            workspace_id=self.workspace_id,
            query="Test Growth Co lightweight prospect research",
            sources=(),
            claims=(),
            missing_inputs=(),
            lineage=(),
        )
        pack = EvidencePack(
            pack_id="pack_dup",
            workspace_id=self.workspace_id,
            job_id=job.job_id,
            query=job.query,
            created_at="2026-07-14T00:00:00+00:00",
            previous_pack_id=None,
            lineage=[job.job_id],
            sources=[
                {
                    "source_id": "source-alpha",
                    "workspace_id": self.workspace_id,
                    "source_type": "web",
                    "uri": self.company_url,
                    "title": "Test Growth Co",
                    "policy": {
                        "approved": True,
                        "allowed_domains": ["testgrowth.co"],
                        "allowed_schemes": ["https"],
                        "max_bytes": 250000,
                        "timeout_seconds": 10,
                        "allow_local_files": False,
                    },
                    "metadata": {},
                }
            ],
            records=[record_a.as_dict(), record_b.as_dict()],
            claims=[],
            unsupported_claims=[],
            evidence_aliases={"ev_beta": "ev_alpha"},
            missing_inputs=[],
            blockers=[],
            status="complete",
            source_policy={"workspace_scoped": True},
        )
        pack_path = evidence_root / "pack_dup.json"
        pack_path.write_text(json.dumps(pack.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return ResearchRun(
            job=job,
            evidence_pack=pack,
            pack_path=str(pack_path),
            status="complete",
            blockers=[],
            warnings=[],
            deduplicated_record_count=1,
        )

    def test_generate_creates_versioned_opportunity_card_with_lineage_and_artifacts(self) -> None:
        record = self.service.generate(self._request())

        self.assertEqual(record.version, 1)
        self.assertEqual(record.status, "ready_for_review")
        self.assertEqual(record.opportunity_card.company_name, self.company_name)
        self.assertEqual(record.opportunity_card.company_url, "https://testgrowth.co/")
        self.assertEqual(len(record.opportunity_card.speculative_asset_briefs), 3)
        self.assertTrue(record.opportunity_card.source_notes)
        self.assertTrue(record.opportunity_card.evidence_references)
        self.assertEqual(record.opportunity_card.lineage.prompt_id, "narratiive-opportunity-card")
        self.assertEqual(record.opportunity_card.lineage.research_pack_id, record.research_pack_id)
        self.assertIsNotNone(record.opportunity_card.lineage.structured_artifact)
        self.assertIsNotNone(record.opportunity_card.lineage.review_summary_artifact)
        self.assertIn("This work is speculative and uncommissioned.", record.opportunity_card.disclaimer)
        self.assertTrue((self.root / "opportunity_cards").exists())
        raw_bytes = Path(record.raw_response_artifact.artifact.location).read_bytes()
        self.assertEqual(hashlib.sha256(raw_bytes).hexdigest(), record.raw_response_artifact.artifact.checksum)
        self.assertEqual(record.research_pack_artifact.workspace_id, "legacy")
        self.assertEqual(record.opportunity_card.workspace_id, self.workspace_id)

    def test_raw_response_and_extensions_are_preserved(self) -> None:
        expected_raw_response: dict[str, str] = {}

        def build_raw_response(evidence_id: str) -> str:
            return json.dumps(
                {
                    "company_name": self.company_name,
                    "company_url": self.company_url,
                    "market_category_context": "Test category context",
                    "commercial_diagnosis": {
                        "statement": "The brand needs a clearer commercial reason to engage.",
                        "growth_constraint": "The promise is too broad.",
                        "evidence_ids": [evidence_id],
                        "source_notes": [{"text": "Note A", "evidence_ids": [evidence_id], "extra_note": "retain"}],
                        "is_hypothesis": False,
                        "confidence": 0.9,
                        "unexpected_field": "preserved",
                    },
                    "growth_opportunity": {
                        "statement": "Sharpen the promise.",
                        "evidence_ids": [evidence_id],
                        "is_hypothesis": False,
                    },
                    "narrative_direction": {
                        "statement": "Tell a tighter story.",
                        "strategic_shift": "From broad to specific.",
                        "evidence_ids": [evidence_id],
                        "is_hypothesis": False,
                    },
                    "creative_treatment": {
                        "creative_territory": "Territory A",
                        "treatment": "Directional treatment",
                        "asset_briefs": [
                            {
                                "asset_type": "hero_campaign_image",
                                "brief": "Hero",
                                "output_specification": "Image",
                                "evidence_ids": [evidence_id],
                                "is_hypothesis": True,
                                "extensions": {"keep_me": True},
                            },
                            {
                                "asset_type": "short_video_concept",
                                "brief": "Video",
                                "output_specification": "Storyboard",
                                "evidence_ids": [evidence_id],
                                "is_hypothesis": True,
                            },
                        ],
                        "evidence_ids": [evidence_id],
                        "is_hypothesis": True,
                        "extensions": {"new_visual_direction": "tight grid"},
                    },
                    "speculative_asset_briefs": [
                        {
                            "asset_type": "hero_campaign_image",
                            "brief": "Hero",
                            "output_specification": "Image",
                            "evidence_ids": [evidence_id],
                            "is_hypothesis": True,
                        },
                        {
                            "asset_type": "short_video_concept",
                            "brief": "Video",
                            "output_specification": "Storyboard",
                            "evidence_ids": [evidence_id],
                            "is_hypothesis": True,
                        },
                    ],
                    "outreach_draft": {
                        "subject": "Opportunity Card",
                        "body": "Draft body",
                        "call_to_action": "Review it",
                        "evidence_ids": [evidence_id],
                    },
                    "source_notes": [
                        {"text": "Source note A", "evidence_ids": [evidence_id], "extra": "retain"}
                    ],
                    "evidence_references": [
                        {"evidence_id": evidence_id, "source_note": "Source note A", "claim": "Claim", "confidence": 0.95}
                    ],
                    "recommended_next_conversation": "Ask Matt to review",
                    "disclaimer": "This work is speculative and uncommissioned.",
                    "confidence": 0.81,
                    "extensions": {"campaign_angle": "Keep me"},
                },
                indent=2,
                sort_keys=True,
            ) + "\n"

        def response_factory(request, prompt, research_pack, research_pack_artifact):
            evidence_id = next(record["evidence_id"] for record in research_pack.records if record.get("evidence_id"))
            expected_raw_response["value"] = build_raw_response(evidence_id)
            return OpportunityCardEngineResponse(
                raw_response=expected_raw_response["value"],
                provider_id="claude",
                model_id="claude-sonnet-4-5",
                prompt_id=prompt.prompt_id,
                prompt_version=prompt.version,
                prompt_checksum=prompt.checksum,
                requested_provider_id="claude",
                requested_model_id="claude-sonnet-4-5",
                routing_policy_id="claude_opportunity_card",
                routing_policy_version="1",
                provider_metadata={"provider_id": "claude", "model_id": "claude-sonnet-4-5"},
            )

        service = OpportunityCardService(
            artifact_catalog=self.runtime.artifact_catalog,
            prompt_registry=self.runtime.prompt_registry,
            research_engine=self.research_engine,
            engine=FakeOpportunityCardEngine(response_factory=response_factory),
            asset_provider=FakeSpeculativeAssetProvider(),
            store=FileOpportunityCardStore(self.root / "opportunity_cards_raw"),
        )

        record = service.generate(self._request())

        self.assertEqual(Path(record.raw_response_artifact.artifact.location).read_text(encoding="utf-8"), expected_raw_response["value"])
        self.assertEqual(record.opportunity_card.extensions["campaign_angle"], "Keep me")
        self.assertEqual(record.opportunity_card.commercial_diagnosis.extensions["unexpected_field"], "preserved")
        self.assertEqual(record.opportunity_card.creative_treatment.extensions["new_visual_direction"], "tight grid")
        self.assertEqual(record.opportunity_card.creative_treatment.asset_briefs[0].extensions["keep_me"], True)
        self.assertEqual(record.opportunity_card.source_notes[0].extensions["extra"], "retain")
        self.assertEqual(record.opportunity_card.status, "ready_for_review")

    def test_research_failure_blocks_generation(self) -> None:
        service = OpportunityCardService(
            artifact_catalog=self.runtime.artifact_catalog,
            prompt_registry=self.runtime.prompt_registry,
            research_engine=FailingResearchEngine(RuntimeError("timeout")),
            engine=FakeOpportunityCardEngine(),
            asset_provider=FakeSpeculativeAssetProvider(),
            store=FileOpportunityCardStore(self.root / "opportunity_cards_failure"),
        )

        with self.assertRaises(OpportunityCardBlockedError):
            service.generate(self._request())

    def test_unsupported_claim_is_recorded_and_blocks_the_card(self) -> None:
        def response_factory(request, prompt, research_pack, research_pack_artifact):
            payload = FakeOpportunityCardEngine()._default_payload(request, prompt, research_pack)
            payload["commercial_diagnosis"]["evidence_ids"] = []
            payload["commercial_diagnosis"]["is_hypothesis"] = False
            return payload

        service = OpportunityCardService(
            artifact_catalog=self.runtime.artifact_catalog,
            prompt_registry=self.runtime.prompt_registry,
            research_engine=self.research_engine,
            engine=FakeOpportunityCardEngine(response_factory=response_factory),
            asset_provider=FakeSpeculativeAssetProvider(),
            store=FileOpportunityCardStore(self.root / "opportunity_cards_blocked"),
        )

        record = service.generate(self._request())

        self.assertEqual(record.status, "blocked")
        self.assertTrue(
            any(
                finding.code in {"unsupported_claim", "missing_evidence_for_diagnosis"}
                and finding.severity in {"error", "blocking"}
                for finding in record.validation_findings
            )
        )

    def test_alias_evidence_ids_are_accepted(self) -> None:
        research_run = self._duplicate_research_run()
        service = OpportunityCardService(
            artifact_catalog=self.runtime.artifact_catalog,
            prompt_registry=self.runtime.prompt_registry,
            research_engine=StaticResearchEngine(research_run),
            engine=FakeOpportunityCardEngine(
                response_factory=lambda request, prompt, research_pack, research_pack_artifact: {
                    "company_name": self.company_name,
                    "company_url": self.company_url,
                    "market_category_context": "Alias evidence test",
                    "commercial_diagnosis": {
                        "statement": "The site needs a sharper commercial reason.",
                        "growth_constraint": "The promise is too broad.",
                        "evidence_ids": ["ev_beta"],
                        "source_notes": [{"text": "Uses alias evidence", "evidence_ids": ["ev_beta"]}],
                        "is_hypothesis": False,
                    },
                    "growth_opportunity": {
                        "statement": "Turn the proof into a repeatable commercial promise.",
                        "evidence_ids": ["ev_beta"],
                        "source_notes": [{"text": "Alias opportunity", "evidence_ids": ["ev_beta"]}],
                        "is_hypothesis": False,
                    },
                    "narrative_direction": {
                        "statement": "Reframe the story.",
                        "strategic_shift": "From generic to specific.",
                        "evidence_ids": ["ev_beta"],
                        "source_notes": [{"text": "Alias direction", "evidence_ids": ["ev_beta"]}],
                        "is_hypothesis": False,
                    },
                    "creative_treatment": {
                        "creative_territory": "Alias territory",
                        "treatment": "A speculative treatment",
                        "asset_briefs": [
                            {
                                "asset_type": "hero_campaign_image",
                                "brief": "Hero",
                                "output_specification": "Image",
                                "evidence_ids": ["ev_beta"],
                                "is_hypothesis": True,
                            },
                            {
                                "asset_type": "short_video_concept",
                                "brief": "Video",
                                "output_specification": "Storyboard",
                                "evidence_ids": ["ev_beta"],
                                "is_hypothesis": True,
                            },
                        ],
                        "evidence_ids": ["ev_beta"],
                        "is_hypothesis": True,
                    },
                    "speculative_asset_briefs": [
                        {
                            "asset_type": "hero_campaign_image",
                            "brief": "Hero",
                            "output_specification": "Image",
                            "evidence_ids": ["ev_beta"],
                            "is_hypothesis": True,
                        },
                        {
                            "asset_type": "short_video_concept",
                            "brief": "Video",
                            "output_specification": "Storyboard",
                            "evidence_ids": ["ev_beta"],
                            "is_hypothesis": True,
                        },
                    ],
                    "outreach_draft": {
                        "subject": "Alias test",
                        "body": "Body",
                        "call_to_action": "Review",
                        "evidence_ids": ["ev_beta"],
                    },
                    "source_notes": [{"text": "Alias source note", "evidence_ids": ["ev_beta"]}],
                    "evidence_references": [{"evidence_id": "ev_beta", "source_note": "Alias source note", "claim": "Alias claim"}],
                    "recommended_next_conversation": "Review with Matt",
                    "disclaimer": "This work is speculative and uncommissioned.",
                    "confidence": 0.9,
                }
            ),
            asset_provider=FakeSpeculativeAssetProvider(),
            store=FileOpportunityCardStore(self.root / "opportunity_cards_alias"),
        )

        record = service.generate(self._request())

        self.assertEqual(record.status, "ready_for_review")
        self.assertEqual(record.opportunity_card.commercial_diagnosis.evidence_ids, ("ev_beta",))
        self.assertEqual(record.opportunity_card.evidence_references[0].evidence_id, "ev_beta")
        self.assertEqual(record.opportunity_card.lineage.research_pack_id, "pack_dup")

    def test_review_approve_and_revise_create_new_versions(self) -> None:
        record = self.service.generate(self._request())
        approved = self.service.approve(record.job_id, reviewer_id="Matt", rationale="Approved for outreach")
        revised = self.service.revise(record.job_id, "Tighten the commercial hook", reviewer_id="Matt")

        self.assertEqual(approved.version, 2)
        self.assertEqual(approved.status, "approved")
        self.assertEqual(revised.version, 3)
        self.assertEqual(revised.status, "revision_requested")
        self.assertEqual(len(self.service.store.history_by_job(record.job_id)), 3)

    def test_command_api_routes_opportunity_commands(self) -> None:
        created = self.api.handle(
            {
                "command": "/opportunity",
                "company_url": self.company_url,
                "company_name": self.company_name,
                "workspace_id": self.workspace_id,
                "client_id": self.client_id,
            }
        )
        self.assertTrue(created["ok"])
        self.assertEqual(created["command"], "opportunity")
        self.assertEqual(created["data"]["company_name"], self.company_name)
        self.assertEqual(created["data"]["status"], "ready_for_review")

        job_id = created["data"]["job_id"]

        status = self.api.handle({"command": "/opportunity-status", "job_id": job_id})
        self.assertEqual(status["command"], "opportunity.status")
        self.assertEqual(status["data"]["opportunity_card"]["company_name"], self.company_name)

        review = self.api.handle({"command": "/opportunity-review", "job_id": job_id})
        self.assertEqual(review["command"], "opportunity.review")
        self.assertEqual(review["data"]["status"], "ready_for_review")

        approved = self.api.handle(
            {
                "command": "/opportunity-approve",
                "job_id": job_id,
                "reviewer_id": "Matt",
                "rationale": "Looks good",
            }
        )
        self.assertEqual(approved["command"], "opportunity.approve")
        self.assertEqual(approved["data"]["status"], "approved")

        revised = self.api.handle(
            {
                "command": "/opportunity-revise",
                "job_id": job_id,
                "instruction": "Tighten the angle",
                "reviewer_id": "Matt",
            }
        )
        self.assertEqual(revised["command"], "opportunity.revise")
        self.assertEqual(revised["data"]["status"], "revision_requested")


if __name__ == "__main__":
    unittest.main()
