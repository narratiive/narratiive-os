from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .approvals import ApprovalService
from .artifact_catalog import FileArtifactCatalog
from .dispatch import FileDispatchQueue
from .dispatch_service import DispatchService
from .execution_package import ExecutionPackageBuilder
from .http_provider import HttpProviderClient, HttpProviderConfig
from .memory import FileMemoryStore, SpecialistMemorySelector
from .provider import ArtifactWriter, ProviderClient, ProviderExecutor
from .provider_routing import ModelRouter, RouteTarget, RoutedProviderClient
from .prompt_registry import FilePromptRegistry
from .repositories import FileWorkflowRunRepository, JsonlEventLog
from .run_service import WorkflowRunService
from .revision_graph import RevisionService
from .scoring import ConfidenceEngine
from .worker import WorkerRunner
from .workspaces import (
    LEGACY_WORKSPACE_ID,
    FileWorkspaceRepository,
    Workspace,
)


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    root: Path
    repository_root: Path
    workspace_id: str = LEGACY_WORKSPACE_ID
    client_id: str = LEGACY_WORKSPACE_ID

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

    @property
    def memory(self) -> Path:
        return self.root / "memory"

    @property
    def artifact_catalog(self) -> Path:
        return self.root / "artifact-catalog"

    @property
    def prompts(self) -> Path:
        return self.root / "prompts"


@dataclass(slots=True)
class RuntimeComponents:
    paths: RuntimePaths
    run_repository: FileWorkflowRunRepository
    event_log: JsonlEventLog
    dispatch_queue: FileDispatchQueue
    run_service: WorkflowRunService
    dispatch_service: DispatchService
    memory_store: FileMemoryStore
    memory_selector: SpecialistMemorySelector
    artifact_catalog: FileArtifactCatalog
    revision_service: RevisionService
    approval_service: ApprovalService
    workspace: Workspace
    prompt_registry: FilePromptRegistry
    workspace_repository: FileWorkspaceRepository | None = None

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
            memory_selector=self.memory_selector,
            confidence_engine=ConfidenceEngine(),
        )
        executor = ProviderExecutor(
            package_builder=package_builder,
            provider=HttpProviderClient(provider_config),
            artifact_writer=ArtifactWriter(self.paths.artifacts),
            artifact_catalog=self.artifact_catalog,
        )
        return WorkerRunner(
            worker_id=worker_id,
            dispatcher=self.dispatch_service,
            executor=executor,
            lease_seconds=lease_seconds,
        )

    def routed_worker(
        self,
        *,
        worker_id: str,
        router: ModelRouter,
        providers: Mapping[RouteTarget, ProviderClient],
        output_type_by_stage: dict[str, str],
        lease_seconds: int = 300,
    ) -> WorkerRunner:
        package_builder = ExecutionPackageBuilder(
            repository_root=self.paths.repository_root,
            output_type_by_stage=output_type_by_stage,
            memory_selector=self.memory_selector,
            confidence_engine=ConfidenceEngine(),
        )
        executor = ProviderExecutor(
            package_builder=package_builder,
            provider=RoutedProviderClient(router=router, providers=providers),
            artifact_writer=ArtifactWriter(self.paths.artifacts),
            artifact_catalog=self.artifact_catalog,
        )
        return WorkerRunner(
            worker_id=worker_id,
            dispatcher=self.dispatch_service,
            executor=executor,
            lease_seconds=lease_seconds,
        )


def compose_local_runtime(root: str | Path, repository_root: str | Path) -> RuntimeComponents:
    workspace = Workspace(
        LEGACY_WORKSPACE_ID,
        LEGACY_WORKSPACE_ID,
        "Legacy unscoped runtime",
    )
    return _compose_runtime(
        RuntimePaths(
            Path(root).resolve(),
            Path(repository_root).resolve(),
            workspace.workspace_id,
            workspace.client_id,
        ),
        workspace,
    )


def compose_workspace_runtime(
    root: str | Path,
    repository_root: str | Path,
    workspace: Workspace,
    *,
    workspace_repository: FileWorkspaceRepository | None = None,
) -> RuntimeComponents:
    base_root = Path(root).resolve()
    paths = RuntimePaths(
        base_root / "workspaces" / workspace.workspace_id,
        Path(repository_root).resolve(),
        workspace.workspace_id,
        workspace.client_id,
    )
    return _compose_runtime(
        paths,
        workspace,
        workspace_repository=workspace_repository,
    )


def _compose_runtime(
    paths: RuntimePaths,
    workspace: Workspace,
    *,
    workspace_repository: FileWorkspaceRepository | None = None,
) -> RuntimeComponents:
    if not paths.repository_root.exists() or not paths.repository_root.is_dir():
        raise ValueError("repository_root must be an existing directory")
    paths.root.mkdir(parents=True, exist_ok=True)

    run_repository = FileWorkflowRunRepository(
        paths.runs,
        workspace_id=workspace.workspace_id,
        client_id=workspace.client_id,
    )
    event_log = JsonlEventLog(
        paths.events, workspace_id=workspace.workspace_id
    )
    dispatch_queue = FileDispatchQueue(paths.jobs)
    run_service = WorkflowRunService(
        run_repository,
        event_log,
        workspace_id=workspace.workspace_id,
        client_id=workspace.client_id,
    )
    dispatch_service = DispatchService(run_repository, event_log, dispatch_queue, run_service)
    memory_store = FileMemoryStore(
        paths.memory,
        workspace_id=workspace.workspace_id,
        client_id=(
            workspace.client_id
            if workspace.workspace_id != LEGACY_WORKSPACE_ID
            else None
        ),
    )
    artifact_catalog = FileArtifactCatalog(
        paths.artifact_catalog,
        workspace_id=workspace.workspace_id,
    )

    revision_service = RevisionService(
        run_repository,
        event_log,
        artifact_catalog,
    )
    return RuntimeComponents(
        paths=paths,
        run_repository=run_repository,
        event_log=event_log,
        dispatch_queue=dispatch_queue,
        run_service=run_service,
        dispatch_service=dispatch_service,
        memory_store=memory_store,
        memory_selector=SpecialistMemorySelector(memory_store),
        artifact_catalog=artifact_catalog,
        revision_service=revision_service,
        approval_service=ApprovalService(
            run_repository,
            event_log,
            revision_service,
        ),
        workspace=workspace,
        prompt_registry=FilePromptRegistry(
            paths.prompts,
            workspace_id=workspace.workspace_id,
        ),
        workspace_repository=workspace_repository,
    )
