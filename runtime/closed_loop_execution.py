from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Literal

from runtime.delegation_framework import DelegatedAssignment

ExecutionStatus = Literal[
    "assigned",
    "in_progress",
    "completed",
    "blocked",
    "failed",
    "escalated",
]


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    task_id: str
    agent_id: str
    capability: str
    priority_score: int
    status: ExecutionStatus = "assigned"
    attempt: int = 1
    max_attempts: int = 2
    evidence: tuple[str, ...] = ()
    blocker: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        if not self.agent_id.strip():
            raise ValueError("agent_id is required")
        if not self.capability.strip():
            raise ValueError("capability is required")
        if not 0 <= self.priority_score <= 100:
            raise ValueError("priority_score must be between 0 and 100")
        if self.attempt < 1:
            raise ValueError("attempt must be at least 1")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.attempt > self.max_attempts:
            raise ValueError("attempt cannot exceed max_attempts")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("evidence entries must be non-empty")
        if self.status == "completed" and not self.evidence:
            raise ValueError("completed work requires evidence")
        if self.status in {"blocked", "failed", "escalated"} and not (
            self.blocker and self.blocker.strip()
        ):
            raise ValueError(f"{self.status} work requires a blocker")

    @classmethod
    def from_assignment(
        cls,
        assignment: DelegatedAssignment,
        *,
        max_attempts: int = 2,
    ) -> "ExecutionRecord":
        return cls(
            task_id=assignment.task_id,
            agent_id=assignment.agent_id,
            capability=assignment.capability,
            priority_score=assignment.priority_score,
            max_attempts=max_attempts,
        )


class ClosedLoopExecution:
    def __init__(self, records: Iterable[ExecutionRecord] = ()) -> None:
        self._records = {record.task_id: record for record in records}
        if len(self._records) != len(tuple(records)):
            raise ValueError("duplicate task_id")

    def get(self, task_id: str) -> ExecutionRecord:
        if task_id not in self._records:
            raise KeyError(task_id)
        return self._records[task_id]

    def register(
        self,
        assignment: DelegatedAssignment,
        *,
        max_attempts: int = 2,
    ) -> ExecutionRecord:
        if assignment.task_id in self._records:
            raise ValueError("duplicate task_id")
        record = ExecutionRecord.from_assignment(
            assignment,
            max_attempts=max_attempts,
        )
        self._records[record.task_id] = record
        return record

    def start(self, task_id: str) -> ExecutionRecord:
        record = self.get(task_id)
        if record.status != "assigned":
            raise ValueError("only assigned work can start")
        updated = replace(record, status="in_progress")
        self._records[task_id] = updated
        return updated

    def complete(self, task_id: str, *, evidence: Iterable[str]) -> ExecutionRecord:
        record = self.get(task_id)
        if record.status != "in_progress":
            raise ValueError("only in-progress work can complete")
        proof = tuple(item.strip() for item in evidence if item.strip())
        if not proof:
            raise ValueError("completed work requires evidence")
        updated = replace(
            record,
            status="completed",
            evidence=proof,
            blocker=None,
        )
        self._records[task_id] = updated
        return updated

    def block(self, task_id: str, *, blocker: str) -> ExecutionRecord:
        record = self.get(task_id)
        if record.status not in {"assigned", "in_progress"}:
            raise ValueError("only active work can be blocked")
        if not blocker.strip():
            raise ValueError("blocker is required")
        updated = replace(record, status="blocked", blocker=blocker.strip())
        self._records[task_id] = updated
        return updated

    def fail(self, task_id: str, *, blocker: str) -> ExecutionRecord:
        record = self.get(task_id)
        if record.status not in {"assigned", "in_progress"}:
            raise ValueError("only active work can fail")
        if not blocker.strip():
            raise ValueError("blocker is required")
        updated = replace(record, status="failed", blocker=blocker.strip())
        self._records[task_id] = updated
        return updated

    def retry(self, task_id: str) -> ExecutionRecord:
        record = self.get(task_id)
        if record.status not in {"blocked", "failed"}:
            raise ValueError("only blocked or failed work can retry")
        if record.attempt >= record.max_attempts:
            updated = replace(record, status="escalated")
            self._records[task_id] = updated
            return updated
        updated = replace(
            record,
            status="assigned",
            attempt=record.attempt + 1,
            blocker=None,
            evidence=(),
        )
        self._records[task_id] = updated
        return updated

    def unresolved(self) -> tuple[ExecutionRecord, ...]:
        return tuple(
            sorted(
                (
                    record
                    for record in self._records.values()
                    if record.status != "completed"
                ),
                key=lambda record: (-record.priority_score, record.task_id),
            )
        )

    def escalations(self) -> tuple[ExecutionRecord, ...]:
        return tuple(
            sorted(
                (
                    record
                    for record in self._records.values()
                    if record.status == "escalated"
                ),
                key=lambda record: (-record.priority_score, record.task_id),
            )
        )
