from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from runtime.mission_control import WorkstreamStatus


_FAILURE_STATES = {"failure", "failed", "error", "cancelled", "timed_out"}
_BLOCKING_LABELS = {"blocked", "blocker"}


@dataclass(frozen=True)
class GitHubWorkItem:
    kind: str
    number: int
    title: str
    url: str
    state: str
    evidence: tuple[str, ...]
    blocker: str | None = None
    requires_review: bool = False

    @property
    def workstream_id(self) -> str:
        return f"github:{self.kind}:{self.number}"

    def to_workstream(self) -> WorkstreamStatus:
        if self.blocker:
            work_state = "blocked"
            next_action = f"Resolve {self.blocker}."
        elif self.requires_review:
            work_state = "tested"
            next_action = "Record the requested review decision."
        else:
            work_state = "known"
            next_action = "Continue through the recorded repository workflow."

        return WorkstreamStatus(
            workstream_id=self.workstream_id,
            title=f"{self.kind.upper()} #{self.number}: {self.title}",
            state=work_state,
            owner="repository",
            next_action=next_action,
            evidence=self.evidence,
            blocker=self.blocker,
        )


@dataclass(frozen=True)
class GitHubWorkSnapshot:
    repository: str
    state: str
    pull_requests: tuple[GitHubWorkItem, ...]
    issues: tuple[GitHubWorkItem, ...]
    approvals_required: tuple[str, ...]
    blockers: tuple[str, ...]
    evidence: tuple[str, ...]
    error: str | None = None

    def workstreams(self) -> tuple[WorkstreamStatus, ...]:
        if self.state != "connected":
            return ()
        return tuple(item.to_workstream() for item in (*self.pull_requests, *self.issues))

    def connection(self) -> dict[str, str]:
        payload = {"state": self.state}
        if self.evidence:
            payload["evidence"] = self.evidence[0]
        return payload


class GitHubWorkAdapter:
    """Normalise read-only GitHub records for Mission Control without inventing state."""

    def build(
        self,
        *,
        repository: str,
        pull_requests: Iterable[Mapping[str, Any]] = (),
        issues: Iterable[Mapping[str, Any]] = (),
        available: bool = True,
        error: str | None = None,
    ) -> GitHubWorkSnapshot:
        if not available:
            return GitHubWorkSnapshot(
                repository=repository,
                state="not_connected",
                pull_requests=(),
                issues=(),
                approvals_required=(),
                blockers=(),
                evidence=(),
                error=error or "GitHub source unavailable",
            )

        prs = tuple(sorted((self._pull_request(value) for value in pull_requests), key=lambda item: item.number))
        pr_numbers = {item.number for item in prs}
        issue_items = tuple(
            sorted(
                (self._issue(value) for value in issues if int(value["number"]) not in pr_numbers),
                key=lambda item: item.number,
            )
        )
        items = (*prs, *issue_items)
        approvals = tuple(
            f"Review {item.kind} #{item.number}: {item.title} — {item.url}"
            for item in items
            if item.requires_review
        )
        blockers = tuple(
            f"{item.workstream_id}:{item.blocker}"
            for item in items
            if item.blocker
        )
        evidence = tuple(dict.fromkeys(item.url for item in items))

        return GitHubWorkSnapshot(
            repository=repository,
            state="connected",
            pull_requests=prs,
            issues=issue_items,
            approvals_required=approvals,
            blockers=blockers,
            evidence=evidence,
        )

    @staticmethod
    def _pull_request(value: Mapping[str, Any]) -> GitHubWorkItem:
        number = int(value["number"])
        title = str(value["title"])
        url = str(value["url"])
        ci_status = str(value.get("ci_status", "unknown")).lower()
        mergeable = value.get("mergeable")
        requires_review = bool(value.get("review_requested", False))

        blocker = None
        if ci_status in _FAILURE_STATES:
            blocker = f"CI {ci_status}"
        elif mergeable is False:
            blocker = "merge conflict"

        return GitHubWorkItem(
            kind="pr",
            number=number,
            title=title,
            url=url,
            state="open",
            evidence=(url,),
            blocker=blocker,
            requires_review=requires_review,
        )

    @staticmethod
    def _issue(value: Mapping[str, Any]) -> GitHubWorkItem:
        number = int(value["number"])
        title = str(value["title"])
        url = str(value["url"])
        labels = {str(label).strip().lower() for label in value.get("labels", ())}
        blocker = "blocked label" if labels & _BLOCKING_LABELS else None

        return GitHubWorkItem(
            kind="issue",
            number=number,
            title=title,
            url=url,
            state="open",
            evidence=(url,),
            blocker=blocker,
            requires_review=False,
        )
