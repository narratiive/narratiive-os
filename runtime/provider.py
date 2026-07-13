from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .dispatch import DispatchJob
from .execution_package import ExecutionPackage, ExecutionPackageBuilder
from .models import ArtifactRef
from .worker import ExecutionResult


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    job_id: str
    run_id: str
    stage_id: str
    output_type: str
    content: str
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in ("job_id", "run_id", "stage_id", "output_type", "content"):
            value = getattr(self, field_name)
            if not str(value).strip():
                raise ValueError(f"{field_name} must not be empty")


class ProviderClient(Protocol):
    def generate(self, package: ExecutionPackage) -> ProviderResponse: ...


class InvalidProviderResponse(ValueError):
    pass


class ArtifactWriter:
    """Writes provider outputs atomically and returns content-addressed references."""

    def __init__(self, root: str | Path, extension_by_type: Mapping[str, str] | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.extension_by_type = dict(extension_by_type or {})

    def write(self, response: ProviderResponse) -> ArtifactRef:
        run_dir = self.root / _safe_identifier(response.run_id, "run_id")
        run_dir.mkdir(parents=True, exist_ok=True)
        stage_id = _safe_identifier(response.stage_id, "stage_id")
        extension = self.extension_by_type.get(response.output_type, ".md")
        if not extension.startswith(".") or "/" in extension or "\\" in extension:
            raise ValueError("artifact extension must be a safe file extension")
        target = run_dir / f"{stage_id}{extension}"
        data = response.content.encode("utf-8")
        checksum = hashlib.sha256(data).hexdigest()
        fd, temporary = tempfile.mkstemp(prefix=f".{stage_id}.", suffix=".tmp", dir=run_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return ArtifactRef(
            artifact_id=f"{response.run_id}--{response.stage_id}--{checksum[:12]}",
            artifact_type=response.output_type,
            location=str(target),
            checksum=checksum,
            metadata=dict(response.metadata or {}),
        )


class ProviderExecutor:
    """AgentExecutor adapter that validates provider output before committing artifacts."""

    def __init__(
        self,
        *,
        package_builder: ExecutionPackageBuilder,
        provider: ProviderClient,
        artifact_writer: ArtifactWriter,
    ) -> None:
        self.package_builder = package_builder
        self.provider = provider
        self.artifact_writer = artifact_writer

    def execute(self, job: DispatchJob) -> ExecutionResult:
        input_artifacts = tuple(
            ArtifactRef(**item) for item in job.payload.get("input_artifacts", ())
        )
        package = self.package_builder.build(job, input_artifacts=input_artifacts)
        response = self.provider.generate(package)
        self._validate(package, response)
        artifact = self.artifact_writer.write(response)
        return ExecutionResult(
            outputs=(artifact,),
            next_available_inputs=(response.output_type,),
            metadata={
                "provider_metadata": dict(response.metadata or {}),
                "artifact_checksum": artifact.checksum,
            },
        )

    @staticmethod
    def _validate(package: ExecutionPackage, response: ProviderResponse) -> None:
        mismatches: list[str] = []
        for field_name in ("job_id", "run_id", "stage_id"):
            if getattr(response, field_name) != getattr(package, field_name):
                mismatches.append(field_name)
        if response.output_type != package.expected_output_type:
            mismatches.append("output_type")
        if mismatches:
            raise InvalidProviderResponse(
                "provider response does not match execution package: " + ", ".join(mismatches)
            )


def provider_response_from_dict(data: Mapping[str, Any]) -> ProviderResponse:
    try:
        return ProviderResponse(
            job_id=str(data["job_id"]),
            run_id=str(data["run_id"]),
            stage_id=str(data["stage_id"]),
            output_type=str(data["output_type"]),
            content=str(data["content"]),
            metadata=dict(data.get("metadata") or {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidProviderResponse("invalid provider response payload") from exc


def provider_response_from_json(payload: str) -> ProviderResponse:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InvalidProviderResponse("provider response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise InvalidProviderResponse("provider response must be a JSON object")
    return provider_response_from_dict(data)


def _safe_identifier(value: str, field_name: str) -> str:
    safe = value.strip()
    if not safe or safe in {".", ".."} or Path(safe).name != safe or "/" in safe or "\\" in safe:
        raise ValueError(f"{field_name} must be a safe filename identifier")
    return safe
