from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime.artifact_catalog import ArtifactRecord, FileArtifactCatalog
from runtime.executive_message import ExecutiveMessage
from runtime.github_work import GitHubWorkError, GitHubWorkSnapshot
from runtime.mission_control import MissionControlSnapshot, WorkstreamStatus
from runtime.mission_control_service import MissionControlService
from runtime.repositories import EventLog, WorkflowEvent


class BriefPeriod(str, Enum):
    MORNING = "morning"
    EVENING = "evening"


@dataclass(frozen=True)
class ExecutiveBrief:
    period: BriefPeriod
    generated_at: str
    status: str
    priorities: tuple[str, ...]
    completed: tuple[str, ...]
    open_items: tuple[str, ...]
    blockers: tuple[str, ...]
    approvals: tuple[str, ...]
    executive: ExecutiveMessage
    github_work: GitHubWorkSnapshot | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "period": self.period.value,
            "generated_at": self.generated_at,
            "status": self.status,
            "priorities": list(self.priorities),
            "completed": list(self.completed),
            "open_items": list(self.open_items),
            "blockers": list(self.blockers),
            "approvals": list(self.approvals),
            "executive": self.executive.to_dict(),
            "github_work": (
                self.github_work.to_dict() if self.github_work is not None else None
            ),
        }

    def render_compact(self, limit: int = 3500) -> str:
        heading = "Morning brief" if self.period is BriefPeriod.MORNING else "End-of-day review"
        lines = [f"{heading} — {self.status}", self.executive.render_compact()]

        if self.period is BriefPeriod.MORNING:
            self._append(lines, "Priorities", self.priorities)
        else:
            self._append(lines, "Completed", self.completed)
            self._append(lines, "Still open", self.open_items)

        self._append(lines, "Blockers", self.blockers)
        self._append(lines, "Approvals", self.approvals)
        if self.github_work is not None:
            github = self.github_work
            lines.append(
                "GitHub: "
                f"{len(github.open_pull_requests)} open PR(s), "
                f"{len(github.active_issues)} active issue(s), "
                f"{len(github.blocked)} blocked, "
                f"{len(github.matt_approval_required)} Matt review(s)."
            )
            if github.changes_since_previous_brief:
                self._append(
                    lines,
                    "Changed since previous brief",
                    tuple(
                        f"{change.action}: #{change.item.number} {change.item.title}"
                        for change in github.changes_since_previous_brief
                    ),
                )
            elif github.baseline_status == "unavailable":
                lines.append("Changed since previous brief: baseline unavailable.")
            else:
                lines.append("Changed since previous brief: no material changes.")

        output = "\n".join(lines)
        if len(output) <= limit:
            return output
        return output[: limit - 1].rstrip() + "…"

    @staticmethod
    def _append(lines: list[str], heading: str, values: tuple[str, ...]) -> None:
        if not values:
            return
        lines.append(f"{heading}:")
        lines.extend(f"- {value}" for value in values)


class ExecutiveBriefService:
    """Create compact daily briefs from recorded Mission Control state only."""

    PRIORITY_LIMIT = 3
    ITEM_LIMIT = 5

    def __init__(self, mission_control: MissionControlService | None = None) -> None:
        self._mission_control = mission_control or MissionControlService()

    def build(self, snapshot: MissionControlSnapshot, period: BriefPeriod) -> ExecutiveBrief:
        executive = self._mission_control.respond(snapshot).executive
        ordered = sorted(snapshot.workstreams, key=self._priority_key)

        priorities = tuple(self._work_line(item) for item in ordered[: self.PRIORITY_LIMIT])
        completed = tuple(
            self._completion_line(item)
            for item in snapshot.workstreams
            if item.state in {"tested", "used"}
        )[: self.ITEM_LIMIT]
        open_items = tuple(
            self._work_line(item)
            for item in ordered
            if item.state not in {"tested", "used"}
        )[: self.ITEM_LIMIT]

        return ExecutiveBrief(
            period=period,
            generated_at=snapshot.generated_at,
            status=snapshot.status,
            priorities=priorities if period is BriefPeriod.MORNING else (),
            completed=completed if period is BriefPeriod.EVENING else (),
            open_items=open_items if period is BriefPeriod.EVENING else (),
            blockers=tuple(snapshot.blockers[: self.ITEM_LIMIT]),
            approvals=tuple(snapshot.approvals_required[: self.ITEM_LIMIT]),
            executive=executive,
            github_work=snapshot.github_work,
        )

    @staticmethod
    def _priority_key(item: WorkstreamStatus) -> tuple[int, str]:
        rank = {
            "blocked": 0,
            "functional": 1,
            "known": 2,
            "unknown": 3,
            "tested": 4,
            "used": 5,
        }
        return rank[item.state], item.workstream_id

    @staticmethod
    def _work_line(item: WorkstreamStatus) -> str:
        suffix = f" [blocked: {item.blocker}]" if item.blocker else ""
        return f"{item.title} ({item.owner}) — {item.next_action}{suffix}"

    @staticmethod
    def _completion_line(item: WorkstreamStatus) -> str:
        evidence = f" — {item.evidence[0]}" if item.evidence else ""
        return f"{item.title}: {item.state}{evidence}"


