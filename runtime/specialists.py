from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .agent_manifest import AgentManifest, load_agent_manifest
from .definitions import WorkflowDefinition, load_workflow_definition
from .prompt_registry import FilePromptRegistry, PromptVersion


_TEMPLATE_OUTPUTS = {
    "templates/Growth_Blueprint.md": "completed_growth_blueprint",
    "templates/Campaign_World.md": "completed_campaign_world",
    "templates/Creative_Directors_Bible.md": "completed_creative_directors_bible",
}


@dataclass(frozen=True, slots=True)
class SpecialistDeployment:
    stage_id: str
    agent_ref: str
    prompt_id: str
    prompt_version: int
    prompt_checksum: str
    output_type: str


class SpecialistCatalog:
    """Loads, validates and deploys the specialists referenced by a workflow."""

    def __init__(self, repository_root: str | Path, workflow_path: str | Path) -> None:
        self.repository_root = Path(repository_root).resolve()
        raw_workflow_path = Path(workflow_path)
        self.workflow_path = (
            raw_workflow_path.resolve()
            if raw_workflow_path.is_absolute()
            else (self.repository_root / raw_workflow_path).resolve()
        )
        self._require_inside_repository(self.workflow_path)
        self.workflow: WorkflowDefinition = load_workflow_definition(self.workflow_path)

    def manifests(self) -> tuple[AgentManifest, ...]:
        loaded: list[AgentManifest] = []
        for stage in self.workflow.stages:
            path = (self.repository_root / stage.agent_ref).resolve()
            self._require_inside_repository(path)
            if not path.is_file():
                raise FileNotFoundError(f"specialist manifest not found: {stage.agent_ref}")
            manifest = load_agent_manifest(path)
            if manifest.agent_id != stage.stage_id:
                raise ValueError(
                    f"specialist identity mismatch for {stage.stage_id}: {manifest.agent_id}"
                )
            loaded.append(manifest)
        return tuple(loaded)

    def output_type(self, manifest: AgentManifest) -> str:
        declared = manifest.metadata.get("AI_OUTPUT_TYPE", "").strip()
        if declared:
            return declared
        for line in manifest.instructions.splitlines():
            stripped = line.strip()
            if stripped.startswith("output_type:"):
                return stripped.split(":", 1)[1].strip()
            if stripped.startswith("output_template:"):
                template = stripped.split(":", 1)[1].strip()
                mapped = _TEMPLATE_OUTPUTS.get(template)
                if mapped:
                    return mapped
        raise ValueError(f"specialist has no output contract: {manifest.agent_id}")

    def validate_handoffs(self) -> None:
        manifests = self.manifests()
        for index, stage in enumerate(self.workflow.stages):
            output_type = self.output_type(manifests[index])
            if index + 1 < len(self.workflow.stages):
                downstream = self.workflow.stages[index + 1]
                if output_type not in downstream.required_inputs:
                    raise ValueError(
                        f"handoff mismatch: {stage.stage_id} produces {output_type}, "
                        f"but {downstream.stage_id} requires {downstream.required_inputs}"
                    )

    def deploy(self, registry: FilePromptRegistry) -> tuple[SpecialistDeployment, ...]:
        self.validate_handoffs()
        deployments: list[SpecialistDeployment] = []
        for stage, manifest in zip(self.workflow.stages, self.manifests()):
            prompt_id = f"specialist-{manifest.agent_id}"
            checksum = hashlib.sha256(manifest.instructions.encode("utf-8")).hexdigest()
            prompt = self._publish_or_reuse(registry, prompt_id, manifest, checksum)
            registry.activate(prompt_id, prompt.version)
            deployments.append(
                SpecialistDeployment(
                    stage_id=stage.stage_id,
                    agent_ref=stage.agent_ref,
                    prompt_id=prompt_id,
                    prompt_version=prompt.version,
                    prompt_checksum=prompt.checksum,
                    output_type=self.output_type(manifest),
                )
            )
        return tuple(deployments)

    @staticmethod
    def _publish_or_reuse(
        registry: FilePromptRegistry,
        prompt_id: str,
        manifest: AgentManifest,
        checksum: str,
    ) -> PromptVersion:
        history = registry.history(prompt_id)
        if history and history[-1].checksum == checksum:
            return history[-1]
        return registry.publish(
            prompt_id,
            manifest.instructions,
            metadata={
                "agent_id": manifest.agent_id,
                "agent_version": manifest.version,
                "source_path": manifest.source_path,
            },
        )

    def _require_inside_repository(self, path: Path) -> None:
        if path != self.repository_root and self.repository_root not in path.parents:
            raise ValueError("specialist path must remain inside repository_root")


def deployment_manifest(deployments: Iterable[SpecialistDeployment]) -> dict:
    items = list(deployments)
    return {
        "schema_version": 1,
        "specialists": [
            {
                "stage_id": item.stage_id,
                "agent_ref": item.agent_ref,
                "prompt_id": item.prompt_id,
                "prompt_version": item.prompt_version,
                "prompt_checksum": item.prompt_checksum,
                "output_type": item.output_type,
            }
            for item in items
        ],
    }
