from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

from .models import WorkflowStatus
from .repositories import EventLog, WorkflowEvent, WorkflowRunRepository
from .revision_graph import RevisionIssue, RevisionPlan, RevisionService


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ApprovalComment:
    command_id: str
    reviewer_id: str
    comment: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "command_id": self.command_id,
            "reviewer_id": self.reviewer_id,
            "comment": self.comment,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    run_id: str
    stage_id: str
    artifact_ids: tuple[str, ...]
    status: ApprovalStatus
    requested_at: str
    reviewer_id: str | None = None
    decided_at: str | None = None
    rationale: str | None = None
    revision_id: str | None = None
    comments: tuple[ApprovalComment, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "run_id": self.run_id,
            "stage_id": self.stage_id,
            "artifact_ids": list(self.artifact_ids),
            "status": self.status.value,
            "requested_at": self.requested_at,
            "reviewer_id": self.reviewer_id,
            "decided_at": self.decided_at,
            "rationale": self.rationale,
            "revision_id": self.revision_id,
            "comments": [comment.to_dict() for comment in self.comments],
        }


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    record: ApprovalRecord
    revision_plan: RevisionPlan | None = None
    replayed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval": self.record.to_dict(),
            "revision_plan": (
                self.revision_plan.to_dict()
                if self.revision_plan is not None
                else None
            ),
            "replayed": self.replayed,
        }


class ApprovalNotFound(KeyError):
    """Raised when a workflow has no approval request."""


class ApprovalConflict(ValueError):
    """Raised when an approval command violates the audit contract."""


