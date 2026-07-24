from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from runtime.artifact_catalog import FileArtifactCatalog
from runtime.executive_brief import (
    BriefPeriod,
    ExecutiveBriefArchive,
    ExecutiveBriefService,
)
from runtime.github_work import (
    GitHubConfig,
    GitHubRESTClient,
    GitHubWorkError,
    GitHubWorkService,
)
from runtime.mission_control import MissionControlBuilder
from runtime.progress_engine import ProgressSnapshot
from runtime.repositories import JsonlEventLog, WorkflowEvent
from runtime.repository_validator import ValidationReport


def work_item(
    number: int,
    *,
    title: str | None = None,
    labels=(),
    state: str = "open",
    updated_at: str = "2026-07-24T10:00:00Z",
):
    return {
        "number": number,
        "title": title or f"Work {number}",
        "html_url": f"https://github.test/repo/{number}",
        "state": state,
        "user": {"login": "author"},
        "created_at": "2026-07-23T10:00:00Z",
        "updated_at": updated_at,
        "labels": [{"name": label} for label in labels],
    }


def pull_detail(
    number: int,
    *,
    labels=(),
    reviewers=(),
    mergeable=True,
    head_sha: str | None = None,
    title: str | None = None,
):
    return {
        **work_item(number, title=title, labels=labels),
        "draft": False,
        "mergeable": mergeable,
        "head": {"sha": head_sha or f"sha-{number}"},
        "requested_reviewers": [{"login": login} for login in reviewers],
    }


class FakeGitHubAPI:
    def __init__(self, pulls=(), issues=(), details=None, checks=None):
        self.pulls = list(pulls)
        self.issues = list(issues)
        self.details = details or {}
        self.checks = checks or {}

    def list_open_pull_requests(self):
        return list(self.pulls)

    def list_open_issues(self):
        return list(self.issues)

    def get_pull_request(self, number):
        return self.details[number]

    def list_check_runs(self, head_sha):
        return list(self.checks.get(head_sha, []))


class FakeResponse:
    def __init__(self, payload, *, link=""):
        self.payload = payload
        self.headers = {"Link": link}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class GitHubWorkServiceTests(unittest.TestCase):
    def config(self):
        return GitHubConfig(
            repository="narratiive/narratiive-os",
            workspace_id="agency",
            matt_login="Matt-Narratiive",
        )

    def service(self, api, clock=None):
        return GitHubWorkService(
            self.config(),
            api,
            clock=clock
            or (lambda: datetime(2026, 7, 24, 12, tzinfo=timezone.utc)),
        )

    def test_reports_all_open_work_without_duplicating_pulls_as_issues(self):
        pulls = [work_item(10), work_item(11), work_item(12)]
        duplicate_pull = {**work_item(10), "pull_request": {"url": "api/pulls/10"}}
        api = FakeGitHubAPI(
            pulls=pulls,
            issues=[duplicate_pull, work_item(66, labels=("blocked",)), work_item(67)],
            details={
                10: pull_detail(10, reviewers=("matt-narratiive",)),
                11: pull_detail(11, mergeable=False),
                12: pull_detail(12),
            },
            checks={
                "sha-12": [{"name": "runtime-tests", "conclusion": "failure"}],
            },
        )

        snapshot = self.service(api).build()

        self.assertEqual(
            [item.number for item in snapshot.open_pull_requests], [10, 11, 12]
        )
        self.assertEqual([item.number for item in snapshot.active_issues], [66, 67])
        self.assertEqual([item.number for item in snapshot.blocked], [11, 12, 66])
        reasons = {
            item.number: item.blocker_reasons for item in snapshot.blocked
        }
        self.assertEqual(reasons[11], ("merge_conflict",))
        self.assertEqual(reasons[12], ("failed_check:runtime-tests",))
        self.assertEqual(reasons[66], ("label:blocked",))
        self.assertEqual(
            [item.number for item in snapshot.matt_approval_required], [10]
        )
        self.assertEqual(snapshot.baseline_status, "unavailable")
        self.assertEqual(snapshot.changes_since_previous_brief, ())

    def test_changes_compare_material_state_against_previous_brief(self):
        initial_api = FakeGitHubAPI(
            pulls=[work_item(1), work_item(2)],
            issues=[work_item(3)],
            details={1: pull_detail(1), 2: pull_detail(2)},
        )
        previous = self.service(initial_api).build()
        current_api = FakeGitHubAPI(
            pulls=[work_item(1, title="Renamed"), work_item(4)],
            issues=[work_item(3)],
            details={
                1: pull_detail(1, title="Renamed"),
                4: pull_detail(4),
            },
        )

        snapshot = self.service(current_api).build(
            previous=previous,
            baseline_artifact_id="art-previous",
        )

        self.assertEqual(snapshot.baseline_status, "available")
        self.assertEqual(snapshot.baseline_artifact_id, "art-previous")
        self.assertEqual(
            [(change.action, change.item.number) for change in snapshot.changes_since_previous_brief],
            [
                ("materially_updated", 1),
                ("no_longer_open", 2),
                ("opened", 4),
            ],
        )

    def test_only_explicit_outstanding_matt_review_request_counts(self):
        api = FakeGitHubAPI(
            pulls=[work_item(1), work_item(2)],
            details={
                1: pull_detail(1, reviewers=("someone-else",)),
                2: pull_detail(2, reviewers=("MATT-NARRATIIVE",)),
            },
        )

        snapshot = self.service(api).build()

        self.assertEqual(
            [item.number for item in snapshot.matt_approval_required], [2]
        )

    def test_malformed_live_response_fails_closed(self):
        api = FakeGitHubAPI(
            pulls=[work_item(1)],
            details={1: {**pull_detail(1), "head": {}}},
        )
        with self.assertRaisesRegex(GitHubWorkError, "head.sha"):
            self.service(api).build()


