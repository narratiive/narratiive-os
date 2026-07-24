from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol


class GitHubWorkError(RuntimeError):
    """Raised when live GitHub work cannot be read or trusted."""


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise GitHubWorkError(f"GitHub response is missing {field_name}")
    return text


def _optional_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True, slots=True)
class GitHubWorkItem:
    kind: str
    number: int
    title: str
    url: str
    state: str
    author: str
    created_at: str
    updated_at: str
    labels: tuple[str, ...] = ()
    draft: bool = False
    head_sha: str = ""
    requested_reviewers: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"pull_request", "issue"}:
            raise GitHubWorkError(f"unsupported GitHub work kind: {self.kind}")
        if self.number <= 0:
            raise GitHubWorkError("GitHub work item number must be positive")
        for field_name in ("title", "url", "state", "created_at", "updated_at"):
            if not str(getattr(self, field_name)).strip():
                raise GitHubWorkError(f"GitHub work item requires {field_name}")

    @property
    def evidence(self) -> str:
        return f"{self.url}#updated-{self.updated_at}"

    def material_signature(self) -> tuple[Any, ...]:
        return (
            self.title,
            self.state,
            self.labels,
            self.draft,
            self.head_sha,
            self.requested_reviewers,
            self.blocker_reasons,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "state": self.state,
            "author": self.author,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "labels": list(self.labels),
            "draft": self.draft,
            "head_sha": self.head_sha,
            "requested_reviewers": list(self.requested_reviewers),
            "blocker_reasons": list(self.blocker_reasons),
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GitHubWorkItem":
        return cls(
            kind=str(value["kind"]),
            number=int(value["number"]),
            title=str(value["title"]),
            url=str(value["url"]),
            state=str(value["state"]),
            author=str(value.get("author", "")),
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            labels=tuple(str(item) for item in value.get("labels", [])),
            draft=bool(value.get("draft", False)),
            head_sha=str(value.get("head_sha", "")),
            requested_reviewers=tuple(
                str(item) for item in value.get("requested_reviewers", [])
            ),
            blocker_reasons=tuple(
                str(item) for item in value.get("blocker_reasons", [])
            ),
        )


@dataclass(frozen=True, slots=True)
class GitHubChange:
    action: str
    item: GitHubWorkItem

    def __post_init__(self) -> None:
        if self.action not in {"opened", "no_longer_open", "materially_updated"}:
            raise GitHubWorkError(f"unsupported GitHub change action: {self.action}")

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "item": self.item.to_dict()}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GitHubChange":
        return cls(
            action=str(value["action"]),
            item=GitHubWorkItem.from_dict(value["item"]),
        )


