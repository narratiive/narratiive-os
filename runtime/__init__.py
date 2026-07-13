"""Executable runtime primitives for Narratiive OS."""

from .agent_manifest import AgentManifest, load_agent_manifest, parse_agent_manifest
from .composition import RuntimeComponents, RuntimePaths, compose_local_runtime
from .definitions import StageDefinition, WorkflowDefinition, load_workflow_definition
from .dispatch import (
    DispatchJob,
    FileDispatchQueue,
    JobNotFound,
    JobStatus,
    LeaseConflict,
)
from .dispatch_service import DispatchService
from .execution_package import ExecutionPackage, ExecutionPackageBuilder
from .http_provider import HttpProviderClient, HttpProviderConfig, ProviderTransportError
from .models import ArtifactRef, StageRecord, WorkflowState
from .provider import (
    ArtifactWriter,
    InvalidProviderResponse,
    ProviderClient,
    ProviderExecutor,
    ProviderResponse,
    provider_response_from_dict,
    provider_response_from_json,
)
from .repositories import (
    FileWorkflowRunRepository,
    JsonlEventLog,
    RunNotFound,
    WorkflowEvent,
)
from .run_service import WorkflowRunService
from .state_machine import InvalidTransition, WorkflowEngine
from .worker import AgentExecutor, ExecutionResult, JsonArtifactExecutor, WorkerRunner

__all__ = [
    "ArtifactRef",
    "StageRecord",
    "WorkflowState",
    "InvalidTransition",
    "WorkflowEngine",
    "FileWorkflowRunRepository",
    "JsonlEventLog",
    "RunNotFound",
    "WorkflowEvent",
    "StageDefinition",
    "WorkflowDefinition",
    "load_workflow_definition",
    "WorkflowRunService",
    "DispatchJob",
    "FileDispatchQueue",
    "JobNotFound",
    "JobStatus",
    "LeaseConflict",
    "DispatchService",
    "AgentExecutor",
    "ExecutionResult",
    "JsonArtifactExecutor",
    "WorkerRunner",
    "AgentManifest",
    "load_agent_manifest",
    "parse_agent_manifest",
    "ExecutionPackage",
    "ExecutionPackageBuilder",
    "ArtifactWriter",
    "InvalidProviderResponse",
    "ProviderClient",
    "ProviderExecutor",
    "ProviderResponse",
    "provider_response_from_dict",
    "provider_response_from_json",
    "HttpProviderClient",
    "HttpProviderConfig",
    "ProviderTransportError",
    "RuntimeComponents",
    "RuntimePaths",
    "compose_local_runtime",
]
