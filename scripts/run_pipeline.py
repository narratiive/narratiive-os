from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.definitions import load_workflow_definition
from runtime.dispatch import FileDispatchQueue
from runtime.execution_package import ExecutionPackageBuilder
from runtime.memory import (
    FileMemoryStore,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    SpecialistMemorySelector,
)
from runtime.pipeline_runner import (
    DeterministicProvider,
    PipelineRunner,
    load_pipeline_fixture,
)
from runtime.prompt_registry import FilePromptRegistry
from runtime.provider import ArtifactWriter, ProviderExecutor
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
from runtime.scoring import ConfidenceEngine
from runtime.specialists import SpecialistCatalog


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Growth Blueprint pipeline with a deterministic fixture"
    )
    parser.add_argument("--repository-root", default=".")
    parser.add_argument(
        "--workflow",
        default="workflows/growth_blueprint_pipeline.json",
    )
    parser.add_argument("--fixture", default="tests/fixtures/rave_pipeline.json")
    parser.add_argument("--runtime-root", default=".runtime/pipeline")
    parser.add_argument("--run-id")
    args = parser.parse_args()

    repository_root = Path(args.repository_root).resolve()
    runtime_root = Path(args.runtime_root).resolve()
    fixture_path = (repository_root / args.fixture).resolve()
    fixture = load_pipeline_fixture(fixture_path.read_text(encoding="utf-8"))
    run_id = args.run_id or str(fixture.get("run_id", "")).strip()
    if not run_id:
        raise ValueError("run_id must be supplied by --run-id or the fixture")
    client_id = str(fixture.get("client_id", "")).strip()
    if not client_id:
        raise ValueError("fixture must define client_id")

    catalog = SpecialistCatalog(repository_root, args.workflow)
    deployments = catalog.deploy(FilePromptRegistry(runtime_root / "prompts"))
    output_types = {item.stage_id: item.output_type for item in deployments}
    memory_store = FileMemoryStore(runtime_root / "memory")
    for item in fixture.get("memory_records", ()):
        record = _memory_record(item, client_id=client_id, run_id=run_id)
        if not memory_store.contains(client_id, record.memory_id):
            memory_store.append(record)
    provider = DeterministicProvider.from_fixture(fixture)
    executor = ProviderExecutor(
        package_builder=ExecutionPackageBuilder(
            repository_root,
            output_types,
            memory_selector=SpecialistMemorySelector(memory_store),
            confidence_engine=ConfidenceEngine(),
        ),
        provider=provider,
        artifact_writer=ArtifactWriter(runtime_root / "artifacts"),
    )
    events = JsonlEventLog(runtime_root / "events")
    runner = PipelineRunner(
        definition=load_workflow_definition(repository_root / args.workflow),
        runs=FileWorkflowRunRepository(runtime_root / "runs"),
        event_log=events,
        queue=FileDispatchQueue(runtime_root / "jobs"),
        executor=executor,
    )
    state = runner.run(
        run_id,
        fixture.get("available_inputs", ()),
        client_id=client_id,
        scoring_input=fixture.get("scoring_input"),
    )
    payload = {
        "run_id": state.run_id,
        "workflow_id": state.workflow_id,
        "status": state.status.value,
        "stages": [
            {
                "stage_id": stage.stage_id,
                "status": stage.status.value,
                "output_artifact_ids": [
                    artifact.artifact_id for artifact in stage.output_artifacts
                ],
            }
            for stage in state.stages
        ],
        "event_count": len(events.read(run_id)),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def _memory_record(item, *, client_id: str, run_id: str) -> MemoryRecord:
    if not isinstance(item, dict):
        raise ValueError("memory_records entries must be objects")
    scope = MemoryScope(str(item["scope"]))
    return MemoryRecord(
        memory_id=str(item["memory_id"]).format(
            client_id=client_id,
            run_id=run_id,
        ),
        client_id=client_id,
        run_id=run_id if scope == MemoryScope.RUN else None,
        kind=MemoryKind(str(item["kind"])),
        scope=scope,
        content=str(item["content"]),
        origin_stage_id=(
            str(item["origin_stage_id"])
            if item.get("origin_stage_id") is not None
            else None
        ),
        stage_ids=tuple(str(value) for value in item.get("stage_ids") or ()),
        source_artifact_ids=tuple(
            str(value) for value in item.get("source_artifact_ids") or ()
        ),
        metadata=dict(item.get("metadata") or {}),
    )


if __name__ == "__main__":
    main()