@dataclass(frozen=True, slots=True)
class GitHubWorkSnapshot:
    repository: str
    workspace_id: str
    observed_at: str
    baseline_status: str
    baseline_artifact_id: str
    open_pull_requests: tuple[GitHubWorkItem, ...]
    active_issues: tuple[GitHubWorkItem, ...]
    blocked: tuple[GitHubWorkItem, ...]
    matt_approval_required: tuple[GitHubWorkItem, ...]
    changes_since_previous_brief: tuple[GitHubChange, ...]

    def __post_init__(self) -> None:
        if self.baseline_status not in {"available", "unavailable"}:
            raise GitHubWorkError(
                f"unsupported GitHub baseline status: {self.baseline_status}"
            )
        if self.baseline_status == "available" and not self.baseline_artifact_id:
            raise GitHubWorkError("available GitHub baseline requires an artifact id")

    @property
    def all_open_items(self) -> tuple[GitHubWorkItem, ...]:
        return (*self.open_pull_requests, *self.active_issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "workspace_id": self.workspace_id,
            "observed_at": self.observed_at,
            "baseline_status": self.baseline_status,
            "baseline_artifact_id": self.baseline_artifact_id,
            "open_pull_requests": [
                item.to_dict() for item in self.open_pull_requests
            ],
            "active_issues": [item.to_dict() for item in self.active_issues],
            "blocked": [item.to_dict() for item in self.blocked],
            "matt_approval_required": [
                item.to_dict() for item in self.matt_approval_required
            ],
            "changes_since_previous_brief": [
                item.to_dict() for item in self.changes_since_previous_brief
            ],
            "summary": {
                "open_pull_requests": len(self.open_pull_requests),
                "active_issues": len(self.active_issues),
                "blocked": len(self.blocked),
                "matt_approval_required": len(self.matt_approval_required),
                "changes_since_previous_brief": len(
                    self.changes_since_previous_brief
                ),
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GitHubWorkSnapshot":
        return cls(
            repository=str(value["repository"]),
            workspace_id=str(value["workspace_id"]),
            observed_at=str(value["observed_at"]),
            baseline_status=str(value.get("baseline_status", "unavailable")),
            baseline_artifact_id=str(value.get("baseline_artifact_id", "")),
            open_pull_requests=tuple(
                GitHubWorkItem.from_dict(item)
                for item in value.get("open_pull_requests", [])
            ),
            active_issues=tuple(
                GitHubWorkItem.from_dict(item)
                for item in value.get("active_issues", [])
            ),
            blocked=tuple(
                GitHubWorkItem.from_dict(item)
                for item in value.get("blocked", [])
            ),
            matt_approval_required=tuple(
                GitHubWorkItem.from_dict(item)
                for item in value.get("matt_approval_required", [])
            ),
            changes_since_previous_brief=tuple(
                GitHubChange.from_dict(item)
                for item in value.get("changes_since_previous_brief", [])
            ),
        )


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    repository: str
    workspace_id: str
    matt_login: str
    api_url: str = "https://api.github.com"
    timeout_seconds: float = 10.0
    max_pages: int = 20

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise GitHubWorkError("GitHub repository must use owner/name")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.workspace_id):
            raise GitHubWorkError("GitHub workspace_id must be a safe identifier")
        if not re.fullmatch(r"[A-Za-z0-9-]+", self.matt_login):
            raise GitHubWorkError("Matt GitHub login is invalid")
        parsed = urllib.parse.urlsplit(self.api_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise GitHubWorkError("GitHub API URL must use HTTPS")
        if self.timeout_seconds <= 0 or self.max_pages <= 0:
            raise GitHubWorkError("GitHub timeout and max_pages must be positive")


class GitHubAPI(Protocol):
    def list_open_pull_requests(self) -> list[Mapping[str, Any]]: ...

    def list_open_issues(self) -> list[Mapping[str, Any]]: ...

    def get_pull_request(self, number: int) -> Mapping[str, Any]: ...

    def list_check_runs(self, head_sha: str) -> list[Mapping[str, Any]]: ...


class GitHubRESTClient:
    """Small read-only GitHub REST adapter with bounded pagination."""

    FAILURE_CONCLUSIONS = {
        "action_required",
        "cancelled",
        "failure",
        "stale",
        "startup_failure",
        "timed_out",
    }

    def __init__(
        self,
        config: GitHubConfig,
        *,
        token_loader: Callable[[], str] | None = None,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.config = config
        self._token_loader = token_loader or (
            lambda: os.getenv("TONY_GITHUB_TOKEN", "").strip()
        )
        self._opener = opener

    def list_open_pull_requests(self) -> list[Mapping[str, Any]]:
        return self._get_pages(
            f"/repos/{self.config.repository}/pulls",
            {"state": "open", "sort": "updated", "direction": "desc"},
        )

    def list_open_issues(self) -> list[Mapping[str, Any]]:
        return self._get_pages(
            f"/repos/{self.config.repository}/issues",
            {"state": "open", "sort": "updated", "direction": "desc"},
        )

    def get_pull_request(self, number: int) -> Mapping[str, Any]:
        value = self._get(f"/repos/{self.config.repository}/pulls/{number}")
        if not isinstance(value, Mapping):
            raise GitHubWorkError("GitHub pull request response must be an object")
        return value

    def list_check_runs(self, head_sha: str) -> list[Mapping[str, Any]]:
        return self._get_pages(
            f"/repos/{self.config.repository}/commits/{head_sha}/check-runs",
            {"filter": "latest"},
            root_key="check_runs",
        )

    def _get_pages(
        self,
        path: str,
        query: Mapping[str, str],
        *,
        root_key: str | None = None,
    ) -> list[Mapping[str, Any]]:
        values: list[Mapping[str, Any]] = []
        url = self._url(path, {**query, "per_page": "100"})
        for _ in range(self.config.max_pages):
            payload, next_url = self._request(url)
            page = payload.get(root_key) if root_key and isinstance(payload, Mapping) else payload
            if not isinstance(page, list) or not all(
                isinstance(item, Mapping) for item in page
            ):
                raise GitHubWorkError("GitHub paginated response has an invalid shape")
            values.extend(page)
            if not next_url:
                return values
            self._validate_next_url(next_url)
            url = next_url
        raise GitHubWorkError("GitHub pagination exceeded the configured page limit")

    def _get(self, path: str) -> Any:
        payload, next_url = self._request(self._url(path, {}))
        if next_url:
            raise GitHubWorkError("unexpected pagination for GitHub object response")
        return payload

    def _request(self, url: str) -> tuple[Any, str]:
        token = self._token_loader().strip()
        if not token:
            raise GitHubWorkError("GitHub token is not configured")
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Narratiive-OS-Tony",
            },
        )
        try:
            with self._opener(
                request, timeout=self.config.timeout_seconds
            ) as response:
                raw = response.read().decode("utf-8")
                link = str(response.headers.get("Link", ""))
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403, 429}:
                raise GitHubWorkError(
                    f"GitHub request was refused with HTTP {exc.code}"
                ) from exc
            raise GitHubWorkError(f"GitHub request failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise GitHubWorkError(f"GitHub request failed: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GitHubWorkError("GitHub returned invalid JSON") from exc
        return payload, self._next_link(link)

    def _url(self, path: str, query: Mapping[str, str]) -> str:
        encoded = urllib.parse.urlencode(query)
        return f"{self.config.api_url.rstrip('/')}{path}" + (
            f"?{encoded}" if encoded else ""
        )

    def _validate_next_url(self, url: str) -> None:
        expected = urllib.parse.urlsplit(self.config.api_url)
        actual = urllib.parse.urlsplit(url)
        if actual.scheme != expected.scheme or actual.netloc != expected.netloc:
            raise GitHubWorkError("GitHub pagination attempted to leave the API host")

    @staticmethod
    def _next_link(value: str) -> str:
        for part in value.split(","):
            match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part)
            if match and match.group(2) == "next":
                return match.group(1)
        return ""


