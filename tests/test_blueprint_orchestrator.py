from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from runtime.artifact_catalog import ArtifactRecord
from runtime.blueprint_orchestrator import (
    BlueprintBlockedError,
    BlueprintContextArtifacts,
    BlueprintRoutingMismatchError,
    BlueprintOrchestrator,
    BlueprintRequest,
    FakeBlueprintEngine,
    FileBlueprintStore,
    ClaudeBlueprintEngine,
)
from runtime.blueprint_knowledge_registry import BlueprintKnowledgeRegistry
from runtime.command_api import RuntimeCommandAPI
from runtime.composition import compose_workspace_runtime
from runtime.provider import ProviderResponse
from runtime.workspaces import Workspace
from tests.blueprint_response_factory import render_canonical_blueprint_markdown


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "blueprint" / "rave_raw_response.md"


class BlueprintOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = Workspace("rave", "rave", "RAVE Coffee")
        self.runtime = compose_workspace_runtime(self.root / "state", REPO_ROOT, self.workspace)
        self.catalog = self.runtime.artifact_catalog
        self.prompts = self.runtime.prompt_registry
        self.store = FileBlueprintStore(self.root / "blueprints")
        self.knowledge_registry = BlueprintKnowledgeRegistry.from_default()
        self.fixture_response = render_canonical_blueprint_markdown(self.knowledge_registry.schema())
        self.legacy_fixture_response = FIXTURE_PATH.read_text(encoding="utf-8")
        self.engine = FakeBlueprintEngine(
            self.fixture_response,
            provider_id="router-provider",
            model_id="blueprint-model-v1",
        )
        self.orchestrator = BlueprintOrchestrator(
            artifact_catalog=self.catalog,
            prompt_registry=self.prompts,
            engine=self.engine,
            knowledge_registry=self.knowledge_registry,
            store=self.store,
        )

        self.research = self.catalog.register(
            run_id="rave-run",
            stage_id="research_analyst",
            artifact_type="completed_research",
            content="Approved research packet for RAVE.",
            producer="research_analyst@1",
        )
        self.strategy = self.catalog.register(
            run_id="rave-run",
            stage_id="strategy_director",
            artifact_type="completed_growth_blueprint",
            content="Approved growth blueprint for RAVE.",
            parent_artifact_ids=(self.research.artifact.artifact_id,),
            producer="strategy_director@1",
        )
        self.campaign = self.catalog.register(
            run_id="rave-run",
            stage_id="campaign_world_generator",
            artifact_type="completed_campaign_world",
            content="Approved campaign world for RAVE.",
            parent_artifact_ids=(self.strategy.artifact.artifact_id,),
            producer="campaign_world_generator@1",
        )
        self.creative = self.catalog.register(
            run_id="rave-run",
            stage_id="creative_director",
            artifact_type="completed_creative_directors_bible",
            content="Approved creative bible for RAVE.",
            parent_artifact_ids=(self.campaign.artifact.artifact_id,),
            producer="creative_director@1",
        )
        self.quality = self.catalog.register(
            run_id="rave-run",
            stage_id="quality_reviewer",
            artifact_type="completed_quality_review",
            content="Quality review approved for RAVE.",
            parent_artifact_ids=(self.creative.artifact.artifact_id,),
            producer="quality_reviewer@1",
        )
        self.evidence_ids = ("ev_deadbeef", "ev_cafebabe")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _request(self, *, request_id: str, blueprint_id: str = "rave-blueprint", approved: bool = True, draft_mode: bool = False, extra_creative: ArtifactRecord | None = None) -> BlueprintRequest:
        creative_artifacts = (self.creative,) if extra_creative is None else (self.creative, extra_creative)
        return BlueprintRequest(
            request_id=request_id,
            workspace_id="rave",
            client_id="rave",
            blueprint_id=blueprint_id,
            approved=approved,
            draft_mode=draft_mode,
            approved_context=BlueprintContextArtifacts(
                research_artifacts=(self.research,),
                strategy_artifacts=(self.strategy,),
                campaign_artifacts=(self.campaign,),
                creative_artifacts=creative_artifacts,
                quality_artifacts=(self.quality,),
                evidence_ids=self.evidence_ids,
            ),
            requested_by="testing",
        )

    @staticmethod
    def _flatten_slide_headings(sections):
        slides = []
        for act in sections:
            slides.extend(act.children)
        return slides

    def _orchestrator_for_response(self, response_text: str, *, store_suffix: str) -> BlueprintOrchestrator:
        return BlueprintOrchestrator(
            artifact_catalog=self.catalog,
            prompt_registry=self.prompts,
            engine=FakeBlueprintEngine(
                response_text,
                provider_id="router-provider",
                model_id="blueprint-model-v1",
            ),
            store=FileBlueprintStore(self.root / store_suffix),
            knowledge_registry=self.knowledge_registry,
        )

    def _canonical_response(self, **kwargs) -> str:
        return render_canonical_blueprint_markdown(self.knowledge_registry.schema(), **kwargs)

    def test_generates_and_versions_a_blueprint_without_flattening_the_raw_response(self) -> None:
        record = self.orchestrator.generate(self._request(request_id="blueprint-request-001"))

        self.assertEqual(record.version, 1)
        self.assertEqual(record.structured_blueprint.blueprint_version, 1)
        self.assertEqual(record.status, "complete")
        self.assertEqual(record.prompt_version, 1)
        self.assertEqual(record.provider_id, "router-provider")
        self.assertEqual(record.model_id, "blueprint-model-v1")
        self.assertEqual(record.requested_provider_id, "router-provider")
        self.assertEqual(record.requested_model_id, "blueprint-model-v1")
        self.assertEqual(record.routing_policy_id, "static")
        self.assertEqual(record.routing_policy_version, "1")
        self.assertEqual(record.structured_blueprint.document_title, "RAVE Blueprint")
        self.assertEqual(record.canon_bundle.bundle_id, "blueprint-canon-v1")
        self.assertEqual(record.canon_bundle.canon_version, "1.0.0")
        self.assertEqual(record.canon_bundle.prompt_asset_id, "blueprint_population_system")
        self.assertEqual(
            [component.asset_id for component in record.canon_bundle.components],
            [
                "blueprint_population_system",
                "blueprint_schema_v3",
                "visual_framework_library_v1",
                "visual_intelligence_system_v1",
            ],
        )
        self.assertTrue(record.raw_response_artifact.artifact.location.endswith(".md"))
        self.assertEqual(
            Path(record.raw_response_artifact.artifact.location).read_text(encoding="utf-8"),
            self.fixture_response,
        )
        self.assertIsNone(record.structured_blueprint.lineage.structured_artifact)
        self.assertEqual(len(record.structured_blueprint.sections), 6)
        self.assertEqual(len(record.structured_blueprint.slides), 30)
        self.assertEqual(
            [section.heading for section in record.structured_blueprint.sections],
            [
                "Act 1 — The Case for Change",
                "Act 2 — Market and Competitive Diagnosis",
                "Act 3 — Audience and Demand Opportunity",
                "Act 4 — Positioning and Narrative Answer",
                "Act 5 — The Growth System",
                "Act 6 — Implementation and Measurement",
            ],
        )
        self.assertEqual([slide.slide_no for slide in record.structured_blueprint.slides], list(range(1, 31)))
        self.assertEqual(record.structured_blueprint.slides[11].slide_name, "Audience Segments / Demand Pools")
        self.assertTrue(record.structured_blueprint.slides[11].founder_insight)
        self.assertTrue(record.structured_blueprint.slides[11].so_what)
        self.assertTrue(record.structured_blueprint.slides[11].content.source_notes)
        self.assertTrue(record.structured_blueprint.slides[26].content.visual_direction)
        self.assertTrue(record.structured_blueprint.slides[26].content.speaker_notes)
        self.assertTrue(record.structured_blueprint.slides[27].founder_insight)
        self.assertTrue(record.structured_blueprint.slides[27].so_what)
        self.assertTrue(record.structured_blueprint.slides[28].content.source_notes)
        self.assertTrue(record.structured_blueprint.slides[28].so_what)
        self.assertTrue(record.structured_blueprint.slides[29].content.source_notes)
        self.assertEqual(record.structured_blueprint.validation_findings, ())
        self.assertIn("ev_deadbeef", record.structured_blueprint.evidence_ids)
        self.assertEqual(record.change_summary, ())
        self.assertTrue(record.artifact_lineage)
        self.assertEqual(record.structured_blueprint.canon_bundle.bundle_id, "blueprint-canon-v1")
        self.assertEqual(record.structured_blueprint.lineage.canon_bundle.bundle_id, "blueprint-canon-v1")
        self.assertEqual(record.structured_blueprint.lineage.prompt_id, "claude-growth-blueprint")
        self.assertEqual(record.structured_blueprint.lineage.evidence_pack_ids, self.evidence_ids)
        prompt = self.prompts.active("claude-growth-blueprint")
        population_text = (REPO_ROOT / "knowledge" / "blueprint" / "population-system.md").read_text(encoding="utf-8")
        schema_text = (REPO_ROOT / "knowledge" / "blueprint" / "blueprint-schema-v3.md").read_text(encoding="utf-8")
        visual_text = (REPO_ROOT / "knowledge" / "blueprint" / "visual-framework-library-v1.md").read_text(encoding="utf-8")
        visual_intelligence_text = (REPO_ROOT / "knowledge" / "blueprint" / "visual-intelligence-system-v1.md").read_text(encoding="utf-8")
        self.assertEqual(
            prompt.metadata["source_path"],
            str(REPO_ROOT / "knowledge" / "blueprint" / "population-system.md"),
        )
        self.assertEqual(
            prompt.content,
            population_text,
        )
        self.assertEqual(
            prompt.checksum,
            hashlib.sha256(population_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(prompt.metadata["bundle"]["bundle_id"], "blueprint-canon-v1")
        self.assertEqual(prompt.metadata["bundle"]["canon_version"], "1.0.0")
        self.assertEqual(prompt.metadata["bundle"]["prompt_asset_id"], "blueprint_population_system")
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][0]["source_path"],
            str(REPO_ROOT / "knowledge" / "blueprint" / "blueprint-schema-v3.md"),
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][0]["source_checksum"],
            hashlib.sha256(schema_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][0]["asset_id"],
            "blueprint_schema_v3",
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][1]["source_path"],
            str(REPO_ROOT / "knowledge" / "blueprint" / "visual-framework-library-v1.md"),
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][1]["source_checksum"],
            hashlib.sha256(visual_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][1]["asset_id"],
            "visual_framework_library_v1",
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][2]["source_path"],
            str(REPO_ROOT / "knowledge" / "blueprint" / "visual-intelligence-system-v1.md"),
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][2]["source_checksum"],
            hashlib.sha256(visual_intelligence_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][2]["asset_id"],
            "visual_intelligence_system_v1",
        )
        self.assertEqual(prompt.metadata["prompt_asset"]["source_title"], "Narratiive Blueprint Population System")
        self.assertEqual(prompt.metadata["prompt_asset"]["drive_document_id"], "1Jna7vhjh5pdMtsSlxsOR8-QeCneaz9MFXcyrTl56HvE")
        self.assertTrue((self.store.root / "workspaces" / "rave" / "clients" / "rave" / "rave_blueprint" / "versions" / "v1.json").exists())

    def test_changed_inputs_create_a_new_version_with_machine_readable_summary(self) -> None:
        first = self.orchestrator.generate(self._request(request_id="blueprint-request-001"))
        extra = self.catalog.register(
            run_id="rave-run",
            stage_id="creative_director",
            artifact_type="completed_creative_directors_bible",
            content="Approved creative bible v2 for RAVE.",
            parent_artifact_ids=(self.campaign.artifact.artifact_id,),
            producer="creative_director@2",
        )
        second = self.orchestrator.generate(
            self._request(
                request_id="blueprint-request-002",
                extra_creative=extra,
            )
        )

        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertEqual(second.previous_version, 1)
        self.assertTrue(any(item.field == "input_checksum" for item in second.change_summary))
        self.assertFalse(any(item.field == "status" for item in second.change_summary))
        self.assertGreater(len(second.artifact_lineage), len(first.artifact_lineage))

    def test_direct_act_and_slide_response_parses_into_the_canonical_model(self) -> None:
        orchestrator = self._orchestrator_for_response(
            self._canonical_response(wrapped=False),
            store_suffix="blueprints-direct",
        )

        record = orchestrator.generate(self._request(request_id="blueprint-request-direct"))

        self.assertEqual(record.status, "complete")
        self.assertEqual(len(record.structured_blueprint.sections), 6)
        self.assertEqual(len(record.structured_blueprint.slides), 30)
        self.assertEqual(record.structured_blueprint.slides[0].slide_name, "Cover")

    def test_missing_slide_is_reported_without_rewriting_the_rest_of_the_blueprint(self) -> None:
        orchestrator = self._orchestrator_for_response(
            self._canonical_response(missing_slide_numbers=(17,)),
            store_suffix="blueprints-missing-slide",
        )

        record = orchestrator.generate(self._request(request_id="blueprint-request-missing-slide"))

        self.assertEqual(record.status, "invalid")
        self.assertTrue(any(finding.code == "missing_slide" for finding in record.validation_findings))
        self.assertEqual(len(record.structured_blueprint.slides), 30)
        self.assertEqual(record.structured_blueprint.slides[16].slide_name, "Positioning Problem")

    def test_duplicate_slide_is_reported_and_the_first_copy_is_preserved(self) -> None:
        orchestrator = self._orchestrator_for_response(
            self._canonical_response(duplicate_slide_numbers=(12,)),
            store_suffix="blueprints-duplicate-slide",
        )

        record = orchestrator.generate(self._request(request_id="blueprint-request-duplicate-slide"))

        self.assertEqual(record.status, "invalid")
        self.assertTrue(any(finding.code == "duplicate_slide" for finding in record.validation_findings))
        self.assertEqual(len(record.structured_blueprint.slides), 30)
        self.assertTrue(record.structured_blueprint.slides[11].content.source_notes)

    def test_wrong_act_membership_is_reported(self) -> None:
        orchestrator = self._orchestrator_for_response(
            self._canonical_response(act_heading_overrides={6: "Act 5 — The Growth System"}),
            store_suffix="blueprints-wrong-act",
        )

        record = orchestrator.generate(self._request(request_id="blueprint-request-wrong-act"))

        self.assertEqual(record.status, "invalid")
        self.assertTrue(any(finding.code == "wrong_act_membership" for finding in record.validation_findings))
        self.assertEqual(len(record.structured_blueprint.slides), 30)

    def test_malformed_slide_number_falls_back_to_the_canonical_name(self) -> None:
        orchestrator = self._orchestrator_for_response(
            self._canonical_response(slide_heading_overrides={12: "Slide 12A — Audience Segments / Demand Pools"}),
            store_suffix="blueprints-malformed-slide",
        )

        record = orchestrator.generate(self._request(request_id="blueprint-request-malformed-slide"))

        self.assertEqual(record.status, "complete")
        self.assertTrue(any(finding.code == "malformed_slide_number" for finding in record.validation_findings))
        self.assertEqual(record.structured_blueprint.slides[11].slide_name, "Audience Segments / Demand Pools")

    def test_unknown_extension_fields_are_preserved_without_loss(self) -> None:
        orchestrator = self._orchestrator_for_response(
            self._canonical_response(
                extra_sections_by_slide={
                    12: [("Appendix Notes", "Preserve this exact text without alteration.")],
                },
            ),
            store_suffix="blueprints-extension-preservation",
        )

        record = orchestrator.generate(self._request(request_id="blueprint-request-extension-preservation"))

        slide = record.structured_blueprint.slides[11]
        self.assertIn("Appendix Notes", slide.extensions)
        self.assertEqual(slide.extensions["Appendix Notes"]["body"], "Preserve this exact text without alteration.")
        self.assertTrue(slide.founder_insight)
        self.assertTrue(slide.so_what)

    def test_legacy_fixture_is_adapted_into_the_canonical_structure(self) -> None:
        orchestrator = self._orchestrator_for_response(
            self.legacy_fixture_response,
            store_suffix="blueprints-legacy-adapter",
        )

        record = orchestrator.generate(self._request(request_id="blueprint-request-legacy-adapter"))

        self.assertEqual(record.status, "complete")
        self.assertEqual(len(record.structured_blueprint.sections), 6)
        self.assertEqual(len(record.structured_blueprint.slides), 30)
        self.assertTrue(any(finding.severity == "warning" for finding in record.validation_findings))
        self.assertEqual(
            Path(record.raw_response_artifact.artifact.location).read_text(encoding="utf-8"),
            self.legacy_fixture_response,
        )

    def test_rejects_cross_workspace_artifacts_without_persisting_foreign_state(self) -> None:
        foreign = ArtifactRecord.from_dict(
            {
                **self.strategy.to_dict(),
                "workspace_id": "other",
            }
        )
        request = BlueprintRequest(
            request_id="blueprint-request-foreign",
            workspace_id="rave",
            client_id="rave",
            approved=True,
            approved_context=BlueprintContextArtifacts(
                research_artifacts=(self.research,),
                strategy_artifacts=(foreign,),
                evidence_ids=self.evidence_ids,
            ),
        )

        with self.assertRaises(BlueprintBlockedError) as error:
            self.orchestrator.generate(request)
        self.assertIn("belongs to workspace other", str(error.exception))
        self.assertEqual(self.store.history("rave", "rave", "rave-blueprint"), [])

    def test_invalid_output_is_retained_with_validation_findings(self) -> None:
        invalid = BlueprintOrchestrator(
            artifact_catalog=self.catalog,
            prompt_registry=self.prompts,
            engine=FakeBlueprintEngine(
                "# RAVE Blueprint\n\n## Slide 1 — Draft\n\nThis draft never cites evidence.",
                provider_id="router-provider",
                model_id="blueprint-model-v1",
            ),
            store=FileBlueprintStore(self.root / "blueprints-invalid"),
            knowledge_registry=self.knowledge_registry,
        )
        record = invalid.generate(self._request(request_id="blueprint-request-invalid"))

        self.assertEqual(record.status, "invalid")
        self.assertTrue(any(finding.code == "missing_evidence_references" for finding in record.validation_findings))
        self.assertTrue(record.raw_response_artifact.artifact.location)

    def test_claude_only_routing_mismatch_fails_closed(self) -> None:
        fixture_response = self.fixture_response

        class RoutedMismatchProvider:
            def generate(self, package):
                return ProviderResponse(
                    job_id=package.job_id,
                    run_id=package.run_id,
                    stage_id=package.stage_id,
                    output_type=package.expected_output_type,
                    content=fixture_response,
                    metadata={
                        "provider_id": "fallback-provider",
                        "model_id": "fallback-model",
                        "routing": {
                            "provider_id": "fallback-provider",
                            "model_id": "fallback-model",
                            "policy_id": "claude_only",
                            "policy_version": "1",
                        },
                    },
                )

        blocked = BlueprintOrchestrator(
            artifact_catalog=self.catalog,
            prompt_registry=self.prompts,
            engine=ClaudeBlueprintEngine(
                provider=RoutedMismatchProvider(),
                prompt_registry=self.prompts,
            ),
            store=FileBlueprintStore(self.root / "blueprints-mismatch"),
            knowledge_registry=self.knowledge_registry,
        )

        with self.assertRaises(BlueprintRoutingMismatchError):
            blocked.generate(self._request(request_id="blueprint-request-mismatch"))

    def test_runtime_command_api_exposes_blueprint_generation(self) -> None:
        api = RuntimeCommandAPI(self.runtime, blueprint_orchestrator=self.orchestrator)
        response = api.handle(
            {
                "command": "blueprints.generate",
                "request": self._request(request_id="blueprint-request-api").to_dict(),
            }
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["command"], "blueprints.generate")
        self.assertEqual(response["data"]["version"], 1)
        self.assertEqual(response["data"]["structured_blueprint"]["status"], "complete")


if __name__ == "__main__":
    unittest.main()
