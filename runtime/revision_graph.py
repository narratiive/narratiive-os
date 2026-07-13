from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

from .artifact_catalog import FileArtifactCatalog
from .models import StageStatus, WorkflowState, WorkflowStatus
from .repositories import EventLog, WorkflowEvent, WorkflowRunRepository


class RevisionSeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    OBSERVATION = "observation"


class RevisionCategory(str, Enum):
    EVIDENCE = "evidence"
    STRATEGY = "strategy"
    CAMPAIGN = "campaign"
    CREATIVE = "creative"
    QUALITY = "quality"


class RevisionOwner(str, Enum):
    RESEARCH_ANALYST = "research_analyst"
    STRATEGY_DIRECTOR = "strategy_director"
    CAMPAIGN_WORLD_GENERATOR = "campaign_world_generator"
    CREATIVE_DIRECTOR = "creative_director"
    QUALITY_REVIEWER = "quality_reviewer"


_CATEGORY_OWNER = {
    RevisionCategory.EVIDENCE: RevisionOwner.RESEARCH_ANALYST,
    RevisionCategory.STRATEGY: RevisionOwner.STRATEGY_DIRECTOR,
    RevisionCategory.CAMPAIGN: RevisionOwner.CAMPAIGN_WORLD_GENERATOR,
    RevisionCategory.CREATIVE: RevisionOwner.CREATIVE_DIRECTOR,
    RevisionCategory.QUALITY: RevisionOwner.QUALITY_REVIEWER,
}