class GitHubWorkService:
    """Build deterministic executive GitHub state from live read-only responses."""

    FAILURE_CONCLUSIONS = GitHubRESTClient.FAILURE_CONCLUSIONS

    def __init__(
        self,
        config: GitHubConfig,
        api: GitHubAPI,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.api = api
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def build(
        self,
        *,
        previous: GitHubWorkSnapshot | None = None,
        baseline_artifact_id: str = "",
    ) -> GitHubWorkSnapshot:
        pulls = tuple(
            sorted(
                (self._pull_item(value) for value in self.api.list_open_pull_requests()),
                key=lambda item: item.number,
            )
        )
        issues = tuple(
            sorted(
                (
                    self._issue_item(value)
                    for value in self.api.list_open_issues()
                    if "pull_request" not in value
                ),
                key=lambda item: item.number,
            )
        )
        all_items = (*pulls, *issues)
        blocked = tuple(item for item in all_items if item.blocker_reasons)
        matt_login = self.config.matt_login.casefold()
        approvals = tuple(
            item
            for item in pulls
            if matt_login in {reviewer.casefold() for reviewer in item.requested_reviewers}
        )
        changes = self._changes(previous, all_items)
        observed_at = (
            self._clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        return GitHubWorkSnapshot(
            repository=self.config.repository,
            workspace_id=self.config.workspace_id,
            observed_at=observed_at,
            baseline_status="available" if previous else "unavailable",
            baseline_artifact_id=baseline_artifact_id if previous else "",
            open_pull_requests=pulls,
            active_issues=issues,
            blocked=blocked,
            matt_approval_required=approvals,
            changes_since_previous_brief=changes,
        )

    def _pull_item(self, value: Mapping[str, Any]) -> GitHubWorkItem:
        number = int(value.get("number", 0))
        detail = self.api.get_pull_request(number)
        head = detail.get("head", {})
        if not isinstance(head, Mapping):
            raise GitHubWorkError("GitHub pull request head must be an object")
        head_sha = _required_text(head.get("sha"), "pull request head.sha")
        checks = self.api.list_check_runs(head_sha)
        blockers = self._label_blockers(detail)
        if detail.get("mergeable") is False:
            blockers.append("merge_conflict")
        failed_checks = sorted(
            {
                _required_text(check.get("name"), "check run name")
                for check in checks
                if _optional_text(check.get("conclusion")).casefold()
                in self.FAILURE_CONCLUSIONS
            }
        )
        blockers.extend(f"failed_check:{name}" for name in failed_checks)
        reviewers = detail.get("requested_reviewers", [])
        if not isinstance(reviewers, list) or not all(
            isinstance(reviewer, Mapping) for reviewer in reviewers
        ):
            raise GitHubWorkError("GitHub requested_reviewers must be a list")
        return self._item(
            detail,
            kind="pull_request",
            draft=bool(detail.get("draft", False)),
            head_sha=head_sha,
            requested_reviewers=tuple(
                sorted(
                    _required_text(reviewer.get("login"), "requested reviewer login")
                    for reviewer in reviewers
                )
            ),
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )

    def _issue_item(self, value: Mapping[str, Any]) -> GitHubWorkItem:
        return self._item(
            value,
            kind="issue",
            blocker_reasons=tuple(self._label_blockers(value)),
        )

    @staticmethod
    def _item(
        value: Mapping[str, Any],
        *,
        kind: str,
        draft: bool = False,
        head_sha: str = "",
        requested_reviewers: tuple[str, ...] = (),
        blocker_reasons: tuple[str, ...] = (),
    ) -> GitHubWorkItem:
        user = value.get("user", {})
        if not isinstance(user, Mapping):
            raise GitHubWorkError("GitHub work item user must be an object")
        labels = value.get("labels", [])
        if not isinstance(labels, list) or not all(
            isinstance(label, Mapping) for label in labels
        ):
            raise GitHubWorkError("GitHub work item labels must be a list")
        return GitHubWorkItem(
            kind=kind,
            number=int(value.get("number", 0)),
            title=_required_text(value.get("title"), "work item title"),
            url=_required_text(value.get("html_url"), "work item html_url"),
            state=_required_text(value.get("state"), "work item state"),
            author=_optional_text(user.get("login")),
            created_at=_required_text(value.get("created_at"), "work item created_at"),
            updated_at=_required_text(value.get("updated_at"), "work item updated_at"),
            labels=tuple(
                sorted(
                    _required_text(label.get("name"), "label name")
                    for label in labels
                )
            ),
            draft=draft,
            head_sha=head_sha,
            requested_reviewers=requested_reviewers,
            blocker_reasons=blocker_reasons,
        )

    @staticmethod
    def _label_blockers(value: Mapping[str, Any]) -> list[str]:
        labels = value.get("labels", [])
        if not isinstance(labels, list) or not all(
            isinstance(label, Mapping) for label in labels
        ):
            raise GitHubWorkError("GitHub work item labels must be a list")
        names = {
            _optional_text(label.get("name")).casefold()
            for label in labels
        }
        return ["label:blocked"] if "blocked" in names else []

    @staticmethod
    def _changes(
        previous: GitHubWorkSnapshot | None,
        current_items: Iterable[GitHubWorkItem],
    ) -> tuple[GitHubChange, ...]:
        if previous is None:
            return ()
        old = {
            (item.kind, item.number): item for item in previous.all_open_items
        }
        current = {(item.kind, item.number): item for item in current_items}
        changes: list[GitHubChange] = []
        for key in sorted(set(old) | set(current)):
            if key not in old:
                changes.append(GitHubChange("opened", current[key]))
            elif key not in current:
                changes.append(GitHubChange("no_longer_open", old[key]))
            elif old[key].material_signature() != current[key].material_signature():
                changes.append(GitHubChange("materially_updated", current[key]))
        return tuple(changes)
