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
from runtime.pipeline_runner import (
    DeterministicProvider,
    PipelineRunner,
    load_pipeline_fixture,
)
from runtime.prompt_registry import FilePromptRegistry
from runtime.provider import ArtifactWriter, ProviderExecutor
from runtime.repositories import FileWorkflowRunRepository, JsonlEventLog
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

    catalog = SpecialistCatalog(repository_root, args.workflow)
    deployments = catalog.deploy(FilePromptRegistry(runtime_root / "prompts"))
    output_types = {item.stage_id: item.output_type for item in deployments}
    provider = DeterministicProvider.from_fixture(fixture)
    executor = ProviderExecutor(
        package_builder=ExecutionPackageBuilder(repository_root, output_types),
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
    state = runner.run(run_id, fixture.get("available_inputs", ()))
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


if __name__ == "__main__":
    main()
