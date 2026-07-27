from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

from .artifact_catalog import FileArtifactCatalog
from .engineering_task_lock import engineering_task_lock
from .execution_journal import ExecutionJournal, ExecutionJournalError


class EngineeringHandoffError(RuntimeError):
    """Raised when an engineering handoff cannot be trusted or advanced."""


def _required_text(value: Any, field: str, *, limit: int | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        raise EngineeringHandoffError(f"engineering task requires {field}")
    if limit is not None and len(text) > limit:
        raise EngineeringHandoffError(f"engineering task {field} exceeds {limit} characters")
    return text


def _text_list(value: Any, field: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EngineeringHandoffError(f"engineering task {field} must be a string list")
    items = tuple(item.strip() for item in value)
    if any(not item for item in items):
        raise EngineeringHandoffError(f"engineering task {field} contains an empty item")
    if required and not items:
        raise EngineeringHandoffError(f"engineering task requires {field}")
    return items


@dataclass(frozen=True, slots=True)
class EngineeringTask:
    task_id: str
    workspace_id: str
    repository: str
    title: str
    problem: str
    scope: tuple[str, ...]
    non_goals: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    verification: tuple[str, ...]
    implementation_agent: str

    def __post_init__(self) -> None:
        safe = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"
        if not re.fullmatch(safe, self.task_id):
            raise EngineeringHandoffError("engineering task task_id is invalid")
        if not re.fullmatch(safe, self.workspace_id):
            raise EngineeringHandoffError("engineering task workspace_id is invalid")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise EngineeringHandoffError("engineering task repository must use owner/name")
        for field in ("title", "problem", "implementation_agent"):
            if not str(getattr(self, field)).strip():
                raise EngineeringHandoffError(f"engineering task requires {field}")
        if len(self.title) > 256:
            raise EngineeringHandoffError("engineering task title exceeds 256 characters")
        if len(self.implementation_agent) > 100:
            raise EngineeringHandoffError(
                "engineering task implementation_agent exceeds 100 characters"
            )
        for field in ("scope", "acceptance_criteria", "verification"):
            if not getattr(self, field):
                raise EngineeringHandoffError(f"engineering task requires {field}")
        for field in ("scope", "non_goals", "acceptance_criteria", "verification"):
            if any(not item.strip() for item in getattr(self, field)):
                raise EngineeringHandoffError(
                    f"engineering task {field} contains an empty item"
                )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EngineeringTask":
        allowed = {
            "task_id",
            "workspace_id",
            "repository",
            "title",
            "problem",
            "scope",
            "non_goals",
            "acceptance_criteria",
            "verification",
            "implementation_agent",
        }
        unexpected = sorted(set(value) - allowed)
        if unexpected:
            raise EngineeringHandoffError(
                f"engineering task contains unsupported fields: {', '.join(unexpected)}"
            )
        return cls(
            task_id=_required_text(value.get("task_id"), "task_id", limit=100),
            workspace_id=_required_text(
                value.get("workspace_id"), "workspace_id", limit=100
            ),
            repository=_required_text(value.get("repository"), "repository"),
            title=_required_text(value.get("title"), "title", limit=256),
            problem=_required_text(value.get("problem"), "problem"),
            scope=_text_list(value.get("scope"), "scope", required=True),
            non_goals=_text_list(value.get("non_goals"), "non_goals"),
            acceptance_criteria=_text_list(
                value.get("acceptance_criteria"),
                "acceptance_criteria",
                required=True,
            ),
            verification=_text_list(
                value.get("verification"), "verification", required=True
            ),
            implementation_agent=_required_text(
                value.get("implementation_agent"),
                "implementation_agent",
                limit=100,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in ("scope", "non_goals", "acceptance_criteria", "verification"):
            value[field] = list(value[field])
        return value

    @property
    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), sort_keys=True)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()

    @property
    def marker(self) -> str:
        return (
            "<!-- tony-engineering-task:v1 "
            f"task_id={self.task_id} digest={self.digest} -->"
        )


@dataclass(frozen=True, slots=True)
class ApprovedEngineeringTask:
    task: EngineeringTask
    artifact_id: str
    approved_by: str
    approved_at: str
    approval_rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "task_digest": self.task.digest,
            "artifact_id": self.artifact_id,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "approval_rationale": self.approval_rationale,
        }


@dataclass(frozen=True, slots=True)
class EngineeringIssueBinding:
    task_id: str
    task_digest: str
    workspace_id: str
    repository: str
    issue_number: int
    issue_url: str

    def __post_init__(self) -> None:
        if self.issue_number <= 0:
            raise EngineeringHandoffError("engineering issue number must be positive")
        if not self.issue_url.strip():
            raise EngineeringHandoffError("engineering issue URL is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EngineeringNotification:
    kind: str
    message: str
    evidence: tuple[str, ...]
    signature: str

    def __post_init__(self) -> None:
        if self.kind not in {
            "decision",
            "blocker",
            "blocker_resolved",
            "merge_ready",
            "merge_readiness_revoked",
        }:
            raise EngineeringHandoffError(
                f"unsupported engineering notification: {self.kind}"
            )
        if not self.message.strip() or not self.evidence:
            raise EngineeringHandoffError(
                "engineering notifications require a message and evidence"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "evidence": list(self.evidence),
            "signature": self.signature,
        }


@dataclass(frozen=True, slots=True)
class EngineeringHandoffSnapshot:
    task_id: str
    task_digest: str
    workspace_id: str
    repository: str
    issue_number: int
    issue_url: str
    state: str
    observed_at: str
    pull_request_number: int = 0
    pull_request_url: str = ""
    head_sha: str = ""
    blockers: tuple[str, ...] = ()
    merge_ready: bool = False
    notification: EngineeringNotification | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "blockers": list(self.blockers),
            "notification": (
                self.notification.to_dict() if self.notification is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EngineeringHandoffSnapshot":
        raw_notification = value.get("notification")
        notification = None
        if isinstance(raw_notification, Mapping):
            notification = EngineeringNotification(
                kind=str(raw_notification["kind"]),
                message=str(raw_notification["message"]),
                evidence=tuple(str(item) for item in raw_notification["evidence"]),
                signature=str(raw_notification["signature"]),
            )
        return cls(
            task_id=str(value["task_id"]),
            task_digest=str(value["task_digest"]),
            workspace_id=str(value["workspace_id"]),
            repository=str(value["repository"]),
            issue_number=int(value["issue_number"]),
            issue_url=str(value["issue_url"]),
            state=str(value["state"]),
            observed_at=str(value["observed_at"]),
            pull_request_number=int(value.get("pull_request_number", 0)),
            pull_request_url=str(value.get("pull_request_url", "")),
            head_sha=str(value.get("head_sha", "")),
            blockers=tuple(str(item) for item in value.get("blockers", [])),
            merge_ready=bool(value.get("merge_ready", False)),
            notification=notification,
        )


class EngineeringGitHubAPI(Protocol):
    def find_issues_by_marker(self, marker: str) -> list[Mapping[str, Any]]: ...

    def create_issue(self, title: str, body: str) -> Mapping[str, Any]: ...

    def get_issue(self, number: int) -> Mapping[str, Any]: ...

    def list_issue_timeline(self, number: int) -> list[Mapping[str, Any]]: ...

    def get_pull_request(self, number: int) -> Mapping[str, Any]: ...

    def list_check_runs(self, head_sha: str) -> list[Mapping[str, Any]]: ...

    def list_pull_request_reviews(self, number: int) -> list[Mapping[str, Any]]: ...

    def list_issue_comments(self, number: int) -> list[Mapping[str, Any]]: ...

    def add_issue_comment(self, number: int, body: str) -> Mapping[str, Any]: ...


class EngineeringTaskService:
    RUN_ID = "tony-engineering-tasks"
    STAGE_ID = "engineering-task-approval"
    ARTIFACT_TYPE = "approved_engineering_task"
    SUCCESS_CONCLUSIONS = {"success", "neutral", "skipped"}
    def __init__(
        self,
        *,
        workspace_id: str,
        client_id: str,
        repository: str,
        artifact_catalog: FileArtifactCatalog,
        execution_journal: ExecutionJournal,
        github: EngineeringGitHubAPI,
        required_checks: Iterable[str] = (),
        required_reviewers: Iterable[str] = (),
        allowed_approvers: Iterable[str] = (),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.workspace_id = workspace_id
        self.client_id = client_id
        self.repository = repository
        self.artifacts = artifact_catalog
        self.journal = execution_journal
        self.github = github
        self.required_checks = tuple(
            sorted({item.strip() for item in required_checks if item.strip()})
        )
        self.required_reviewers = tuple(
            sorted(
                {item.strip() for item in required_reviewers if item.strip()},
                key=str.casefold,
            )
        )
        self.allowed_approvers = tuple(
            sorted(
                {item.strip() for item in allowed_approvers if item.strip()},
                key=str.casefold,
            )
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def approve(
        self,
        task: EngineeringTask,
        *,
        command_id: str,
        reviewer_id: str,
        rationale: str,
    ) -> ApprovedEngineeringTask:
        self._verify_journal()
        self._validate_context(task)
        command_id = _required_text(command_id, "command_id")
        reviewer_id = _required_text(reviewer_id, "reviewer_id")
        rationale = _required_text(rationale, "approval_rationale")
        if not self.allowed_approvers:
            raise EngineeringHandoffError(
                "engineering task approver allowlist is not configured"
            )
        if reviewer_id.casefold() not in {
            item.casefold() for item in self.allowed_approvers
        }:
            raise EngineeringHandoffError(
                "reviewer is not authorized to approve engineering tasks"
            )
        existing = self._approved(task.task_id)
        if existing is not None:
            if existing.task.digest != task.digest:
                raise EngineeringHandoffError(
                    "approved engineering task is immutable and its digest changed"
                )
            return existing

        approved_at = self._now()
        content = json.dumps(
            {
                "schema_version": 1,
                "task": task.to_dict(),
                "task_digest": task.digest,
                "approval": {
                    "approved_by": reviewer_id,
                    "approved_at": approved_at,
                    "rationale": rationale,
                },
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        artifact = self.artifacts.register(
            run_id=self.RUN_ID,
            stage_id=self.STAGE_ID,
            artifact_type=self.ARTIFACT_TYPE,
            content=content,
            producer="Tony",
            extension=".json",
            metadata={
                "task_id": task.task_id,
                "task_digest": task.digest,
                "repository": task.repository,
            },
        )
        self.journal.append(
            decision_id=self._decision_id(task.task_id),
            workspace_id=self.workspace_id,
            client_id=self.client_id,
            action="engineering_task.approved",
            rationale=rationale,
            actor=reviewer_id,
            status="completed",
            state_hash=task.digest,
            artifacts=(artifact.artifact.artifact_id,),
            metadata={
                "command_id": command_id,
                "task_id": task.task_id,
                "task_digest": task.digest,
                "repository": task.repository,
                "approved_at": approved_at,
                "artifact_version": artifact.version,
            },
        )
        return ApprovedEngineeringTask(
            task=task,
            artifact_id=artifact.artifact.artifact_id,
            approved_by=reviewer_id,
            approved_at=approved_at,
            approval_rationale=rationale,
        )

    def create_issue(
        self,
        task_id: str,
        *,
        command_id: str,
        actor: str = "Tony",
    ) -> EngineeringIssueBinding:
        with self._task_lock(task_id):
            return self._create_issue_locked(
                task_id,
                command_id=command_id,
                actor=actor,
            )

    def _create_issue_locked(
        self,
        task_id: str,
        *,
        command_id: str,
        actor: str,
    ) -> EngineeringIssueBinding:
        self._verify_journal()
        approved = self._require_approved(task_id)
        command_id = _required_text(command_id, "command_id")
        binding = self._binding(task_id)
        if binding is not None:
            self._validate_binding(binding, approved.task)
            return binding

        matches = self.github.find_issues_by_marker(approved.task.marker)
        if len(matches) > 1:
            self._audit_blocked(
                approved.task,
                "engineering_issue.reconcile",
                "multiple GitHub Issues contain the approved task marker",
                {"issue_numbers": [int(item.get("number", 0)) for item in matches]},
            )
            raise EngineeringHandoffError(
                "multiple GitHub Issues contain the approved task marker"
            )
        if len(matches) == 1:
            return self._record_binding(
                approved.task,
                matches[0],
                command_id=command_id,
                actor=actor,
                rationale="Recovered the existing GitHub Issue by approved task marker",
            )

        self.journal.append(
            decision_id=self._decision_id(task_id),
            workspace_id=self.workspace_id,
            client_id=self.client_id,
            action="engineering_issue.create",
            rationale="Create the canonical GitHub Issue from the approved task",
            actor=actor,
            status="selected",
            state_hash=approved.task.digest,
            artifacts=(approved.artifact_id,),
            metadata={
                "command_id": command_id,
                "task_id": task_id,
                "task_digest": approved.task.digest,
                "repository": self.repository,
                "marker": approved.task.marker,
            },
        )
        try:
            issue = self.github.create_issue(
                approved.task.title,
                self._render_issue(approved),
            )
        except Exception as exc:
            self.journal.append(
                decision_id=self._decision_id(task_id),
                workspace_id=self.workspace_id,
                client_id=self.client_id,
                action="engineering_issue.create",
                rationale="GitHub Issue creation outcome requires marker reconciliation",
                actor=actor,
                status="failed",
                state_hash=approved.task.digest,
                artifacts=(approved.artifact_id,),
                metadata={
                    "command_id": command_id,
                    "task_id": task_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise EngineeringHandoffError(
                "GitHub Issue creation failed; reconcile by task marker before retrying"
            ) from exc
        return self._record_binding(
            approved.task,
            issue,
            command_id=command_id,
            actor=actor,
            rationale="Created and bound the canonical GitHub Issue",
        )

    def get(self, task_id: str) -> dict[str, Any]:
        self._verify_journal()
        approved = self._require_approved(task_id)
        binding = self._binding(task_id)
        latest = self._latest_snapshot(task_id)
        return {
            "approved_task": approved.to_dict(),
            "binding": binding.to_dict() if binding is not None else None,
            "snapshot": latest.to_dict() if latest is not None else None,
            "audit": [
                record.to_dict()
                for record in self.journal.history(self._decision_id(task_id))
            ],
        }

    def refresh(
        self,
        task_id: str,
        *,
        actor: str = "Tony",
    ) -> EngineeringHandoffSnapshot:
        self._verify_journal()
        approved = self._require_approved(task_id)
        binding = self._binding(task_id)
        if binding is None:
            raise EngineeringHandoffError(
                "approved engineering task has no bound GitHub Issue"
            )
        self._validate_binding(binding, approved.task)
        previous = self._latest_snapshot(task_id)
        snapshot = self._observe(binding)
        notification = self._notification(previous, snapshot)
        if notification is not None and self._notification_seen(task_id, notification):
            notification = None
        snapshot = replace(snapshot, notification=notification)
        state_hash = self._snapshot_hash(snapshot, include_notification=False)
        if notification is not None:
            self.journal.append(
                decision_id=self._decision_id(task_id),
                workspace_id=self.workspace_id,
                client_id=self.client_id,
                action="engineering_issue.comment",
                rationale="Publish the material engineering workflow transition",
                actor=actor,
                status="selected",
                state_hash=notification.signature,
                artifacts=(approved.artifact_id,),
                metadata={
                    "notification": notification.to_dict(),
                    "issue_number": binding.issue_number,
                },
            )
            try:
                self._publish_notification(binding, notification)
            except Exception as exc:
                self.journal.append(
                    decision_id=self._decision_id(task_id),
                    workspace_id=self.workspace_id,
                    client_id=self.client_id,
                    action="engineering_issue.comment",
                    rationale="GitHub Issue transition comment failed closed",
                    actor=actor,
                    status="failed",
                    state_hash=notification.signature,
                    artifacts=(approved.artifact_id,),
                    metadata={
                        "issue_number": binding.issue_number,
                        "error_type": type(exc).__name__,
                    },
                )
                raise EngineeringHandoffError(
                    "GitHub Issue transition comment could not be recorded"
                ) from exc
            self.journal.append(
                decision_id=self._decision_id(task_id),
                workspace_id=self.workspace_id,
                client_id=self.client_id,
                action="engineering_task.notification",
                rationale=notification.message,
                actor=actor,
                status="completed",
                state_hash=notification.signature,
                artifacts=(approved.artifact_id,),
                metadata={
                    "notification": notification.to_dict(),
                    "issue_number": binding.issue_number,
                },
            )
        self.journal.append(
            decision_id=self._decision_id(task_id),
            workspace_id=self.workspace_id,
            client_id=self.client_id,
            action="engineering_task.observed",
            rationale="Observed the bound GitHub Issue and linked implementation evidence",
            actor=actor,
            status="completed",
            state_hash=state_hash,
            artifacts=(approved.artifact_id,),
            metadata={"snapshot": snapshot.to_dict()},
        )
        return snapshot

    def list_snapshots(self) -> tuple[EngineeringHandoffSnapshot, ...]:
        self._verify_journal()
        snapshots: dict[str, EngineeringHandoffSnapshot] = {}
        for record in self.journal.read_all():
            if (
                record.workspace_id != self.workspace_id
                or record.action != "engineering_task.observed"
            ):
                continue
            raw = record.metadata.get("snapshot")
            if isinstance(raw, Mapping):
                try:
                    snapshot = EngineeringHandoffSnapshot.from_dict(raw)
                except (KeyError, TypeError, ValueError) as exc:
                    raise EngineeringHandoffError(
                        "engineering handoff snapshot is invalid"
                    ) from exc
                snapshots[snapshot.task_id] = snapshot
        return tuple(snapshots[key] for key in sorted(snapshots))

    def _observe(self, binding: EngineeringIssueBinding) -> EngineeringHandoffSnapshot:
        issue = self.github.get_issue(binding.issue_number)
        if int(issue.get("number", 0)) != binding.issue_number:
            raise EngineeringHandoffError("GitHub returned the wrong bound Issue")
        issue_url = _required_text(issue.get("html_url"), "issue html_url")
        if issue_url != binding.issue_url:
            raise EngineeringHandoffError("bound GitHub Issue URL changed")
        body = str(issue.get("body", ""))
        marker = self._require_approved(binding.task_id).task.marker
        if marker not in body:
            raise EngineeringHandoffError("bound GitHub Issue lost its approved task marker")

        issue_state = _required_text(issue.get("state"), "issue state").casefold()
        if issue_state != "open":
            return self._snapshot(binding, state="merged_or_closed")
        issue_labels = issue.get("labels", [])
        if not isinstance(issue_labels, list):
            raise EngineeringHandoffError("GitHub Issue labels must be a list")
        if any(
            isinstance(label, Mapping)
            and str(label.get("name", "")).casefold() == "blocked"
            for label in issue_labels
        ):
            return self._snapshot(
                binding,
                state="blocked",
                blockers=("issue_label:blocked",),
            )

        pull_numbers = self._linked_pull_numbers(binding.issue_number)
        if not pull_numbers:
            return self._snapshot(binding, state="awaiting_implementation")

        pulls = [self.github.get_pull_request(number) for number in pull_numbers]
        open_pulls = [
            pull
            for pull in pulls
            if str(pull.get("state", "")).casefold() == "open"
            and not bool(pull.get("merged", False))
        ]
        if not open_pulls:
            return self._snapshot(binding, state="merged_or_closed")
        if len(open_pulls) > 1:
            for pull in open_pulls:
                _required_text(pull.get("html_url"), "pull request html_url")
            return self._snapshot(
                binding,
                state="blocked",
                blockers=("multiple_linked_open_pull_requests",),
            )

        pull = open_pulls[0]
        number = int(pull.get("number", 0))
        if number <= 0:
            raise EngineeringHandoffError(
                "GitHub linked pull request number must be positive"
            )
        url = _required_text(pull.get("html_url"), "pull request html_url")
        head = pull.get("head")
        if not isinstance(head, Mapping):
            raise EngineeringHandoffError("GitHub pull request head must be an object")
        head_sha = _required_text(head.get("sha"), "pull request head.sha")
        if bool(pull.get("draft", False)):
            return self._snapshot(
                binding,
                state="implementing",
                pull_request_number=number,
                pull_request_url=url,
                head_sha=head_sha,
            )

        blockers = self._readiness_blockers(pull, head_sha)
        return self._snapshot(
            binding,
            state="blocked" if blockers else "merge_ready",
            pull_request_number=number,
            pull_request_url=url,
            head_sha=head_sha,
            blockers=blockers,
            merge_ready=not blockers,
        )

    def _readiness_blockers(
        self,
        pull: Mapping[str, Any],
        head_sha: str,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if pull.get("mergeable") is not True:
            blockers.append(
                "mergeability_unknown"
                if pull.get("mergeable") is None
                else "merge_conflict"
            )
        labels = pull.get("labels", [])
        if not isinstance(labels, list):
            raise EngineeringHandoffError("GitHub pull request labels must be a list")
        label_names = {
            str(label.get("name", "")).casefold()
            for label in labels
            if isinstance(label, Mapping)
        }
        if "blocked" in label_names:
            blockers.append("label:blocked")

        checks = self.github.list_check_runs(head_sha)
        latest_checks: dict[str, Mapping[str, Any]] = {}
        for check in checks:
            name = _required_text(check.get("name"), "check run name")
            latest_checks[name] = check
        if not self.required_checks:
            blockers.append("required_checks_not_configured")
        for name in self.required_checks:
            check = latest_checks.get(name)
            if check is None:
                blockers.append(f"missing_check:{name}")
                continue
            status = str(check.get("status", "")).casefold()
            conclusion = str(check.get("conclusion", "")).casefold()
            if status != "completed" or not conclusion:
                blockers.append(f"pending_check:{name}")
            elif conclusion not in self.SUCCESS_CONCLUSIONS:
                blockers.append(f"failed_check:{name}")

        reviews = self.github.list_pull_request_reviews(int(pull.get("number", 0)))
        latest_reviews: dict[str, Mapping[str, Any]] = {}
        for review in reviews:
            user = review.get("user")
            if not isinstance(user, Mapping):
                raise EngineeringHandoffError("GitHub review user must be an object")
            login = _required_text(user.get("login"), "review user login").casefold()
            latest_reviews[login] = review
        for login, review in latest_reviews.items():
            if str(review.get("state", "")).casefold() == "changes_requested":
                blockers.append(f"changes_requested:{login}")
        if not self.required_reviewers:
            blockers.append("required_reviewers_not_configured")
        for reviewer in self.required_reviewers:
            review = latest_reviews.get(reviewer.casefold())
            if review is None:
                blockers.append(f"missing_approval:{reviewer}")
                continue
            if str(review.get("state", "")).casefold() != "approved":
                blockers.append(f"missing_approval:{reviewer}")
            elif str(review.get("commit_id", "")).strip() != head_sha:
                blockers.append(f"stale_approval:{reviewer}")
        return tuple(dict.fromkeys(blockers))

    def _linked_pull_numbers(self, issue_number: int) -> tuple[int, ...]:
        numbers: set[int] = set()
        for event in self.github.list_issue_timeline(issue_number):
            if str(event.get("event", "")).casefold() != "cross-referenced":
                continue
            source = event.get("source")
            source_issue = source.get("issue") if isinstance(source, Mapping) else None
            if not isinstance(source_issue, Mapping) or "pull_request" not in source_issue:
                continue
            repository = source_issue.get("repository")
            full_name = (
                str(repository.get("full_name", ""))
                if isinstance(repository, Mapping)
                else ""
            )
            if not full_name:
                repository_url = str(source_issue.get("repository_url", "")).rstrip("/")
                match = re.search(r"/repos/([^/]+/[^/]+)$", repository_url)
                if match:
                    full_name = match.group(1)
            if not full_name:
                html_url = str(source_issue.get("html_url", ""))
                match = re.match(
                    r"https://[^/]+/([^/]+/[^/]+)/(?:pull|issues)/\d+",
                    html_url,
                )
                if match:
                    full_name = match.group(1)
            if full_name.casefold() != self.repository.casefold():
                continue
            number = int(source_issue.get("number", 0))
            if number > 0:
                numbers.add(number)
        return tuple(sorted(numbers))

    def _notification(
        self,
        previous: EngineeringHandoffSnapshot | None,
        current: EngineeringHandoffSnapshot,
    ) -> EngineeringNotification | None:
        kind = ""
        message = ""
        if current.blockers:
            if previous is None or previous.blockers != current.blockers:
                kind = "decision" if "multiple_linked_open_pull_requests" in current.blockers else "blocker"
                message = (
                    f"Engineering task {current.task_id} requires a decision: "
                    "multiple linked implementation PRs are open."
                    if kind == "decision"
                    else f"Engineering task {current.task_id} is blocked: "
                    + ", ".join(current.blockers)
                )
        elif current.merge_ready and (
            previous is None
            or not previous.merge_ready
            or previous.head_sha != current.head_sha
        ):
            kind = "merge_ready"
            message = (
                f"Engineering task {current.task_id} is ready for Matt's merge decision."
            )
        elif previous is not None and previous.blockers:
            kind = "blocker_resolved"
            message = f"Engineering task {current.task_id}'s recorded blocker is resolved."
        elif (
            previous is not None
            and previous.merge_ready
            and not current.merge_ready
        ):
            kind = "merge_readiness_revoked"
            message = f"Engineering task {current.task_id} is no longer merge-ready."
        if not kind:
            return None
        evidence = tuple(
            item
            for item in (current.issue_url, current.pull_request_url)
            if item
        )
        signature = hashlib.sha256(
            json.dumps(
                {
                    "task_id": current.task_id,
                    "kind": kind,
                    "blockers": current.blockers,
                    "head_sha": current.head_sha,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return EngineeringNotification(kind, message, evidence, signature)

    def _publish_notification(
        self,
        binding: EngineeringIssueBinding,
        notification: EngineeringNotification,
    ) -> None:
        marker = f"<!-- tony-engineering-event:{notification.signature} -->"
        comments = self.github.list_issue_comments(binding.issue_number)
        if any(marker in str(comment.get("body", "")) for comment in comments):
            return
        self.github.add_issue_comment(
            binding.issue_number,
            f"{marker}\n\n{notification.message}",
        )

    def _record_binding(
        self,
        task: EngineeringTask,
        issue: Mapping[str, Any],
        *,
        command_id: str,
        actor: str,
        rationale: str,
    ) -> EngineeringIssueBinding:
        binding = EngineeringIssueBinding(
            task_id=task.task_id,
            task_digest=task.digest,
            workspace_id=self.workspace_id,
            repository=self.repository,
            issue_number=int(issue.get("number", 0)),
            issue_url=_required_text(issue.get("html_url"), "issue html_url"),
        )
        body = str(issue.get("body", ""))
        if task.marker not in body:
            raise EngineeringHandoffError(
                "GitHub Issue response does not contain the approved task marker"
            )
        approved = self._require_approved(task.task_id)
        self.journal.append(
            decision_id=self._decision_id(task.task_id),
            workspace_id=self.workspace_id,
            client_id=self.client_id,
            action="engineering_issue.bound",
            rationale=rationale,
            actor=actor,
            status="completed",
            state_hash=task.digest,
            artifacts=(approved.artifact_id,),
            metadata={
                "command_id": command_id,
                "binding": binding.to_dict(),
            },
        )
        return binding

    def _approved(self, task_id: str) -> ApprovedEngineeringTask | None:
        records = self.journal.history(self._decision_id(task_id))
        approval = next(
            (
                record
                for record in records
                if record.action == "engineering_task.approved"
                and record.status == "completed"
            ),
            None,
        )
        if approval is None:
            return None
        if len(approval.artifacts) != 1:
            raise EngineeringHandoffError(
                "approved engineering task must reference exactly one artifact"
            )
        matches = self.artifacts.get(approval.artifacts[0])
        artifact_version = int(approval.metadata.get("artifact_version", 0))
        if artifact_version:
            matches = [
                item
                for item in matches
                if item.run_id == self.RUN_ID
                and item.stage_id == self.STAGE_ID
                and item.version == artifact_version
            ]
        if len(matches) != 1:
            raise EngineeringHandoffError(
                "approved engineering task artifact is missing or ambiguous"
            )
        record = matches[0]
        try:
            content = Path(record.artifact.location).read_text(encoding="utf-8")
        except OSError as exc:
            raise EngineeringHandoffError(
                "approved engineering task artifact cannot be read"
            ) from exc
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if checksum != record.artifact.checksum:
            raise EngineeringHandoffError(
                "approved engineering task artifact checksum mismatch"
            )
        try:
            payload = json.loads(content)
            task = EngineeringTask.from_dict(payload["task"])
            raw_approval = payload["approval"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise EngineeringHandoffError(
                "approved engineering task artifact is invalid"
            ) from exc
        if not isinstance(raw_approval, Mapping):
            raise EngineeringHandoffError(
                "approved engineering task approval is invalid"
            )
        if (
            payload.get("task_digest") != task.digest
            or approval.state_hash != task.digest
        ):
            raise EngineeringHandoffError("approved engineering task digest mismatch")
        return ApprovedEngineeringTask(
            task=task,
            artifact_id=record.artifact.artifact_id,
            approved_by=_required_text(raw_approval.get("approved_by"), "approved_by"),
            approved_at=_required_text(raw_approval.get("approved_at"), "approved_at"),
            approval_rationale=_required_text(
                raw_approval.get("rationale"), "approval_rationale"
            ),
        )

    def _require_approved(self, task_id: str) -> ApprovedEngineeringTask:
        approved = self._approved(_required_text(task_id, "task_id"))
        if approved is None:
            raise EngineeringHandoffError("engineering task is not approved")
        self._validate_context(approved.task)
        return approved

    def _binding(self, task_id: str) -> EngineeringIssueBinding | None:
        for record in reversed(self.journal.history(self._decision_id(task_id))):
            if record.action != "engineering_issue.bound" or record.status != "completed":
                continue
            value = record.metadata.get("binding")
            if not isinstance(value, Mapping):
                raise EngineeringHandoffError("engineering issue binding is invalid")
            try:
                return EngineeringIssueBinding(
                    task_id=str(value["task_id"]),
                    task_digest=str(value["task_digest"]),
                    workspace_id=str(value["workspace_id"]),
                    repository=str(value["repository"]),
                    issue_number=int(value["issue_number"]),
                    issue_url=str(value["issue_url"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise EngineeringHandoffError(
                    "engineering issue binding is invalid"
                ) from exc
        return None

    def _latest_snapshot(self, task_id: str) -> EngineeringHandoffSnapshot | None:
        for record in reversed(self.journal.history(self._decision_id(task_id))):
            if record.action != "engineering_task.observed":
                continue
            value = record.metadata.get("snapshot")
            if not isinstance(value, Mapping):
                raise EngineeringHandoffError("engineering handoff snapshot is invalid")
            try:
                return EngineeringHandoffSnapshot.from_dict(value)
            except (KeyError, TypeError, ValueError) as exc:
                raise EngineeringHandoffError(
                    "engineering handoff snapshot is invalid"
                ) from exc
        return None

    def _notification_seen(
        self,
        task_id: str,
        notification: EngineeringNotification,
    ) -> bool:
        return any(
            record.action == "engineering_task.notification"
            and record.state_hash == notification.signature
            for record in self.journal.history(self._decision_id(task_id))
        )

    def _validate_context(self, task: EngineeringTask) -> None:
        if task.workspace_id != self.workspace_id:
            raise EngineeringHandoffError(
                "engineering task belongs to a different workspace"
            )
        if task.repository.casefold() != self.repository.casefold():
            raise EngineeringHandoffError(
                "engineering task belongs to a different repository"
            )

    def _validate_binding(
        self,
        binding: EngineeringIssueBinding,
        task: EngineeringTask,
    ) -> None:
        if (
            binding.task_id != task.task_id
            or binding.task_digest != task.digest
            or binding.workspace_id != self.workspace_id
            or binding.repository.casefold() != self.repository.casefold()
        ):
            raise EngineeringHandoffError(
                "engineering issue binding does not match the approved task"
            )

    def _audit_blocked(
        self,
        task: EngineeringTask,
        action: str,
        rationale: str,
        metadata: Mapping[str, Any],
    ) -> None:
        self.journal.append(
            decision_id=self._decision_id(task.task_id),
            workspace_id=self.workspace_id,
            client_id=self.client_id,
            action=action,
            rationale=rationale,
            actor="Tony",
            status="blocked",
            state_hash=task.digest,
            metadata={"task_id": task.task_id, **dict(metadata)},
        )

    def _verify_journal(self) -> None:
        try:
            self.journal.verify()
        except ExecutionJournalError as exc:
            raise EngineeringHandoffError(
                "engineering task audit journal failed integrity verification"
            ) from exc

    def _task_lock(self, task_id: str):
        return engineering_task_lock(
            self.journal.state_dir,
            task_id,
            error_type=EngineeringHandoffError,
            error_prefix="engineering task",
        )

    def _snapshot(
        self,
        binding: EngineeringIssueBinding,
        *,
        state: str,
        pull_request_number: int = 0,
        pull_request_url: str = "",
        head_sha: str = "",
        blockers: tuple[str, ...] = (),
        merge_ready: bool = False,
    ) -> EngineeringHandoffSnapshot:
        return EngineeringHandoffSnapshot(
            task_id=binding.task_id,
            task_digest=binding.task_digest,
            workspace_id=binding.workspace_id,
            repository=binding.repository,
            issue_number=binding.issue_number,
            issue_url=binding.issue_url,
            state=state,
            observed_at=self._now(),
            pull_request_number=pull_request_number,
            pull_request_url=pull_request_url,
            head_sha=head_sha,
            blockers=blockers,
            merge_ready=merge_ready,
        )

    @staticmethod
    def _snapshot_hash(
        snapshot: EngineeringHandoffSnapshot,
        *,
        include_notification: bool,
    ) -> str:
        value = snapshot.to_dict()
        if not include_notification:
            value["notification"] = None
        return hashlib.sha256(
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _decision_id(task_id: str) -> str:
        return f"engineering-task:{task_id}"

    def _now(self) -> str:
        return (
            self._clock()
            .astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _render_issue(approved: ApprovedEngineeringTask) -> str:
        task = approved.task

        def bullets(items: tuple[str, ...]) -> str:
            return "\n".join(f"- {item}" for item in items) or "- None"

        return "\n".join(
            (
                task.marker,
                "",
                "## Problem",
                "",
                task.problem,
                "",
                "## Scope",
                "",
                bullets(task.scope),
                "",
                "## Non-goals",
                "",
                bullets(task.non_goals),
                "",
                "## Acceptance criteria",
                "",
                bullets(task.acceptance_criteria),
                "",
                "## Verification",
                "",
                bullets(task.verification),
                "",
                "## Handoff",
                "",
                f"- Implementation agent: {task.implementation_agent}",
                f"- Approved by: {approved.approved_by}",
                f"- Approved at: {approved.approved_at}",
                f"- Approval rationale: {approved.approval_rationale}",
                f"- Task digest: `{task.digest}`",
                "",
                "Implementation pull requests must include "
                "`Closes #<this-issue-number>` in the PR body.",
            )
        )