class ExecutiveBriefArchive:
    """Persist executive briefs as immutable artefacts with append-only events."""

    RUN_ID = "tony-executive-briefs"
    STAGE_ID = "executive-brief"
    ARTIFACT_TYPE = "executive_brief"

    def __init__(
        self,
        artifact_catalog: FileArtifactCatalog,
        event_log: EventLog,
        *,
        workspace_id: str,
    ) -> None:
        self.artifact_catalog = artifact_catalog
        self.event_log = event_log
        self.workspace_id = workspace_id

    def latest_github_snapshot(
        self,
        *,
        repository: str,
    ) -> tuple[GitHubWorkSnapshot, str] | None:
        latest = self._latest_persisted()
        if latest is None:
            return None
        payload = self._read_payload(latest)
        github = payload.get("github_work")
        if github is None:
            return None
        if not isinstance(github, dict):
            raise GitHubWorkError("archived executive brief has invalid GitHub data")
        snapshot = GitHubWorkSnapshot.from_dict(github)
        if snapshot.workspace_id != self.workspace_id:
            raise GitHubWorkError(
                "archived GitHub snapshot belongs to a different workspace"
            )
        if snapshot.repository.casefold() != repository.casefold():
            return None
        return snapshot, latest.artifact.artifact_id

    def store(self, brief: ExecutiveBrief) -> ArtifactRecord:
        if brief.github_work is not None:
            if brief.github_work.workspace_id != self.workspace_id:
                raise GitHubWorkError(
                    "executive brief GitHub data belongs to a different workspace"
                )
        content = json.dumps(
            brief.to_dict(), separators=(",", ":"), sort_keys=True
        )
        latest = self._latest_persisted()
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        parents = (
            (latest.artifact.artifact_id,)
            if latest is not None and latest.artifact.checksum != checksum
            else ()
        )
        evidence = (
            [item.evidence for item in brief.github_work.all_open_items]
            if brief.github_work is not None
            else []
        )
        record = self.artifact_catalog.register(
            run_id=self.RUN_ID,
            stage_id=self.STAGE_ID,
            artifact_type=self.ARTIFACT_TYPE,
            content=content,
            parent_artifact_ids=parents,
            producer="Tony",
            extension=".json",
            metadata={
                "period": brief.period.value,
                "generated_at": brief.generated_at,
                "repository": (
                    brief.github_work.repository if brief.github_work else ""
                ),
                "source_evidence": evidence,
            },
        )
        self.event_log.append(
            WorkflowEvent.create(
                event_id=f"evt-{uuid4().hex}",
                run_id=self.RUN_ID,
                event_type="executive_brief.generated",
                payload={
                    "artifact_id": record.artifact.artifact_id,
                    "artifact_version": record.version,
                    "period": brief.period.value,
                    "generated_at": brief.generated_at,
                },
                workspace_id=self.workspace_id,
            )
        )
        return record

    def _latest_persisted(self) -> ArtifactRecord | None:
        history = self.artifact_catalog.history(
            self.RUN_ID, self.STAGE_ID, self.ARTIFACT_TYPE
        )
        persisted = {
            (
                str(event.payload.get("artifact_id", "")),
                int(event.payload.get("artifact_version", 0)),
            )
            for event in self.event_log.read(self.RUN_ID)
            if event.event_type == "executive_brief.generated"
        }
        return next(
            (
                record
                for record in reversed(history)
                if (record.artifact.artifact_id, record.version) in persisted
            ),
            None,
        )

    @staticmethod
    def _read_payload(record: ArtifactRecord) -> dict[str, Any]:
        try:
            raw = Path(record.artifact.location).read_bytes()
        except OSError as exc:
            raise GitHubWorkError(
                f"could not read archived executive brief: {exc}"
            ) from exc
        checksum = hashlib.sha256(raw).hexdigest()
        if checksum != record.artifact.checksum:
            raise GitHubWorkError("archived executive brief checksum mismatch")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubWorkError("archived executive brief is invalid JSON") from exc
        if not isinstance(value, dict):
            raise GitHubWorkError("archived executive brief must be an object")
        return value
