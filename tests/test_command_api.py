import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from runtime.blueprint_orchestrator import (
    BlueprintContextArtifacts,
    BlueprintOrchestrator,
    BlueprintRequest,
    FakeBlueprintEngine,
    FileBlueprintStore,
)
from runtime.blueprint_knowledge_registry import BlueprintKnowledgeRegistry
from runtime.command_api import CommandError, RuntimeCommandAPI
from runtime.composition import compose_local_runtime
from runtime.wsgi_api import RuntimeWSGIApp
from tests.blueprint_response_factory import render_canonical_blueprint_markdown


REPO_ROOT = Path(__file__).resolve().parents[1]


class CommandAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        (self.repo / "workflow_definitions").mkdir(parents=True)
        (self.repo / "workflow_definitions" / "test.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "workflow_id": "test_pipeline",
                    "stages": [
                        {
                            "stage_id": "research",
                            "agent_ref": "agents/research.md",
                            "required_inputs": ["client_inputs"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.runtime = compose_local_runtime(self.root / "state", self.repo)
        self.api = RuntimeCommandAPI(self.runtime)
        self.blueprint_store = FileBlueprintStore(self.root / "blueprints")
        self.knowledge_registry = BlueprintKnowledgeRegistry.from_default()
        self.blueprint_orchestrator = BlueprintOrchestrator(
            artifact_catalog=self.runtime.artifact_catalog,
            prompt_registry=self.runtime.prompt_registry,
            engine=FakeBlueprintEngine(
                render_canonical_blueprint_markdown(self.knowledge_registry.schema()),
                provider_id="router-provider",
                model_id="blueprint-model-v1",
            ),
            store=self.blueprint_store,
            knowledge_registry=self.knowledge_registry,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_get_list_and_dispatch(self):
        created = self.api.handle(
            {
                "command": "runs.create",
                "run_id": "run-1",
                "definition_path": "workflow_definitions/test.json",
                "available_inputs": ["client_inputs"],
            }
        )
        self.assertTrue(created["ok"])
        self.assertEqual(created["data"]["current_stage_id"], "research")

        listed = self.api.handle({"command": "runs.list"})
        self.assertEqual(listed["data"]["run_ids"], ["run-1"])

        fetched = self.api.handle({"command": "runs.get", "run_id": "run-1"})
        self.assertEqual(fetched["data"]["run_id"], "run-1")

        dispatched = self.api.handle(
            {
                "command": "stages.dispatch",
                "run_id": "run-1",
                "client_id": "rave",
            }
        )
        self.assertEqual(dispatched["data"]["stage_id"], "research")
        self.assertEqual(dispatched["data"]["payload"]["client_id"], "rave")

        job = self.api.handle({"command": "jobs.get", "job_id": dispatched["data"]["job_id"]})
        self.assertEqual(job["data"]["status"], "pending")

    def test_unsafe_definition_path_is_rejected(self):
        with self.assertRaises(CommandError) as error:
            self.api.handle(
                {
                    "command": "runs.create",
                    "run_id": "run-1",
                    "definition_path": "../outside.json",
                    "available_inputs": [],
                }
            )
        self.assertEqual(error.exception.code, "unsafe_path")

    def test_unknown_command_is_not_found(self):
        with self.assertRaises(CommandError) as error:
            self.api.handle({"command": "system.destroy"})
        self.assertEqual(error.exception.status, 404)

    def test_dispatch_rejects_non_object_scoring_input(self):
        with self.assertRaises(CommandError) as error:
            self.api.handle(
                {
                    "command": "stages.dispatch",
                    "run_id": "run-1",
                    "scoring_input": [],
                }
            )
        self.assertEqual(error.exception.code, "invalid_scoring_input")

    def test_wsgi_gateway_returns_structured_response(self):
        app = RuntimeWSGIApp(self.api)
        request = json.dumps({"command": "health"}).encode("utf-8")
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        body = b"".join(
            app(
                {
                    "REQUEST_METHOD": "POST",
                    "PATH_INFO": "/commands",
                    "CONTENT_LENGTH": str(len(request)),
                    "wsgi.input": io.BytesIO(request),
                },
                start_response,
            )
        )
        payload = json.loads(body)
        self.assertEqual(captured["status"], "200 OK")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "ok")

    def test_wsgi_gateway_hides_internal_errors(self):
        app = RuntimeWSGIApp(self.api)
        request = b"not-json"
        captured = {}

        def start_response(status, headers):
            captured["status"] = status

        body = b"".join(
            app(
                {
                    "REQUEST_METHOD": "POST",
                    "PATH_INFO": "/commands",
                    "CONTENT_LENGTH": str(len(request)),
                    "wsgi.input": io.BytesIO(request),
                },
                start_response,
            )
        )
        payload = json.loads(body)
        self.assertEqual(captured["status"], "400 Bad Request")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_json")

    def test_blueprint_generate_command_returns_versioned_structured_output(self):
        api = RuntimeCommandAPI(
            self.runtime,
            blueprint_orchestrator=self.blueprint_orchestrator,
        )
        research = self.runtime.artifact_catalog.register(
            run_id="rave-run",
            stage_id="research_analyst",
            artifact_type="completed_research",
            content="Approved research packet for legacy workspace.",
            producer="research_analyst@1",
        )
        strategy = self.runtime.artifact_catalog.register(
            run_id="rave-run",
            stage_id="strategy_director",
            artifact_type="completed_growth_blueprint",
            content="Approved growth blueprint for legacy workspace.",
            parent_artifact_ids=(research.artifact.artifact_id,),
            producer="strategy_director@1",
        )
        campaign = self.runtime.artifact_catalog.register(
            run_id="rave-run",
            stage_id="campaign_world_generator",
            artifact_type="completed_campaign_world",
            content="Approved campaign world for legacy workspace.",
            parent_artifact_ids=(strategy.artifact.artifact_id,),
            producer="campaign_world_generator@1",
        )
        creative = self.runtime.artifact_catalog.register(
            run_id="rave-run",
            stage_id="creative_director",
            artifact_type="completed_creative_directors_bible",
            content="Approved creative bible for legacy workspace.",
            parent_artifact_ids=(campaign.artifact.artifact_id,),
            producer="creative_director@1",
        )
        quality = self.runtime.artifact_catalog.register(
            run_id="rave-run",
            stage_id="quality_reviewer",
            artifact_type="completed_quality_review",
            content="Approved quality review for legacy workspace.",
            parent_artifact_ids=(creative.artifact.artifact_id,),
            producer="quality_reviewer@1",
        )
        request_payload = BlueprintRequest(
            request_id="legacy-blueprint-request-1",
            workspace_id="legacy",
            client_id="legacy",
            approved=True,
            approved_context=BlueprintContextArtifacts(
                research_artifacts=(research,),
                strategy_artifacts=(strategy,),
                campaign_artifacts=(campaign,),
                creative_artifacts=(creative,),
                quality_artifacts=(quality,),
                evidence_ids=("ev_deadbeef", "ev_cafebabe"),
            ),
        ).to_dict()

        result = api.handle(
            {
                "command": "blueprints.generate",
                "request": request_payload,
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["command"], "blueprints.generate")
        self.assertEqual(result["data"]["status"], "complete")
        self.assertEqual(result["data"]["prompt_version"], 1)
        self.assertEqual(result["data"]["structured_blueprint"]["document_title"], "RAVE Blueprint")
        self.assertEqual(result["data"]["structured_blueprint"]["blueprint_version"], 1)
        self.assertEqual(
            [section["heading"] for section in result["data"]["structured_blueprint"]["sections"]],
            [
                "Act 1 — The Case for Change",
                "Act 2 — Market and Competitive Diagnosis",
                "Act 3 — Audience and Demand Opportunity",
                "Act 4 — Positioning and Narrative Answer",
                "Act 5 — The Growth System",
                "Act 6 — Implementation and Measurement",
            ],
        )
        self.assertEqual(len(result["data"]["structured_blueprint"]["slides"]), 30)
        prompt = self.runtime.prompt_registry.active("claude-growth-blueprint")
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
        self.assertTrue(result["data"]["structured_blueprint"]["slides"][11]["content"]["founder_insight"])


if __name__ == "__main__":
    unittest.main()
