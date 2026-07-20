from __future__ import annotations

import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from runtime import (
    BlueprintContextArtifacts,
    BlueprintKnowledgeRegistry,
    BlueprintOrchestrator,
    BlueprintRequest,
    BlueprintVisualMapper,
    FakeBlueprintEngine,
    FileBlueprintStore,
    RenderValidationFinding,
    StructuredBlueprint,
    VisualFrameworkRegistry,
)
from runtime.composition import compose_workspace_runtime
from runtime.workspaces import Workspace
from tests.blueprint_response_factory import render_canonical_blueprint_markdown


REPO_ROOT = Path(__file__).resolve().parents[1]


class BlueprintVisualMapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = Workspace("rave", "rave", "RAVE Coffee")
        self.runtime = compose_workspace_runtime(self.root / "state", REPO_ROOT, self.workspace)
        self.knowledge_registry = BlueprintKnowledgeRegistry.from_default()
        self.schema = self.knowledge_registry.schema()
        self.raw_response = render_canonical_blueprint_markdown(self.schema)
        self.orchestrator = BlueprintOrchestrator(
            artifact_catalog=self.runtime.artifact_catalog,
            prompt_registry=self.runtime.prompt_registry,
            engine=FakeBlueprintEngine(
                self.raw_response,
                provider_id="router-provider",
                model_id="blueprint-model-v1",
            ),
            knowledge_registry=self.knowledge_registry,
            store=FileBlueprintStore(self.root / "blueprints"),
        )
        self.research = self.runtime.artifact_catalog.register(
            run_id="rave-run",
            stage_id="research_analyst",
            artifact_type="completed_research",
            content="Approved research packet for RAVE.",
            producer="research_analyst@1",
        )
        self.strategy = self.runtime.artifact_catalog.register(
            run_id="rave-run",
            stage_id="strategy_director",
            artifact_type="completed_growth_blueprint",
            content="Approved growth blueprint for RAVE.",
            parent_artifact_ids=(self.research.artifact.artifact_id,),
            producer="strategy_director@1",
        )
        self.campaign = self.runtime.artifact_catalog.register(
            run_id="rave-run",
            stage_id="campaign_world_generator",
            artifact_type="completed_campaign_world",
            content="Approved campaign world for RAVE.",
            parent_artifact_ids=(self.strategy.artifact.artifact_id,),
            producer="campaign_world_generator@1",
        )
        self.creative = self.runtime.artifact_catalog.register(
            run_id="rave-run",
            stage_id="creative_director",
            artifact_type="completed_creative_directors_bible",
            content="Approved creative bible for RAVE.",
            parent_artifact_ids=(self.campaign.artifact.artifact_id,),
            producer="creative_director@1",
        )
        self.quality = self.runtime.artifact_catalog.register(
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

    def _request(self, request_id: str = "blueprint-request-001") -> BlueprintRequest:
        return BlueprintRequest(
            request_id=request_id,
            workspace_id="rave",
            client_id="rave",
            blueprint_id="rave-blueprint",
            approved=True,
            approved_context=BlueprintContextArtifacts(
                research_artifacts=(self.research,),
                strategy_artifacts=(self.strategy,),
                campaign_artifacts=(self.campaign,),
                creative_artifacts=(self.creative,),
                quality_artifacts=(self.quality,),
                evidence_ids=self.evidence_ids,
            ),
            requested_by="testing",
        )

    def _generate_record(self, *, request_id: str = "blueprint-request-001"):
        return self.orchestrator.generate(self._request(request_id))

    def test_registry_builds_from_the_canonical_blueprint_assets(self) -> None:
        registry = VisualFrameworkRegistry.from_knowledge_registry(self.knowledge_registry)

        self.assertEqual(set(registry.layout_specs), {"A", "B", "C", "D", "E", "F"})
        self.assertEqual(
            {
                definition.source_asset_id
                for definition in registry.all_definitions()
            },
            {
                "visual_framework_library_v1",
                "visual_intelligence_system_v1",
                "blueprint_schema_v3",
            },
        )
        self.assertTrue(all(registry.definition(definition.framework_id).framework_id == definition.framework_id for definition in registry.all_definitions()))

    def test_canonical_blueprint_maps_to_renderer_agnostic_renderable_blueprint(self) -> None:
        record = self._generate_record()
        mapper = BlueprintVisualMapper(self.knowledge_registry)

        renderable = mapper.map(record.structured_blueprint)

        self.assertEqual(len(renderable.acts), 6)
        self.assertEqual(len(renderable.slides), 30)
        self.assertEqual(renderable.status, "complete")
        self.assertEqual(renderable.validation_findings, ())
        self.assertEqual(renderable.lineage.canon_bundle.bundle_id, "blueprint-canon-v1")
        self.assertEqual(renderable.lineage.structured_blueprint.prompt_id, "claude-growth-blueprint")
        self.assertEqual(renderable.lineage.structured_blueprint.provider_id, "router-provider")
        self.assertEqual(renderable.lineage.structured_blueprint.model_id, "blueprint-model-v1")
        self.assertEqual(renderable.lineage.structured_blueprint.evidence_pack_ids, self.evidence_ids)
        self.assertEqual(
            Path(renderable.lineage.structured_blueprint.raw_response_artifact.artifact.location).read_text(encoding="utf-8"),
            record.structured_blueprint.raw_response,
        )
        self.assertEqual(renderable.lineage.source_asset_ids, (
            "visual_framework_library_v1",
            "visual_intelligence_system_v1",
            "blueprint_schema_v3",
        ))
        self.assertTrue(all(slide.selected_framework_id == self.schema.slides[index].visual_type for index, slide in enumerate(renderable.slides)))
        self.assertTrue(all(slide.selected_layout_type == self.schema.slides[index].layout_type for index, slide in enumerate(renderable.slides)))
        self.assertTrue(all(slide.framework_selection.framework_id == slide.selected_framework_id for slide in renderable.slides))
        self.assertTrue(
            all(
                mapper.framework_registry.definition(slide.selected_framework_id).source_asset_id
                in {"visual_framework_library_v1", "visual_intelligence_system_v1", "blueprint_schema_v3"}
                for slide in renderable.slides
            )
        )

    def test_unknown_extensions_and_block_content_are_preserved(self) -> None:
        record = self._generate_record()
        payload = record.structured_blueprint.to_dict()
        slide_payload = payload["acts"][2]["slides"][1]
        slide_payload.setdefault("extensions", {})["custom_appendix"] = {
            "body": "Preserve this exact text without alteration.",
            "nested": {"keep": True},
        }
        slide_payload["content"].setdefault("extensions", {})["custom_source_context"] = {
            "body": ["Line one", "Line two"],
            "source": "manual",
        }
        mutated = StructuredBlueprint.from_dict(payload)
        mapper = BlueprintVisualMapper(self.knowledge_registry)

        renderable = mapper.map(mutated)
        slide = renderable.slides[11]

        self.assertIn("custom_appendix", slide.extensions)
        self.assertEqual(
            slide.extensions["custom_appendix"]["body"],
            "Preserve this exact text without alteration.",
        )
        self.assertEqual(
            slide.extensions["custom_appendix"]["nested"],
            {"keep": True},
        )
        self.assertTrue(any(block.block_type == "extension:custom_source_context" for block in slide.content_blocks))
        self.assertTrue(any("Line one" in block.text for block in slide.content_blocks))

    def test_render_validation_findings_are_immutable(self) -> None:
        finding = RenderValidationFinding(
            code="copy_density_exceeded",
            severity="warning",
            message="Copy density exceeded.",
            location="slide.12",
        )

        with self.assertRaises(FrozenInstanceError):
            finding.severity = "info"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
