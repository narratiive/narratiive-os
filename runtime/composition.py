from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dispatch import FileDispatchQueue
from .dispatch_service import DispatchService
from .execution_package import ExecutionPackageBuilder
from .http_provider import HttpProviderClient, HttpProviderConfig
from .provider import ArtifactWriter, ProviderExecutor
from .repositories import FileWorkflowRunRepository, JsonlEventLog
from .run_service import WorkflowRunService
from .worker import WorkerRunner


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    root: Path
    repository_root: Path

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def events(self) -> Path:
        return self.root / "events"

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"


@dataclass(slots=True)
class RuntimeComponents:
    paths: RuntimePaths
    run_repository: FileWorkflowRunRepository
    event_log: JsonlEventLog
    dispatch_queue: FileDispatchQueue
    run_service: WorkflowRunService
    dispatch_service: DispatchService

    def http_worker(
        self,
        *,
        worker_id: str,
        provider_config: HttpProviderConfig,
        output_type_by_stage: dict[str, str],
        lease_seconds: int = 300,
    ) -> WorkerRunner:
        package_builder = ExecutionPackageBuilder(
            repository_root=self.paths.repository_root,
            output_type_by_stage=output_type_by_stage,
        )
        executor = ProviderExecutor(
            package_builder=package_builder,
            provider=HttpProviderClient(provider_config),
            artifact_writer=ArtifactWriter(self.paths.artifacts),
        )
        return WorkerRunner(
            worker_id=worker_id,
            dispatcher=self.dispatch_service,
            executor=executor,
            lease_seconds=lease_seconds,
        )


def compose_local_runtime(root: str | Path, repository_root: str | Path) -> RuntimeComponents:
    paths = RuntimePaths(Path(root).resolve(), Path(repository_root).resolve())
    if not paths.repository_root.exists() or not paths.repository_root.is_dir():
        raise ValueError("repository_root must be an existing directory")
    paths.root.mkdir(parents=True, exist_ok=True)

    run_repository = FileWorkflowRunRepository(paths.runs)
    event_log = JsonlEventLog(paths.events)
    dispatch_queue = FileDispatchQueue(paths.jobs)
    run_service = WorkflowRunService(run_repository, event_log)
    dispatch_service = DispatchService(run_repository, event_log, dispatch_queue, run_service)

    return RuntimeComponents(
        paths=paths,
        run_repository=run_repository,
        event_log=event_log,
        dispatch_queue=dispatch_queue,
        run_service=run_service,
        dispatch_service=dispatch_service,
    )