@dataclass(frozen=True, slots=True)
class RevisionIssue:
    revision_id: str
    run_id: str
    source_stage_id: str
    category: RevisionCategory
    severity: RevisionSeverity
    reason: str
    owner: RevisionOwner | None = None
    evidence_requirement: str | None = None
    affected_artifact_ids: tuple[str, ...] = ()
    blocking: bool = False

    def __post_init__(self) -> None:
        for field_name in ("revision_id", "run_id", "source_stage_id", "reason"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.blocking and not (self.evidence_requirement or "").strip():
            raise ValueError(
                "blocking revisions require evidence_requirement"
            )
        object.__setattr__(
            self,
            "affected_artifact_ids",
            tuple(dict.fromkeys(self.affected_artifact_ids)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "run_id": self.run_id,
            "source_stage_id": self.source_stage_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "reason": self.reason,
            "owner": self.owner.value if self.owner is not None else None,
            "evidence_requirement": self.evidence_requirement,
            "affected_artifact_ids": list(self.affected_artifact_ids),
            "blocking": self.blocking,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RevisionIssue":
        blocking = data.get("blocking", False)
        if not isinstance(blocking, bool):
            raise ValueError("blocking must be a boolean")
        raw_owner = data.get("owner")
        return cls(
            revision_id=str(data["revision_id"]),
            run_id=str(data["run_id"]),
            source_stage_id=str(data["source_stage_id"]),
            category=RevisionCategory(str(data["category"])),
            severity=RevisionSeverity(str(data["severity"])),
            reason=str(data["reason"]),
            owner=RevisionOwner(str(raw_owner)) if raw_owner is not None else None,
            evidence_requirement=(
                str(data["evidence_requirement"])
                if data.get("evidence_requirement") is not None
                else None
            ),
            affected_artifact_ids=tuple(
                str(item) for item in data.get("affected_artifact_ids") or ()
            ),
            blocking=blocking,
        )


@dataclass(frozen=True, slots=True)
class RevisionPlan:
    revision_id: str
    owner_stage_id: str
    invalidated_stage_ids: tuple[str, ...]
    blocking: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "owner_stage_id": self.owner_stage_id,
            "invalidated_stage_ids": list(self.invalidated_stage_ids),
            "blocking": self.blocking,
        }


class StageDependencyGraph:
    """Ordered Growth Blueprint graph used for selective invalidation."""

    def __init__(self, stage_ids: tuple[str, ...]) -> None:
        if not stage_ids or len(stage_ids) != len(set(stage_ids)):
            raise ValueError("dependency graph requires unique stages")
        self.stage_ids = stage_ids
        self._positions = {
            stage_id: position for position, stage_id in enumerate(stage_ids)
        }

    def downstream(self, stage_id: str) -> tuple[str, ...]:
        try:
            position = self._positions[stage_id]
        except KeyError as exc:
            raise ValueError(f"unknown dependency stage: {stage_id}") from exc
        return self.stage_ids[position:]

    def earliest(self, stage_ids: tuple[str, ...]) -> str:
        if not stage_ids:
            raise ValueError("at least one stage is required")
        try:
            return min(stage_ids, key=self._positions.__getitem__)
        except KeyError as exc:
            raise ValueError(f"unknown dependency stage: {exc.args[0]}") from exc


class RevisionRouter:
    """Resolves one deterministic owner from explicit, lineage or category signals."""

    def __init__(self, artifact_catalog: FileArtifactCatalog) -> None:
        self.artifact_catalog = artifact_catalog

    def resolve_owner(
        self,
        issue: RevisionIssue,
        state: WorkflowState,
        graph: StageDependencyGraph,
    ) -> str:
        if issue.owner is not None:
            owner = issue.owner.value
            state.stage(owner)
            return owner

        producers: list[str] = []
        for artifact_id in issue.affected_artifact_ids:
            matches = [
                record
                for record in self.artifact_catalog.get(artifact_id)
                if record.run_id == issue.run_id
            ]
            if not matches:
                raise ValueError(
                    f"affected artifact is not in run {issue.run_id}: {artifact_id}"
                )
            producers.extend(record.stage_id for record in matches)
        if producers:
            return graph.earliest(tuple(producers))

        owner = _CATEGORY_OWNER[issue.category].value
        state.stage(owner)
        return owner


class RevisionService:
    """Routes revisions and atomically snapshots selective invalidation state."""

    def __init__(
        self,
        runs: WorkflowRunRepository,
        event_log: EventLog,
        artifact_catalog: FileArtifactCatalog,
    ) -> None:
        self.runs = runs
        self.event_log = event_log
        self.router = RevisionRouter(artifact_catalog)

    def request_revision(self, issue: RevisionIssue) -> RevisionPlan:
        state = self.runs.load(issue.run_id)
        state.stage(issue.source_stage_id)
        graph = StageDependencyGraph(
            tuple(stage.stage_id for stage in state.stages)
        )
        owner_stage_id = self.router.resolve_owner(issue, state, graph)
        invalidated_stage_ids = graph.downstream(owner_stage_id)
        previous_artifacts: dict[str, list[str]] = {}

        for stage_id in invalidated_stage_ids:
            stage = state.stage(stage_id)
            previous_artifacts[stage_id] = [
                artifact.artifact_id for artifact in stage.output_artifacts
            ]
            stage.output_artifacts = []
            stage.failure_reason = issue.reason
            stage.started_at = None
            stage.completed_at = None
            stage.retry_count = 0
            stage.revision_count += 1
            if stage_id == owner_stage_id:
                stage.status = (
                    StageStatus.BLOCKED if issue.blocking else StageStatus.READY
                )
                stage.missing_inputs = (
                    [issue.evidence_requirement]
                    if issue.blocking and issue.evidence_requirement
                    else []
                )
                if issue.blocking and issue.evidence_requirement:
                    stage.required_inputs = tuple(
                        dict.fromkeys(
                            (*stage.required_inputs, issue.evidence_requirement)
                        )
                    )
            else:
                stage.status = StageStatus.NOT_STARTED
                stage.input_artifacts = []
                stage.missing_inputs = []

        state.current_stage_id = owner_stage_id
        state.revision_owner = owner_stage_id
        state.status = (
            WorkflowStatus.BLOCKED if issue.blocking else WorkflowStatus.ACTIVE
        )
        state.touch()
        self.runs.save(state)
        self._event(
            issue.run_id,
            "revision.requested",
            {
                "issue": issue.to_dict(),
                "owner_stage_id": owner_stage_id,
                "invalidated_stage_ids": list(invalidated_stage_ids),
            },
        )
        for stage_id in invalidated_stage_ids:
            self._event(
                issue.run_id,
                "stage.invalidated",
                {
                    "revision_id": issue.revision_id,
                    "stage_id": stage_id,
                    "owner_stage_id": owner_stage_id,
                    "previous_output_artifact_ids": previous_artifacts[stage_id],
                    "blocking": issue.blocking and stage_id == owner_stage_id,
                    "reason": issue.reason,
                },
            )
        return RevisionPlan(
            revision_id=issue.revision_id,
            owner_stage_id=owner_stage_id,
            invalidated_stage_ids=invalidated_stage_ids,
            blocking=issue.blocking,
        )

    def _event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self.event_log.append(
            WorkflowEvent.create(
                event_id=f"evt-{uuid4().hex}",
                run_id=run_id,
                event_type=event_type,
                payload=payload,
                workspace_id=self.runs.load(run_id).workspace_id,
            )
        )