class GitHubRESTClientTests(unittest.TestCase):
    def config(self, max_pages=20):
        return GitHubConfig(
            repository="narratiive/narratiive-os",
            workspace_id="agency",
            matt_login="matt",
            max_pages=max_pages,
        )

    def test_follows_same_host_pagination_and_uses_get_only(self):
        calls = []
        responses = [
            FakeResponse(
                [work_item(1)],
                link=(
                    '<https://api.github.com/repos/narratiive/narratiive-os/'
                    'issues?state=open&page=2>; rel="next"'
                ),
            ),
            FakeResponse([work_item(2)]),
        ]

        def opener(request, timeout):
            calls.append((request, timeout))
            return responses.pop(0)

        client = GitHubRESTClient(
            self.config(), token_loader=lambda: "secret", opener=opener
        )

        values = client.list_open_issues()

        self.assertEqual([item["number"] for item in values], [1, 2])
        self.assertTrue(all(request.method == "GET" for request, _ in calls))
        self.assertTrue(all(timeout == 10.0 for _, timeout in calls))

    def test_missing_token_and_cross_host_pagination_fail_closed(self):
        client = GitHubRESTClient(
            self.config(),
            token_loader=lambda: "",
            opener=lambda *_args, **_kwargs: None,
        )
        with self.assertRaisesRegex(GitHubWorkError, "not configured"):
            client.list_open_issues()

        response = FakeResponse(
            [work_item(1)],
            link='<https://evil.test/issues?page=2>; rel="next"',
        )
        client = GitHubRESTClient(
            self.config(),
            token_loader=lambda: "secret",
            opener=lambda *_args, **_kwargs: response,
        )
        with self.assertRaisesRegex(GitHubWorkError, "leave the API host"):
            client.list_open_issues()

    def test_authentication_and_page_limit_fail_closed(self):
        error = urllib.error.HTTPError(
            "https://api.github.com/repos/x/y/issues", 403, "Forbidden", {}, None
        )
        client = GitHubRESTClient(
            self.config(),
            token_loader=lambda: "secret",
            opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
        )
        with self.assertRaisesRegex(GitHubWorkError, "refused"):
            client.list_open_issues()

        response = FakeResponse(
            [work_item(1)],
            link=(
                '<https://api.github.com/repos/narratiive/narratiive-os/'
                'issues?page=2>; rel="next"'
            ),
        )
        client = GitHubRESTClient(
            self.config(max_pages=1),
            token_loader=lambda: "secret",
            opener=lambda *_args, **_kwargs: response,
        )
        with self.assertRaisesRegex(GitHubWorkError, "page limit"):
            client.list_open_issues()