class ApprovalService:
    """Event-sourced approval queue and immutable decision service."""

    _DECISION_EVENTS = {
        "approval.approved": ApprovalStatus.APPROVED,
        "approval.revision_requested": ApprovalStatus.REVISION_REQUESTED,
        "approval.blocked": ApprovalStatus.BLOCKED,
    }

    def __init__(
        self,
        runs: WorkflowRunRepository,
        event_log: EventLog,
        revision_service: RevisionService,
    ) -> None:
        self.runs = runs
        self.event_log = event_log
        self.revision_service = revision_service

    def queue(self) -> tuple[ApprovalRecord, ...]:
        records = []
        for run_id in self.runs.list_run_ids():
            try:
                record = self.current(run_id)
            except ApprovalNotFound:
                continue
            if record.status == ApprovalStatus.PENDING:
                records.append(record)
        return tuple(sorted(records, key=lambda item: item.requested_at))

    def history(self, run_id: str) -> tuple[ApprovalRecord, ...]:
        records: list[ApprovalRecord] = []
        current: dict[str, Any] | None = None
        comments: list[ApprovalComment] = []
        for event in self.event_log.read(run_id):
            if event.event_type == "approval.requested":
                if current is not None:
                    records.append(self._record(current, comments))
                current = {
                    "approval_id": str(event.payload["approval_id"]),
                    "run_id": run_id,
                    "stage_id": str(event.payload["stage_id"]),
                    "artifact_ids": tuple(
                        str(item) for item in event.payload.get("artifact_ids", [])
                    ),
                    "status": ApprovalStatus.PENDING,
                    "requested_at": event.occurred_at,
                    "reviewer_id": None,
                    "decided_at": None,
                    "rationale": None,
                    "revision_id": None,
                }
                comments = []
                continue
            if current is None:
                continue
            if event.payload.get("approval_id") != current["approval_id"]:
                continue
            if event.event_type == "approval.comment_added":
                comments.append(
                    ApprovalComment(
                        command_id=str(event.payload["command_id"]),
                        reviewer_id=str(event.payload["reviewer_id"]),
                        comment=str(event.payload["comment"]),
                        created_at=event.occurred_at,
                    )
                )
            elif event.event_type in self._DECISION_EVENTS:
                current.update(
                    status=self._DECISION_EVENTS[event.event_type],
                    reviewer_id=str(event.payload["reviewer_id"]),
                    decided_at=event.occurred_at,
                    rationale=str(event.payload["rationale"]),
                    revision_id=event.payload.get("revision_id"),
                )
        if current is not None:
            records.append(self._record(current, comments))
        return tuple(records)

    def current(self, run_id: str) -> ApprovalRecord:
        history = self.history(run_id)
        if not history:
            raise ApprovalNotFound(run_id)
        return history[-1]

    def approve(
        self,
        run_id: str,
        command_id: str,
        reviewer_id: str,
        rationale: str,
    ) -> ApprovalResult:
        replay = self._replay(run_id, command_id, "approve")
        if replay is not None:
            return ApprovalResult(self.current(run_id), replayed=True)
        record = self._pending(run_id)
        state = self.runs.load(run_id)
        if state.status != WorkflowStatus.AWAITING_APPROVAL:
            raise ApprovalConflict("workflow is not awaiting approval")
        self._validate_command(command_id, reviewer_id, rationale)
        state.status = WorkflowStatus.COMPLETE
        state.touch()
        self.runs.save(state)
        self._decision_event(
            record,
            "approval.approved",
            command_id,
            reviewer_id,
            rationale,
        )
        return ApprovalResult(self.current(run_id))

    def block(
        self,
        run_id: str,
        command_id: str,
        reviewer_id: str,
        rationale: str,
    ) -> ApprovalResult:
        replay = self._replay(run_id, command_id, "block")
        if replay is not None:
            return ApprovalResult(self.current(run_id), replayed=True)
        record = self._pending(run_id)
        self._validate_command(command_id, reviewer_id, rationale)
        state = self.runs.load(run_id)
        state.status = WorkflowStatus.BLOCKED
        state.touch()
        self.runs.save(state)
        self._decision_event(
            record,
            "approval.blocked",
            command_id,
            reviewer_id,
            rationale,
        )
        return ApprovalResult(self.current(run_id))

    def comment(
        self,
        run_id: str,
        command_id: str,
        reviewer_id: str,
        comment: str,
    ) -> ApprovalResult:
        replay = self._replay(run_id, command_id, "comment")
        if replay is not None:
            return ApprovalResult(self.current(run_id), replayed=True)
        record = self.current(run_id)
        self._validate_command(command_id, reviewer_id, comment)
        self._event(
            run_id,
            "approval.comment_added",
            {
                "approval_id": record.approval_id,
                "command_id": command_id,
                "command": "comment",
                "reviewer_id": reviewer_id,
                "comment": comment,
            },
        )
        return ApprovalResult(self.current(run_id))

    def revise(
        self,
        issue: RevisionIssue,
        command_id: str,
        reviewer_id: str,
        rationale: str,
    ) -> ApprovalResult:
        replay = self._replay(issue.run_id, command_id, "revise")
        if replay is not None:
            return ApprovalResult(self.current(issue.run_id), replayed=True)
        record = self._pending(issue.run_id)
        self._validate_command(command_id, reviewer_id, rationale)
        if issue.source_stage_id != record.stage_id:
            raise ApprovalConflict(
                "revision source_stage_id must match the approval stage"
            )
        plan = self.revision_service.request_revision(issue)
        self._decision_event(
            record,
            "approval.revision_requested",
            command_id,
            reviewer_id,
            rationale,
            revision_id=issue.revision_id,
        )
        return ApprovalResult(self.current(issue.run_id), plan)

    def _pending(self, run_id: str) -> ApprovalRecord:
        record = self.current(run_id)
        if record.status != ApprovalStatus.PENDING:
            raise ApprovalConflict(
                f"approval is already {record.status.value}"
            )
        return record

    def _replay(
        self,
        run_id: str,
        command_id: str,
        command: str,
    ) -> WorkflowEvent | None:
        if not command_id.strip():
            raise ValueError("command_id must not be empty")
        for event in self.event_log.read(run_id):
            if event.payload.get("command_id") != command_id:
                continue
            if event.payload.get("command") != command:
                raise ApprovalConflict(
                    "command_id was already used for a different command"
                )
            return event
        return None

    @staticmethod
    def _validate_command(
        command_id: str,
        reviewer_id: str,
        content: str,
    ) -> None:
        for field_name, value in (
            ("command_id", command_id),
            ("reviewer_id", reviewer_id),
            ("rationale", content),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")

    def _decision_event(
        self,
        record: ApprovalRecord,
        event_type: str,
        command_id: str,
        reviewer_id: str,
        rationale: str,
        *,
        revision_id: str | None = None,
    ) -> None:
        command = event_type.removeprefix("approval.").replace(
            "revision_requested", "revise"
        ).replace("approved", "approve").replace("blocked", "block")
        self._event(
            record.run_id,
            event_type,
            {
                "approval_id": record.approval_id,
                "command_id": command_id,
                "command": command,
                "reviewer_id": reviewer_id,
                "rationale": rationale,
                "revision_id": revision_id,
            },
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
            )
        )

    @staticmethod
    def _record(
        values: dict[str, Any],
        comments: list[ApprovalComment],
    ) -> ApprovalRecord:
        return ApprovalRecord(**values, comments=tuple(comments))
