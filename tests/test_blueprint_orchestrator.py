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
from runtime.command_api import RuntimeCommandAPI
from runtime.composition import compose_workspace_runtime
from runtime.provider import ProviderResponse
from runtime.workspaces import Workspace


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
        self.fixture_response = FIXTURE_PATH.read_text(encoding="utf-8")
        self.engine = FakeBlueprintEngine(
            self.fixture_response,
            provider_id="router-provider",
            model_id="blueprint-model-v1",
        )
        self.orchestrator = BlueprintOrchestrator(
            artifact_catalog=self.catalog,
            prompt_registry=self.prompts,
            engine=self.engine,
            store=self.store,
            prompt_source_path=REPO_ROOT / "agents" / "strategy_director.md",
            supporting_instruction_source_paths=(
                REPO_ROOT / "workflows" / "growth_blueprint_pipeline.md",
            ),
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

    def test_generates_and_versions_a_blueprint_without_flattening_the_raw_response(self) -> None:
        record = self.orchestrator.generate(self._request(request_id="blueprint-request-001"))

        self.assertEqual(record.version, 1)
        self.assertEqual(record.status, "complete")
        self.assertEqual(record.prompt_version, 1)
        self.assertEqual(record.provider_id, "router-provider")
        self.assertEqual(record.model_id, "blueprint-model-v1")
        self.assertEqual(record.requested_provider_id, "router-provider")
        self.assertEqual(record.requested_model_id, "blueprint-model-v1")
        self.assertEqual(record.routing_policy_id, "static")
        self.assertEqual(record.routing_policy_version, "1")
        self.assertEqual(record.structured_blueprint.document_title, "RAVE Blueprint")
        self.assertTrue(record.raw_response_artifact.artifact.location.endswith(".md"))
        self.assertEqual(
            Path(record.raw_response_artifact.artifact.location).read_text(encoding="utf-8"),
            self.fixture_response,
        )
        self.assertGreater(len(record.structured_blueprint.sections), 0)
        self.assertEqual(
            [section.heading for section in record.structured_blueprint.sections],
            [
                "Act I — Thesis and Commercial Question",
                "Act II — Market, Category and Competition",
                "Act III — Audience and Demand Pools",
                "Act IV — Strategic Platform",
                "Act V — Campaign and Activation",
            ],
        )
        slides = self._flatten_slide_headings(record.structured_blueprint.sections)
        self.assertEqual(len(slides), 30)
        self.assertGreaterEqual(
            sum(
                1
                for act in record.structured_blueprint.sections
                for slide in act.children
                if any(child.heading == "Founder Insight" for child in slide.children)
            ),
            10,
        )
        self.assertGreaterEqual(
            sum(
                1
                for act in record.structured_blueprint.sections
                for slide in act.children
                if any(child.heading == "So What" for child in slide.children)
            ),
            10,
        )
        self.assertTrue(
            any(
                child.heading == "Visual / Layout Direction"
                for act in record.structured_blueprint.sections
                for slide in act.children
                for child in slide.children
            )
        )
        self.assertTrue(
            any(
                child.heading == "Source Notes"
                for act in record.structured_blueprint.sections
                for slide in act.children
                for child in slide.children
            )
        )
        self.assertIn("ev_deadbeef", record.structured_blueprint.evidence_ids)
        self.assertEqual(record.change_summary, ())
        self.assertTrue(record.artifact_lineage)
        prompt = self.prompts.active("claude-growth-blueprint")
        strategy_director_text = (REPO_ROOT / "agents" / "strategy_director.md").read_text(encoding="utf-8")
        pipeline_text = (REPO_ROOT / "workflows" / "growth_blueprint_pipeline.md").read_text(encoding="utf-8")
        self.assertEqual(
            prompt.metadata["source_path"],
            str(REPO_ROOT / "agents" / "strategy_director.md"),
        )
        self.assertEqual(
            prompt.content,
            strategy_director_text,
        )
        self.assertEqual(
            prompt.checksum,
            hashlib.sha256(strategy_director_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            prompt.metadata["output_template_path"],
            str(REPO_ROOT / "templates" / "Growth_Blueprint.md"),
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][0]["source_path"],
            str(REPO_ROOT / "workflows" / "growth_blueprint_pipeline.md"),
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"][0]["source_checksum"],
            hashlib.sha256(pipeline_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            prompt.metadata["supporting_instruction_sources"],
            [
                {
                    "source_path": str(REPO_ROOT / "workflows" / "growth_blueprint_pipeline.md"),
                    "source_checksum": hashlib.sha256(pipeline_text.encode("utf-8")).hexdigest(),
                }
            ],
        )
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
            prompt_source_path=REPO_ROOT / "agents" / "strategy_director.md",
            supporting_instruction_source_paths=(
                REPO_ROOT / "workflows" / "growth_blueprint_pipeline.md",
            ),
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
                prompt_source_path=REPO_ROOT / "agents" / "strategy_director.md",
            ),
            store=FileBlueprintStore(self.root / "blueprints-mismatch"),
            prompt_source_path=REPO_ROOT / "agents" / "strategy_director.md",
            supporting_instruction_source_paths=(
                REPO_ROOT / "workflows" / "growth_blueprint_pipeline.md",
            ),
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
