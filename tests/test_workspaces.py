import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from runtime.command_api import CommandError, WorkspaceCommandAPI
from runtime.blueprint_orchestrator import BlueprintOrchestrator, FakeBlueprintEngine
from runtime.blueprint_knowledge_registry import BlueprintKnowledgeRegistry
from runtime.composition import compose_local_runtime
from runtime.definitions import load_workflow_definition
from runtime.execution_package import ExecutionPackageBuilder
from runtime.memory import MemoryKind, MemoryRecord, MemoryScope
from runtime.pipeline_runner import DeterministicProvider, PipelineRunner
from runtime.provider import ArtifactWriter, ProviderExecutor
from runtime.repositories import WorkflowEvent
from runtime.specialists import SpecialistCatalog
from runtime.workspaces import WorkspaceRuntimeManager


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / "workflows/growth_blueprint_pipeline.json"
FIXTURE_PATH = REPOSITORY_ROOT / "tests/fixtures/rave_pipeline.json"
WORKSPACES = (
    ("rave", "rave", "RAVE"),
    ("maeving", "maeving", "Maeving"),
    ("narratiive", "narratiive", "Narratiive"),
)


class MultiClientWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime_root = self.root / "runtime"
        self.manager = WorkspaceRuntimeManager(
            self.runtime_root,
            REPOSITORY_ROOT,
        )
        for workspace_id, client_id, display_name in WORKSPACES:
            self.manager.create(workspace_id, client_id, display_name)
        self.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run_fixture(self, workspace_id: str):
        runtime = self.manager.runtime(workspace_id)
        client_id = runtime.workspace.client_id
        runtime.memory_store.append(
            MemoryRecord(
                memory_id=f"{workspace_id}-context",
                workspace_id=workspace_id,
                client_id=client_id,
                kind=MemoryKind.CONTEXT,
                scope=MemoryScope.CLIENT,
                content=f"Private context for {workspace_id}",
            )
        )
        catalog = SpecialistCatalog(REPOSITORY_ROOT, WORKFLOW_PATH)
        deployments = catalog.deploy(runtime.prompt_registry)
        output_types = {
            deployment.stage_id: deployment.output_type
            for deployment in deployments
        }
        provider = DeterministicProvider.from_fixture(self.fixture)
        runner = PipelineRunner(
            definition=load_workflow_definition(WORKFLOW_PATH),
            runs=runtime.run_repository,
            event_log=runtime.event_log,
            queue=runtime.dispatch_queue,
            executor=ProviderExecutor(
                package_builder=ExecutionPackageBuilder(
                    REPOSITORY_ROOT,
                    output_types,
                    memory_selector=runtime.memory_selector,
                ),
                provider=provider,
                artifact_writer=ArtifactWriter(runtime.paths.artifacts),
                artifact_catalog=runtime.artifact_catalog,
            ),
            workspace_id=workspace_id,
            client_id=client_id,
        )
        state = runner.run(
            "shared-run",
            self.fixture["available_inputs"],
            client_id=client_id,
        )
        return state, provider.calls

    def test_rave_maeving_and_narratiive_run_concurrently_in_isolation(self):
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                workspace_id: executor.submit(self._run_fixture, workspace_id)
                for workspace_id, _, _ in WORKSPACES
            }
            results = {
                workspace_id: future.result()
                for workspace_id, future in futures.items()
            }

        for workspace_id, client_id, _ in WORKSPACES:
            state, calls = results[workspace_id]
            runtime = self.manager.runtime(workspace_id)
            self.assertEqual(state.workspace_id, workspace_id)
            self.assertEqual(state.client_id, client_id)
            self.assertEqual(len(calls), 5)
            self.assertEqual(
                [item.memory_id for item in runtime.memory_store.read(client_id)],
                [f"{workspace_id}-context"],
            )
            self.assertTrue(
                all(
                    event.workspace_id == workspace_id
                    for event in runtime.event_log.read("shared-run")
                )
            )
            records = runtime.artifact_catalog.list_all()
            self.assertEqual(len(records), 5)
            self.assertTrue(
                all(record.workspace_id == workspace_id for record in records)
            )
            self.assertTrue(
                all(
                    record.artifact.metadata["workspace_id"] == workspace_id
                    for record in records
                )
            )
            approvals = runtime.approval_service.queue()
            self.assertEqual(len(approvals), 1)
            self.assertEqual(approvals[0].workspace_id, workspace_id)
            prompts = runtime.prompt_registry.history(
                "specialist-research_analyst"
            )
            self.assertTrue(prompts)
            self.assertTrue(
                all(prompt.workspace_id == workspace_id for prompt in prompts)
            )

        for workspace_id, client_id, _ in WORKSPACES:
            runtime = self.manager.runtime(workspace_id)
            foreign_clients = {
                other_client
                for _, other_client, _ in WORKSPACES
                if other_client != client_id
            }
            for foreign_client in foreign_clients:
                with self.assertRaises(ValueError):
                    runtime.memory_store.read(foreign_client, "shared-run")

    def test_cross_workspace_artifact_and_repository_references_are_rejected(self):
        rave = self.manager.runtime("rave")
        maeving = self.manager.runtime("maeving")
        foreign = rave.artifact_catalog.register(
            run_id="rave-run",
            stage_id="research",
            artifact_type="research",
            content="RAVE-only evidence",
        )

        with self.assertRaisesRegex(ValueError, "not found in workspace maeving"):
            maeving.artifact_catalog.register(
                run_id="maeving-run",
                stage_id="strategy",
                artifact_type="strategy",
                content="Maeving strategy",
                parent_artifact_ids=(foreign.artifact.artifact_id,),
            )

        state = load_workflow_definition(WORKFLOW_PATH).new_state(
            "foreign-run",
            workspace_id="rave",
            client_id="rave",
        )
        with self.assertRaisesRegex(ValueError, "different workspace"):
            maeving.run_repository.save(state)
        with self.assertRaisesRegex(ValueError, "different workspace"):
            maeving.event_log.append(
                WorkflowEvent.create(
                    event_id="foreign-event",
                    run_id="foreign-run",
                    event_type="test.foreign",
                    workspace_id="rave",
                )
            )

    def test_workspace_command_api_scopes_runs_and_rejects_foreign_context(self):
        legacy = compose_local_runtime(self.runtime_root, REPOSITORY_ROOT)
        api = WorkspaceCommandAPI(legacy, self.manager)
        api.handle(
            {
                "command": "runs.create",
                "workspace_id": "rave",
                "run_id": "rave-only-run",
                "definition_path": "workflows/growth_blueprint_pipeline.json",
                "available_inputs": ["client_inputs", "source_material"],
            }
        )

        listed = api.handle(
            {"command": "runs.list", "workspace_id": "rave"}
        )
        self.assertEqual(listed["workspace_id"], "rave")
        self.assertEqual(listed["data"]["run_ids"], ["rave-only-run"])
        self.assertEqual(
            api.handle({"command": "workspaces.list"})["data"]["count"],
            3,
        )

        with self.assertRaises(CommandError) as foreign_run:
            api.handle(
                {
                    "command": "runs.get",
                    "workspace_id": "maeving",
                    "run_id": "rave-only-run",
                }
            )
        self.assertEqual(
            foreign_run.exception.code,
            "cross_workspace_reference",
        )

        with self.assertRaises(CommandError) as foreign_client:
            api.handle(
                {
                    "command": "runs.list",
                    "workspace_id": "rave",
                    "client_id": "maeving",
                }
            )
        self.assertEqual(
            foreign_client.exception.code,
            "cross_workspace_reference",
        )

    def test_workspace_blueprint_requests_reject_cross_workspace_nested_payload(self):
        legacy = compose_local_runtime(self.runtime_root, REPOSITORY_ROOT)
        orchestrator = BlueprintOrchestrator(
            artifact_catalog=legacy.artifact_catalog,
            prompt_registry=legacy.prompt_registry,
            engine=FakeBlueprintEngine(
                "# RAVE Blueprint\n\n## Slide 1 — Draft\n\nThis draft never cites evidence.",
                provider_id="router-provider",
                model_id="blueprint-model-v1",
            ),
            knowledge_registry=BlueprintKnowledgeRegistry.from_default(),
        )
        api = WorkspaceCommandAPI(legacy, self.manager, blueprint_orchestrator=orchestrator)

        with self.assertRaises(CommandError) as error:
            api.handle(
                {
                    "command": "blueprints.generate",
                    "workspace_id": "rave",
                    "request": {
                        "workspace_id": "maeving",
                        "client_id": "maeving",
                    },
                }
            )
        self.assertEqual(error.exception.code, "cross_workspace_reference")

    def test_legacy_unscoped_data_migrates_without_deleting_source(self):
        legacy = compose_local_runtime(self.runtime_root, REPOSITORY_ROOT)
        definition = load_workflow_definition(WORKFLOW_PATH)
        legacy.run_service.create_run(
            definition,
            "legacy-run",
            {"client_inputs", "source_material"},
        )
        legacy.memory_store.append(
            MemoryRecord(
                memory_id="legacy-context",
                client_id="rave-legacy",
                kind=MemoryKind.CONTEXT,
                scope=MemoryScope.CLIENT,
                content="Legacy client context",
            )
        )
        legacy.prompt_registry.publish("legacy-prompt", "Legacy prompt")
        legacy.artifact_catalog.register(
            run_id="legacy-run",
            stage_id="research",
            artifact_type="research",
            content="Legacy artifact",
        )

        self.manager.migrate_legacy(
            workspace_id="rave-legacy",
            client_id="rave-legacy",
            display_name="RAVE legacy migration",
        )
        migrated = self.manager.runtime("rave-legacy")

        self.assertTrue(legacy.run_repository.exists("legacy-run"))
        self.assertEqual(
            migrated.run_repository.load("legacy-run").workspace_id,
            "rave-legacy",
        )
        self.assertTrue(
            all(
                event.workspace_id == "rave-legacy"
                for event in migrated.event_log.read("legacy-run")
            )
        )
        self.assertEqual(
            migrated.memory_store.read("rave-legacy")[0].workspace_id,
            "rave-legacy",
        )
        self.assertEqual(
            migrated.prompt_registry.get("legacy-prompt", 1).workspace_id,
            "rave-legacy",
        )
        self.assertEqual(
            migrated.artifact_catalog.list_all()[0].workspace_id,
            "rave-legacy",
        )


if __name__ == "__main__":
    unittest.main()
