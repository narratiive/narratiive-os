from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from runtime.artifact_catalog import FileArtifactCatalog
from runtime.command_api import CommandError, RuntimeCommandAPI
from runtime.composition import compose_local_runtime, compose_workspace_runtime
from runtime.engineering_handoff import (
    EngineeringHandoffError,
    EngineeringTask,
    EngineeringTaskService,
)
from runtime.execution_journal import ExecutionJournal
from runtime.workspaces import Workspace


def task_payload(**overrides):
    value = {
        "task_id": "eng-71",
        "workspace_id": "agency",
        "repository": "narratiive/narratiive-os",
        "title": "Engineering Task Pipeline",
        "problem": "Matt manually copies engineering instructions.",
        "scope": ["Create one approved GitHub Issue", "Track the linked PR"],
        "non_goals": ["Do not merge"],
        "acceptance_criteria": ["One approved task creates one Issue"],
        "verification": ["Run the full test suite"],
        "implementation_agent": "Codex",
    }
    value.update(overrides)
    return value


class FakeEngineeringGitHub:
    def __init__(self):
        self.issues = []
        self.timeline = []
        self.pulls = {}
        self.checks = {}
        self.reviews = {}
        self.comments = {}
        self.create_calls = 0
        self.comment_calls = 0
        self.create_error = None
        self.create_delay = 0
        self.comment_error = None

    def find_issues_by_marker(self, marker):
        return [item for item in self.issues if marker in item.get("body", "")]

    def create_issue(self, title, body):
        self.create_calls += 1
        if self.create_delay:
            time.sleep(self.create_delay)
        if self.create_error is not None:
            raise self.create_error
        issue = {
            "number": 71,
            "title": title,
            "body": body,
            "html_url": "https://github.test/issues/71",
            "state": "open",
            "labels": [],
        }
        self.issues.append(issue)
        return dict(issue)

    def get_issue(self, number):
        return next(item for item in self.issues if item["number"] == number)

    def list_issue_timeline(self, number):
        return list(self.timeline)

    def get_pull_request(self, number):
        return dict(self.pulls[number])

    def list_check_runs(self, head_sha):
        return list(self.checks.get(head_sha, []))

    def list_pull_request_reviews(self, number):
        return list(self.reviews.get(number, []))

    def list_issue_comments(self, number):
        return list(self.comments.get(number, []))

    def add_issue_comment(self, number, body):
        self.comment_calls += 1
        if self.comment_error is not None:
            raise self.comment_error
        comment = {"id": self.comment_calls, "body": body}
        self.comments.setdefault(number, []).append(comment)
        return comment


def linked_pull_event(number=72, repository="narratiive/narratiive-os"):
    return {
        "event": "cross-referenced",
        "source": {
            "issue": {
                "number": number,
                "repository": {"full_name": repository},
                "pull_request": {"url": f"https://api.github.test/pulls/{number}"},
            }
        },
    }


def pull(number=72, **overrides):
    value = {
        "number": number,
        "html_url": f"https://github.test/pulls/{number}",
        "state": "open",
        "merged": False,
        "draft": False,
        "mergeable": True,
        "head": {"sha": "abc1234"},
        "labels": [],
    }
    value.update(overrides)
    return value


class EngineeringTaskServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.github = FakeEngineeringGitHub()
        self.journal = ExecutionJournal(root / "journal")
        self.catalog = FileArtifactCatalog(root / "catalog", workspace_id="agency")
        self.service = EngineeringTaskService(
            workspace_id="agency",
            client_id="agency-client",
            repository="narratiive/narratiive-os",
            artifact_catalog=self.catalog,
            execution_journal=self.journal,
            github=self.github,
            required_checks=("runtime-tests",),
            required_reviewers=("matt",),
            allowed_approvers=("matt",),
            clock=lambda: datetime(2026, 7, 24, 21, tzinfo=timezone.utc),
        )
        self.task = EngineeringTask.from_dict(task_payload())

    def approve(self):
        return self.service.approve(
            self.task,
            command_id="approve-71",
            reviewer_id="matt",
            rationale="Sprint 3 scope approved",
        )

    def create(self):
        self.approve()
        return self.service.create_issue("eng-71", command_id="create-71")

    def ready_pull(self):
        self.github.timeline = [linked_pull_event()]
        self.github.pulls[72] = pull()
        self.github.checks["abc1234"] = [
            {
                "name": "runtime-tests",
                "status": "completed",
                "conclusion": "success",
            }
        ]
        self.github.reviews[72] = [
            {
                "user": {"login": "matt"},
                "state": "APPROVED",
                "commit_id": "abc1234",
            }
        ]

    def test_contract_rejects_unknown_fields_and_cross_workspace_tasks(self):
        with self.assertRaisesRegex(EngineeringHandoffError, "unsupported fields"):
            EngineeringTask.from_dict(task_payload(secret="not allowed"))
        foreign = EngineeringTask.from_dict(task_payload(workspace_id="other"))
        with self.assertRaisesRegex(EngineeringHandoffError, "different workspace"):
            self.service.approve(
                foreign,
                command_id="approve-foreign",
                reviewer_id="matt",
                rationale="No",
            )
        self.assertEqual(self.catalog.list_all(), [])
        self.assertEqual(self.journal.read_all(), [])

    def test_approval_is_immutable_artifact_and_hash_chained_audit_record(self):
        approved = self.approve()
        replayed = self.service.approve(
            self.task,
            command_id="approve-71-retry",
            reviewer_id="matt",
            rationale="Sprint 3 scope approved",
        )

        self.assertEqual(replayed.artifact_id, approved.artifact_id)
        self.assertEqual(self.journal.verify()["records"], 1)
        self.assertEqual(self.journal.read_all()[0].state_hash, self.task.digest)
        changed = replace(self.task, problem="Changed after approval")
        with self.assertRaisesRegex(EngineeringHandoffError, "immutable"):
            self.service.approve(
                changed,
                command_id="approve-changed",
                reviewer_id="matt",
                rationale="Changed",
            )

    def test_unapproved_task_never_writes_to_github(self):
        with self.assertRaisesRegex(EngineeringHandoffError, "not approved"):
            self.service.create_issue("eng-71", command_id="create-71")
        self.assertEqual(self.github.create_calls, 0)

    def test_only_allowlisted_reviewer_can_approve(self):
        with self.assertRaisesRegex(EngineeringHandoffError, "not authorized"):
            self.service.approve(
                self.task,
                command_id="approve-unauthorized",
                reviewer_id="someone-else",
                rationale="Attempted approval",
            )
        self.assertEqual(self.catalog.list_all(), [])
        self.assertEqual(self.journal.read_all(), [])

    def test_one_approved_task_creates_one_deterministic_issue(self):
        binding = self.create()
        replayed = self.service.create_issue("eng-71", command_id="create-71-retry")

        self.assertEqual(binding, replayed)
        self.assertEqual(self.github.create_calls, 1)
        issue = self.github.issues[0]
        self.assertEqual(issue["title"], self.task.title)
        self.assertIn(self.task.marker, issue["body"])
        self.assertIn("## Acceptance criteria", issue["body"])
        self.assertIn("Do not merge", issue["body"])
        bound = [
            item
            for item in self.journal.read_all()
            if item.action == "engineering_issue.bound"
        ]
        self.assertEqual(len(bound), 1)

    def test_existing_marker_is_reconciled_without_create(self):
        self.approve()
        self.github.issues.append(
            {
                "number": 99,
                "title": self.task.title,
                "body": self.task.marker,
                "html_url": "https://github.test/issues/99",
                "state": "open",
                "labels": [],
            }
        )
        binding = self.service.create_issue("eng-71", command_id="reconcile-71")
        self.assertEqual(binding.issue_number, 99)
        self.assertEqual(self.github.create_calls, 0)

    def test_concurrent_commands_across_service_instances_create_one_issue(self):
        self.approve()
        self.github.create_delay = 0.02
        second = EngineeringTaskService(
            workspace_id="agency",
            client_id="agency-client",
            repository="narratiive/narratiive-os",
            artifact_catalog=self.catalog,
            execution_journal=ExecutionJournal(self.journal.state_dir),
            github=self.github,
            required_checks=("runtime-tests",),
            required_reviewers=("matt",),
            allowed_approvers=("matt",),
        )
        results = []
        errors = []

        def create(service, command_id):
            try:
                results.append(
                    service.create_issue("eng-71", command_id=command_id)
                )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=create, args=(self.service, "create-a")),
            threading.Thread(target=create, args=(second, "create-b")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(self.github.create_calls, 1)
        self.assertEqual([item.issue_number for item in results], [71, 71])

    def test_duplicate_marker_fails_closed_and_is_audited(self):
        self.approve()
        self.github.issues.extend(
            [
                {
                    "number": number,
                    "body": self.task.marker,
                    "html_url": f"https://github.test/issues/{number}",
                }
                for number in (90, 91)
            ]
        )
        with self.assertRaisesRegex(EngineeringHandoffError, "multiple"):
            self.service.create_issue("eng-71", command_id="create-duplicate")
        self.assertEqual(self.github.create_calls, 0)
        self.assertEqual(self.journal.latest("engineering-task:eng-71").status, "blocked")

    def test_ambiguous_create_failure_requires_reconciliation_before_retry(self):
        self.approve()
        self.github.create_error = TimeoutError("unknown outcome")
        with self.assertRaisesRegex(EngineeringHandoffError, "reconcile"):
            self.service.create_issue("eng-71", command_id="create-timeout")
        self.assertEqual(
            self.journal.latest("engineering-task:eng-71").status,
            "failed",
        )

        self.github.create_error = None
        self.github.issues.append(
            {
                "number": 71,
                "title": self.task.title,
                "body": self.task.marker,
                "html_url": "https://github.test/issues/71",
                "state": "open",
                "labels": [],
            }
        )
        binding = self.service.create_issue("eng-71", command_id="reconcile-timeout")
        self.assertEqual(binding.issue_number, 71)
        self.assertEqual(self.github.create_calls, 1)

    def test_routine_progress_is_suppressed(self):
        self.create()
        first = self.service.refresh("eng-71")
        second = self.service.refresh("eng-71")
        self.assertEqual(first.state, "awaiting_implementation")
        self.assertIsNone(first.notification)
        self.assertIsNone(second.notification)
        self.assertEqual(self.github.comment_calls, 0)

    def test_linked_draft_pr_is_tracked_without_interrupting_matt(self):
        self.create()
        self.github.timeline = [linked_pull_event()]
        self.github.pulls[72] = pull(draft=True)
        snapshot = self.service.refresh("eng-71")
        self.assertEqual(snapshot.state, "implementing")
        self.assertEqual(snapshot.pull_request_number, 72)
        self.assertIsNone(snapshot.notification)

    def test_multiple_linked_open_prs_requires_a_decision_once(self):
        self.create()
        self.github.timeline = [linked_pull_event(72), linked_pull_event(73)]
        self.github.pulls = {72: pull(72), 73: pull(73)}

        first = self.service.refresh("eng-71")
        second = self.service.refresh("eng-71")

        self.assertEqual(first.state, "blocked")
        self.assertEqual(first.notification.kind, "decision")
        self.assertIsNone(second.notification)
        self.assertEqual(self.github.comment_calls, 1)

    def test_readiness_fails_closed_for_pending_checks_and_stale_approval(self):
        self.create()
        self.github.timeline = [linked_pull_event()]
        self.github.pulls[72] = pull()
        self.github.checks["abc1234"] = [
            {"name": "runtime-tests", "status": "in_progress", "conclusion": None}
        ]
        self.github.reviews[72] = [
            {
                "user": {"login": "matt"},
                "state": "APPROVED",
                "commit_id": "old-head",
            }
        ]
        snapshot = self.service.refresh("eng-71")
        self.assertFalse(snapshot.merge_ready)
        self.assertIn("pending_check:runtime-tests", snapshot.blockers)
        self.assertIn("stale_approval:matt", snapshot.blockers)
        self.assertEqual(snapshot.notification.kind, "blocker")

    def test_current_checks_and_approval_report_merge_ready_once_per_head(self):
        self.create()
        self.ready_pull()
        first = self.service.refresh("eng-71")
        second = self.service.refresh("eng-71")
        self.assertTrue(first.merge_ready)
        self.assertEqual(first.notification.kind, "merge_ready")
        self.assertIsNone(second.notification)
        self.assertEqual(self.github.comment_calls, 1)

        self.github.pulls[72]["head"] = {"sha": "def5678"}
        self.github.checks["def5678"] = [
            {
                "name": "runtime-tests",
                "status": "completed",
                "conclusion": "success",
            }
        ]
        self.github.reviews[72].append(
            {
                "user": {"login": "matt"},
                "state": "APPROVED",
                "commit_id": "def5678",
            }
        )
        new_head = self.service.refresh("eng-71")
        self.assertTrue(new_head.merge_ready)
        self.assertEqual(new_head.notification.kind, "merge_ready")
        self.assertEqual(self.github.comment_calls, 2)

    def test_failed_transition_comment_does_not_suppress_a_safe_retry(self):
        self.create()
        self.ready_pull()
        self.github.comment_error = TimeoutError("unknown comment outcome")
        with self.assertRaisesRegex(EngineeringHandoffError, "could not be recorded"):
            self.service.refresh("eng-71")
        self.assertIsNone(self.service.get("eng-71")["snapshot"])

        self.github.comment_error = None
        retried = self.service.refresh("eng-71")
        self.assertEqual(retried.notification.kind, "merge_ready")
        self.assertTrue(retried.merge_ready)

    def test_changes_requested_and_missing_configuration_block_readiness(self):
        self.create()
        self.ready_pull()
        self.github.reviews[72].append(
            {
                "user": {"login": "reviewer"},
                "state": "CHANGES_REQUESTED",
                "commit_id": "abc1234",
            }
        )
        snapshot = self.service.refresh("eng-71")
        self.assertIn("changes_requested:reviewer", snapshot.blockers)

        unconfigured = EngineeringTaskService(
            workspace_id="agency",
            client_id="agency-client",
            repository="narratiive/narratiive-os",
            artifact_catalog=self.catalog,
            execution_journal=self.journal,
            github=self.github,
            allowed_approvers=("matt",),
        )
        snapshot = unconfigured.refresh("eng-71")
        self.assertIn("required_checks_not_configured", snapshot.blockers)
        self.assertIn("required_reviewers_not_configured", snapshot.blockers)

    def test_foreign_pull_cross_reference_is_ignored(self):
        self.create()
        self.github.timeline = [linked_pull_event(repository="other/repository")]
        snapshot = self.service.refresh("eng-71")
        self.assertEqual(snapshot.state, "awaiting_implementation")

    def test_tampered_artifact_and_journal_fail_closed(self):
        approved = self.approve()
        record = self.catalog.get(approved.artifact_id)[0]
        Path(record.artifact.location).write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(EngineeringHandoffError, "checksum"):
            self.service.create_issue("eng-71", command_id="create-tampered")
        self.assertEqual(self.github.create_calls, 0)

        # Corrupt the journal chain after proving artifact tampering is rejected.
        line = json.loads(self.journal.path.read_text(encoding="utf-8"))
        line["rationale"] = "tampered journal"
        self.journal.path.write_text(json.dumps(line) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(EngineeringHandoffError, "integrity"):
            self.service.get("eng-71")

    def test_get_returns_complete_audit_and_latest_snapshot(self):
        binding = self.create()
        self.service.refresh("eng-71")
        result = self.service.get("eng-71")
        self.assertEqual(result["binding"]["issue_number"], binding.issue_number)
        self.assertEqual(result["snapshot"]["state"], "awaiting_implementation")
        self.assertGreaterEqual(len(result["audit"]), 4)

    def test_authenticated_command_boundary_exposes_only_pipeline_commands(self):
        runtime = compose_local_runtime(
            Path(self.temporary.name) / "runtime",
            Path(self.temporary.name),
        )
        runtime.engineering_task_service = self.service
        api = RuntimeCommandAPI(runtime)

        approved = api.handle(
            {
                "command": "engineering_tasks.approve",
                "command_id": "approve-api-71",
                "reviewer_id": "matt",
                "rationale": "Approved through the command gateway",
                "task": self.task.to_dict(),
            }
        )
        created = api.handle(
            {
                "command": "engineering_tasks.create_issue",
                "command_id": "create-api-71",
                "task_id": "eng-71",
            }
        )
        fetched = api.handle(
            {
                "command": "engineering_tasks.get",
                "task_id": "eng-71",
            }
        )

        self.assertEqual(approved["data"]["task_digest"], self.task.digest)
        self.assertEqual(created["data"]["issue_number"], 71)
        self.assertEqual(fetched["data"]["binding"]["issue_number"], 71)

    def test_command_boundary_fails_closed_when_workflow_is_unconfigured(self):
        runtime = compose_local_runtime(
            Path(self.temporary.name) / "runtime-unconfigured",
            Path(self.temporary.name),
        )
        api = RuntimeCommandAPI(runtime)
        with self.assertRaises(CommandError) as captured:
            api.handle(
                {
                    "command": "engineering_tasks.get",
                    "task_id": "eng-71",
                }
            )
        self.assertEqual(captured.exception.code, "engineering_tasks_unavailable")
        self.assertEqual(captured.exception.status, 503)

    def test_environment_configuration_is_restricted_to_one_workspace(self):
        values = {
            "TONY_GITHUB_REPOSITORY": "narratiive/narratiive-os",
            "TONY_GITHUB_WORKSPACE_ID": "agency",
            "TONY_GITHUB_MATT_LOGIN": "matt",
            "TONY_GITHUB_TOKEN": "read-token",
            "TONY_GITHUB_ISSUE_TOKEN": "issue-write-token",
            "TONY_GITHUB_REQUIRED_CHECKS": "runtime-tests",
        }
        with patch.dict("os.environ", values, clear=True):
            configured = compose_workspace_runtime(
                Path(self.temporary.name) / "configured",
                Path(self.temporary.name),
                Workspace("agency", "agency-client", "Agency"),
            )
            foreign = compose_workspace_runtime(
                Path(self.temporary.name) / "foreign",
                Path(self.temporary.name),
                Workspace("other", "other-client", "Other"),
            )
        self.assertIsNotNone(configured.engineering_task_service)
        self.assertIsNone(foreign.engineering_task_service)


if __name__ == "__main__":
    unittest.main()