class ExecutiveBriefArchiveTests(unittest.TestCase):
    def progress(self):
        return ProgressSnapshot(
            status="healthy",
            campaigns=(),
            validation=ValidationReport(
                status="pass",
                objects_validated=0,
                errors=(),
                warnings=(),
            ),
        )

    def test_briefs_are_immutable_workspace_scoped_and_event_linked(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        catalog = FileArtifactCatalog(root / "catalog", workspace_id="agency")
        events = JsonlEventLog(root / "events", workspace_id="agency")
        archive = ExecutiveBriefArchive(
            catalog, events, workspace_id="agency"
        )
        api = FakeGitHubAPI(
            pulls=[work_item(1)],
            details={1: pull_detail(1)},
        )
        github = GitHubWorkService(
            GitHubConfig(
                repository="narratiive/narratiive-os",
                workspace_id="agency",
                matt_login="matt",
            ),
            api,
            clock=lambda: datetime(2026, 7, 24, 12, tzinfo=timezone.utc),
        ).build()
        mission = MissionControlBuilder().build(
            generated_at="2026-07-24T12:00:00Z",
            progress=self.progress(),
            connections={"GitHub": {"state": "connected"}},
            github_work=github,
        )
        brief = ExecutiveBriefService().build(mission, BriefPeriod.MORNING)

        record = archive.store(brief)
        restored, artifact_id = archive.latest_github_snapshot(
            repository="narratiive/narratiive-os"
        )

        self.assertEqual(artifact_id, record.artifact.artifact_id)
        self.assertEqual(restored.workspace_id, "agency")
        self.assertEqual(restored.open_pull_requests[0].number, 1)
        recorded_events = events.read(archive.RUN_ID)
        self.assertEqual(recorded_events[0].event_type, "executive_brief.generated")
        self.assertEqual(
            recorded_events[0].payload["artifact_id"], record.artifact.artifact_id
        )

        changed_api = FakeGitHubAPI(
            pulls=[work_item(1), work_item(2)],
            details={1: pull_detail(1), 2: pull_detail(2)},
        )
        changed = GitHubWorkService(
            GitHubConfig(
                repository="narratiive/narratiive-os",
                workspace_id="agency",
                matt_login="matt",
            ),
            changed_api,
        ).build(previous=restored, baseline_artifact_id=artifact_id)
        self.assertEqual(changed.baseline_artifact_id, record.artifact.artifact_id)
        self.assertEqual(
            [(item.action, item.item.number) for item in changed.changes_since_previous_brief],
            [("opened", 2)],
        )

    def test_corrupt_archived_brief_fails_closed(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        catalog = FileArtifactCatalog(root / "catalog", workspace_id="agency")
        events = JsonlEventLog(root / "events", workspace_id="agency")
        archive = ExecutiveBriefArchive(
            catalog, events, workspace_id="agency"
        )
        record = catalog.register(
            run_id=archive.RUN_ID,
            stage_id=archive.STAGE_ID,
            artifact_type=archive.ARTIFACT_TYPE,
            content='{"github_work":null}',
            extension=".json",
        )
        events.append(
            WorkflowEvent.create(
                event_id="evt-corrupt-brief",
                run_id=archive.RUN_ID,
                event_type="executive_brief.generated",
                payload={
                    "artifact_id": record.artifact.artifact_id,
                    "artifact_version": record.version,
                },
                workspace_id="agency",
            )
        )
        Path(record.artifact.location).write_text("corrupt", encoding="utf-8")

        with self.assertRaisesRegex(GitHubWorkError, "checksum mismatch"):
            archive.latest_github_snapshot(
                repository="narratiive/narratiive-os"
            )

    def test_artifact_without_append_only_event_does_not_advance_baseline(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        catalog = FileArtifactCatalog(root / "catalog", workspace_id="agency")
        events = JsonlEventLog(root / "events", workspace_id="agency")
        archive = ExecutiveBriefArchive(
            catalog, events, workspace_id="agency"
        )
        catalog.register(
            run_id=archive.RUN_ID,
            stage_id=archive.STAGE_ID,
            artifact_type=archive.ARTIFACT_TYPE,
            content='{"github_work":{"repository":"narratiive/narratiive-os"}}',
            extension=".json",
        )

        self.assertIsNone(
            archive.latest_github_snapshot(
                repository="narratiive/narratiive-os"
            )
        )

    def test_foreign_workspace_brief_is_rejected_before_persistence(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        catalog = FileArtifactCatalog(root / "catalog", workspace_id="agency")
        events = JsonlEventLog(root / "events", workspace_id="agency")
        archive = ExecutiveBriefArchive(
            catalog, events, workspace_id="agency"
        )
        api = FakeGitHubAPI(
            pulls=[work_item(1)],
            details={1: pull_detail(1)},
        )
        github = GitHubWorkService(
            GitHubConfig(
                repository="narratiive/narratiive-os",
                workspace_id="agency",
                matt_login="matt",
            ),
            api,
        ).build()
        foreign = replace(github, workspace_id="other-workspace")
        mission = MissionControlBuilder().build(
            generated_at="2026-07-24T12:00:00Z",
            progress=self.progress(),
            connections={"GitHub": {"state": "connected"}},
            github_work=foreign,
        )
        brief = ExecutiveBriefService().build(mission, BriefPeriod.MORNING)

        with self.assertRaisesRegex(GitHubWorkError, "different workspace"):
            archive.store(brief)
        self.assertEqual(catalog.list_all(), [])
        self.assertEqual(events.read(archive.RUN_ID), [])


if __name__ == "__main__":
    unittest.main()
