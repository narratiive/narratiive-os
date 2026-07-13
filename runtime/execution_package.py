from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .agent_manifest import AgentManifest, load_agent_manifest
from .dispatch import DispatchJob
from .memory import SpecialistMemorySelector
from .models import ArtifactRef
from .scoring import ConfidenceEngine, ScoringInput


@dataclass(frozen=True, slots=True)
class ExecutionPackage:
    schema_version: int
    job_id: str
    run_id: str
    stage_id: str
    agent_id: str
    agent_version: str
    agent_ref: str
    instructions: str
    input_artifacts: tuple[dict[str, Any], ...]
    memory_records: tuple[dict[str, Any], ...]
    confidence_scorecard: dict[str, Any] | None
    context: Mapping[str, Any]
    expected_output_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


class ExecutionPackageBuilder:
    """Builds deterministic provider-neutral packages from dispatch jobs."""

    def __init__(
        self,
        repository_root: str | Path,
        output_type_by_stage: Mapping[str, str],
        memory_selector: SpecialistMemorySelector | None = None,
        confidence_engine: ConfidenceEngine | None = None,
    ) -> None:
        self.repository_root = Path(repository_root)
        self.output_type_by_stage = dict(output_type_by_stage)
        self.memory_selector = memory_selector
        self.confidence_engine = confidence_engine

    def build(
        self,
        job: DispatchJob,
        *,
        input_artifacts: Iterable[ArtifactRef] = (),
        context: Mapping[str, Any] | None = None,
    ) -> ExecutionPackage:
        manifest = self._load_manifest(job.agent_ref)
        output_type = self.output_type_by_stage.get(job.stage_id)
        if not output_type:
            raise ValueError(f"no expected output type configured for stage: {job.stage_id}")
        artifacts = tuple(_artifact_to_dict(item) for item in input_artifacts)
        package_context = dict(context or job.payload or {})
        memory_records: tuple[dict[str, Any], ...] = ()
        if self.memory_selector is not None:
            client_id = str(package_context.get("client_id", "")).strip()
            if client_id:
                memory_records = tuple(
                    record.to_dict()
                    for record in self.memory_selector.select(
                        client_id=client_id,
                        run_id=job.run_id,
                        stage_id=job.stage_id,
                    )
                )
        confidence_scorecard = None
        raw_scoring_input = package_context.get("scoring_input")
        if (
            self.confidence_engine is not None
            and job.stage_id == "quality_reviewer"
            and isinstance(raw_scoring_input, Mapping)
        ):
            confidence_scorecard = self.confidence_engine.score(
                ScoringInput.from_dict(raw_scoring_input)
            ).to_dict()
        return ExecutionPackage(
            schema_version=1,
            job_id=job.job_id,
            run_id=job.run_id,
            stage_id=job.stage_id,
            agent_id=manifest.agent_id,
            agent_version=manifest.version,
            agent_ref=job.agent_ref,
            instructions=manifest.instructions,
            input_artifacts=artifacts,
            memory_records=memory_records,
            confidence_scorecard=confidence_scorecard,
            context=package_context,
            expected_output_type=output_type,
        )

    def _load_manifest(self, agent_ref: str) -> AgentManifest:
        path = (self.repository_root / agent_ref).resolve()
        root = self.repository_root.resolve()
        if root != path and root not in path.parents:
            raise ValueError("agent_ref must resolve inside repository_root")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"agent manifest not found: {agent_ref}")
        return load_agent_manifest(path)


def _artifact_to_dict(artifact: ArtifactRef) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "artifact_type": artifact.artifact_type,
        "location": artifact.location,
        "checksum": artifact.checksum,
        "metadata": dict(artifact.metadata),
    }
