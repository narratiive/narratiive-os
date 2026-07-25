from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from runtime.artifact_catalog import FileArtifactCatalog
from runtime.codex_adapter import (
    CodexImplementationAdapter,
    CodexProcessResult,
    CodexTimeoutError,
    EngineeringExecutionPolicy,
    GitWorktreeManager,
    SubprocessCodexRunner,
    VerificationCommand,
)
from runtime.engineering_handoff import EngineeringTask, EngineeringTaskService
from runtime.engineering_orchestrator import (
    EngineeringOrchestrationError,
    EngineeringOrchestrationService,
)
from runtime.execution_journal import ExecutionJournal
from runtime.command_api import RuntimeCommandAPI
from runtime.composition import compose_local_runtime
from runtime.mission_control import MissionControlBuilder
from runtime.mission_control_service import MissionControlService
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationReport


class FakeEngineeringGitHub:
    def __init__(self):
        self.issues = []
        self.create_calls = 0
        self.comment_calls = 0

    def find_issues_by_marker(self, marker):
        return [item for item in self.issues if marker in item["body"]]

    def create_issue(self, title, body):
        self.create_calls += 1
        issue = {
            "number": 81,
            "title": title,
            "body": body,
            "html_url": "https://github.test/issues/81",
            "state": "open",
            "labels": [],
        }
        self.issues.append(issue)
        return issue

    def get_issue(self, number):
        return self.issues[0]

    def list_issue_timeline(self, number):
        return []

    def get_pull_request(self, number):
        raise AssertionError("Pull Request access is not part of Codex dispatch")

    def list_check_runs(self, head_sha):
        return []

    def list_pull_request_reviews(self, number):
        return []

    def list_issue_comments(self, number):
        return []

    def add_issue_comment(self, number, body):
        self.comment_calls += 1
        raise AssertionError("routine Codex dispatch must not write Issue comments")


class FakeCodexRunner:
    def __init__(self, *behaviours):
        self.behaviours = list(behaviours or ("success",))
        self.calls = []

    def run(
        self,
        command,
        *,
        cwd,
        prompt,
        output_path,
        timeout_seconds,
        environment,
    ):
        self.calls.append(
            {
                "command": tuple(command),
                "cwd": Path(cwd),
                "prompt": prompt,
                "timeout_seconds": timeout_seconds,
                "environment": dict(environment),
            }
        )
        behaviour = self.behaviours.pop(0) if self.behaviours else "success"
        if behaviour == "nonzero":
            return CodexProcessResult(1, "temporary output", "provider unavailable", "")
        if behaviour == "timeout":
            raise CodexTimeoutError("partial stdout", "timed out")

        base = self._git(cwd, "rev-parse", "HEAD")
        relative = (
            "docs/forbidden.md"
            if behaviour == "forbidden"
            else "runtime/implemented.py"
        )
        target = Path(cwd) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("IMPLEMENTED = True\n", encoding="utf-8")
        self._git(cwd, "add", relative)
        self._git(cwd, "commit", "-m", "feat: implement approved task")
        head = self._git(cwd, "rev-parse", "HEAD")
        value = {
            "schema_version": 1,
            "task_id": "eng-81",
            "run_id": self._run_id_from_prompt(prompt),
            "status": "completed",
            "base_commit": base,
            "commit": head,
            "changed_files": [relative],
            "tests": ["fixed-verification"],
            "summary": "Implemented the approved task.",
            "blockers": [],
        }
        if behaviour == "contradictory":
            value["commit"] = "deadbeef"
        final_output = (
            "{not-json"
            if behaviour == "malformed"
            else json.dumps(value, sort_keys=True)
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(final_output, encoding="utf-8")
        if behaviour in {"crash", "ambiguous"}:
            if behaviour == "ambiguous":
                output_path.unlink()
            raise SystemExit("simulated process host restart")
        return CodexProcessResult(0, "codex-jsonl", "", final_output)

    @staticmethod
    def _git(cwd, *arguments):
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    @staticmethod
    def _run_id_from_prompt(prompt):
        marker = "completion task_id must be eng-81 and run_id must be "
        return prompt.split(marker, 1)[1].split(".", 1)[0]


class EngineeringOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self._git(self.repository, "init", "-b", "main")
        self._git(self.repository, "config", "user.name", "Test Codex")
        self._git(self.repository, "config", "user.email", "codex@example.test")
        self._git(
            self.repository,
            "remote",
            "add",
            "origin",
            "https://github.com/narratiive/narratiive-os.git",
        )
        (self.repository / "runtime").mkdir()
        (self.repository / "runtime" / "base.py").write_text(
            "BASE = True\n", encoding="utf-8"
        )
        self._git(self.repository, "add", "runtime/base.py")
        self._git(self.repository, "commit", "-m", "initial")

        self.github = FakeEngineeringGitHub()
        self.journal = ExecutionJournal(self.root / "journal")
        self.catalog = FileArtifactCatalog(
            self.root / "catalog",
            workspace_id="agency",
        )
        self.tasks = EngineeringTaskService(
            workspace_id="agency",
            client_id="agency-client",
            repository="narratiive/narratiive-os",
            artifact_catalog=self.catalog,
            execution_journal=self.journal,
            github=self.github,
            required_checks=("runtime-tests",),
            required_reviewers=("matt",),
            allowed_approvers=("matt",),
        )
        self.task = EngineeringTask.from_dict(
            {
                "task_id": "eng-81",
                "workspace_id": "agency",
                "repository": "narratiive/narratiive-os",
                "title": "Durable Codex dispatch",
                "problem": "Approved work still requires manual implementation handoff.",
                "scope": ["Implement isolated local Codex dispatch"],
                "non_goals": ["Do not push", "Do not merge"],
                "acceptance_criteria": ["Create one verified local commit"],
                "verification": ["Use the configured verification profile"],
                "implementation_agent": "Codex",
            }
        )
        self.policy = EngineeringExecutionPolicy(
            version="1",
            repository="narratiive/narratiive-os",
            workspace_id="agency",
            client_id="agency-client",
            base_ref="main",
            allowed_paths=("runtime/**", "tests/**"),
            verification_profile="test-profile",
            verification_commands=(
                VerificationCommand(
                    "fixed-verification",
                    (
                        sys.executable,
                        "-c",
                        "import os; print(os.getenv('GH_TOKEN', 'absent'))",
                    ),
                ),
            ),
            timeout_seconds=5,
            max_attempts=2,
            codex_executable="codex",
        )

    def _git(self, cwd, *arguments):
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def approve(self):
        return self.tasks.approve(
            self.task,
            command_id="approve-81",
            reviewer_id="matt",
            rationale="Sprint 3B increment approved",
        )

    def bind(self):
        self.approve()
        return self.tasks.create_issue("eng-81", command_id="issue-81")

    def service(
        self,
        runner=None,
        *,
        journal=None,
        catalog=None,
        policy=None,
        tasks=None,
    ):
        resolved_journal = journal or self.journal
        worktrees = GitWorktreeManager(
            self.repository,
            self.root / "worktrees",
            verification_environment={
                "PATH": os.environ.get("PATH", ""),
                "GH_TOKEN": "must-not-leak",
            },
        )
        adapter = CodexImplementationAdapter(
            policy=policy or self.policy,
            worktrees=worktrees,
            schema_path=(
                Path(__file__).parents[1]
                / "schemas"
                / "shared"
                / "codex-engineering-result.schema.json"
            ),
            state_dir=self.root / "state",
            runner=runner or FakeCodexRunner(),
            environment={
                "PATH": os.environ.get("PATH", ""),
                "HOME": str(self.root),
                "GH_TOKEN": "must-not-leak",
                "GITHUB_TOKEN": "must-not-leak",
                "UNRELATED_SECRET": "must-not-leak",
            },
        )
        return EngineeringOrchestrationService(
            workspace_id="agency",
            client_id="agency-client",
            repository="narratiive/narratiive-os",
            task_service=tasks or self.tasks,
            execution_journal=resolved_journal,
            artifact_catalog=catalog or self.catalog,
            policy=policy or self.policy,
            adapter=adapter,
            worktrees=worktrees,
        )

    def test_happy_path_records_verified_local_evidence_without_github_write(self):
        self.bind()
        runner = FakeCodexRunner()
        result = self.service(runner).dispatch("eng-81", command_id="dispatch-81")

        self.assertEqual(result.state, "implementation_complete")
        self.assertEqual(result.changed_files, ("runtime/implemented.py",))
        self.assertTrue(result.head_commit)
        self.assertIsNone(result.notification)
        artifact_types = {
            record.artifact.artifact_type for record in self.catalog.list_all()
        }
        self.assertTrue(
            {
                "engineering_execution_package",
                "engineering_codex_prompt",
                "engineering_codex_output",
                "engineering_codex_log",
                "engineering_diff_summary",
                "engineering_verification",
            }.issubset(artifact_types)
        )
        call = runner.calls[0]
        self.assertIn("sandbox_workspace_write.network_access=false", call["command"])
        self.assertNotIn("GH_TOKEN", call["environment"])
        self.assertNotIn("GITHUB_TOKEN", call["environment"])
        self.assertNotIn("UNRELATED_SECRET", call["environment"])
        self.assertEqual(self.github.create_calls, 1)
        self.assertEqual(self.github.comment_calls, 0)
        verification = next(
            record
            for record in self.catalog.list_all()
            if record.artifact.artifact_type == "engineering_verification"
        )
        verification_content = Path(
            verification.artifact.location
        ).read_text(encoding="utf-8")
        self.assertNotIn("must-not-leak", verification_content)
        self.assertFalse(hasattr(self.service(), "merge"))
        self.assertFalse(hasattr(self.service(), "push"))

    def test_missing_approval_and_missing_issue_binding_fail_before_codex(self):
        runner = FakeCodexRunner()
        with self.assertRaisesRegex(
            EngineeringOrchestrationError,
            "not approved",
        ):
            self.service(runner).dispatch("eng-81", command_id="missing-approval")
        self.assertEqual(runner.calls, [])

        self.approve()
        with self.assertRaisesRegex(
            EngineeringOrchestrationError,
            "no canonical GitHub Issue",
        ):
            self.service(runner).dispatch("eng-81", command_id="missing-issue")
        self.assertEqual(runner.calls, [])

    def test_wrong_repository_workspace_or_client_policy_is_rejected(self):
        self.bind()
        for field, value in (
            ("repository", "other/repository"),
            ("workspace_id", "other"),
            ("client_id", "other-client"),
        ):
            values = self.policy.to_dict()
            values[field] = value
            values["verification_commands"] = self.policy.verification_commands
            wrong = EngineeringExecutionPolicy(**values)
            with self.assertRaisesRegex(
                EngineeringOrchestrationError,
                "policy identity",
            ):
                self.service(policy=wrong)

    def test_duplicate_dispatch_replays_one_completed_run(self):
        self.bind()
        runner = FakeCodexRunner()
        service = self.service(runner)
        first = service.dispatch("eng-81", command_id="dispatch-a")
        second = service.dispatch("eng-81", command_id="dispatch-b")
        self.assertEqual(first, second)
        self.assertEqual(len(runner.calls), 1)

    def test_concurrent_dispatch_across_instances_runs_codex_once(self):
        self.bind()
        runner = FakeCodexRunner()
        first = self.service(runner)
        second = self.service(
            runner,
            journal=ExecutionJournal(self.journal.state_dir),
            catalog=FileArtifactCatalog(
                self.catalog.root,
                workspace_id="agency",
            ),
        )
        results = []
        errors = []

        def dispatch(service, command):
            try:
                results.append(
                    service.dispatch("eng-81", command_id=command)
                )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=dispatch, args=(first, "concurrent-a")),
            threading.Thread(target=dispatch, args=(second, "concurrent-b")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(
            [item.state for item in results],
            ["implementation_complete", "implementation_complete"],
        )
        self.assertTrue(self.journal.verify()["ok"])

    def test_timeout_is_retried_only_within_bounded_policy(self):
        self.bind()
        runner = FakeCodexRunner("timeout", "timeout")
        result = self.service(runner).dispatch(
            "eng-81",
            command_id="dispatch-timeout",
        )
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(result.state, "implementation_blocked")
        self.assertIn("retry budget exhausted", result.error)
        self.assertEqual(result.attempt, 2)

    def test_retryable_failure_can_succeed_on_second_attempt(self):
        self.bind()
        runner = FakeCodexRunner("nonzero", "success")
        result = self.service(runner).dispatch(
            "eng-81",
            command_id="dispatch-retry",
        )
        self.assertEqual(result.state, "implementation_complete")
        self.assertEqual(result.attempt, 2)
        self.assertEqual(len(runner.calls), 2)
        states = [
            record.metadata["to_state"]
            for record in self.journal.read_all()
            if record.action == "engineering_orchestration.transition"
        ]
        self.assertIn("failed", states)
        self.assertIn("implementation_queued", states)

    def test_malformed_output_fails_closed(self):
        self.bind()
        result = self.service(FakeCodexRunner("malformed")).dispatch(
            "eng-81",
            command_id="dispatch-malformed",
        )
        self.assertEqual(result.state, "implementation_blocked")
        self.assertIn("malformed", result.error)

    def test_contradictory_output_fails_closed(self):
        self.bind()
        result = self.service(FakeCodexRunner("contradictory")).dispatch(
            "eng-81",
            command_id="dispatch-contradictory",
        )
        self.assertEqual(result.state, "implementation_blocked")
        self.assertIn("contradictory", result.error)

    def test_restart_recovers_committed_work_from_durable_receipt(self):
        self.bind()
        crashing = FakeCodexRunner("crash")
        with self.assertRaises(SystemExit):
            self.service(crashing).dispatch(
                "eng-81",
                command_id="dispatch-crash",
            )
        restarted_runner = FakeCodexRunner()
        recovered = self.service(
            restarted_runner,
            journal=ExecutionJournal(self.journal.state_dir),
            catalog=FileArtifactCatalog(
                self.catalog.root,
                workspace_id="agency",
            ),
        ).recover("eng-81")
        self.assertEqual(recovered.state, "implementation_complete")
        self.assertEqual(restarted_runner.calls, [])

    def test_ambiguous_committed_work_without_receipt_is_blocked(self):
        self.bind()
        with self.assertRaises(SystemExit):
            self.service(FakeCodexRunner("ambiguous")).dispatch(
                "eng-81",
                command_id="dispatch-ambiguous",
            )
        result = self.service(FakeCodexRunner()).recover("eng-81")
        self.assertEqual(result.state, "implementation_blocked")
        self.assertIn("receipt is missing", result.error)

    def test_forbidden_changed_path_is_blocked(self):
        self.bind()
        result = self.service(FakeCodexRunner("forbidden")).dispatch(
            "eng-81",
            command_id="dispatch-forbidden",
        )
        self.assertEqual(result.state, "implementation_blocked")
        self.assertIn("forbidden paths", result.error)

    def test_journal_tampering_prevents_dispatch_and_recovery(self):
        self.bind()
        lines = self.journal.path.read_text(encoding="utf-8").splitlines()
        value = json.loads(lines[0])
        value["rationale"] = "tampered"
        lines[0] = json.dumps(value)
        self.journal.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        runner = FakeCodexRunner()
        with self.assertRaisesRegex(
            EngineeringOrchestrationError,
            "integrity",
        ):
            self.service(runner).dispatch(
                "eng-81",
                command_id="dispatch-tampered",
            )
        self.assertEqual(runner.calls, [])

    def test_routine_transitions_have_no_notification_or_issue_comment(self):
        self.bind()
        service = self.service(FakeCodexRunner())
        result = service.dispatch("eng-81", command_id="dispatch-silent")
        self.assertIsNone(result.notification)
        self.assertTrue(
            all(item.notification is None for item in service.list_runs())
        )
        self.assertEqual(self.github.comment_calls, 0)

    def test_authenticated_command_boundary_dispatches_only_by_task_identity(self):
        self.bind()
        orchestrator = self.service(FakeCodexRunner())
        runtime = compose_local_runtime(
            self.root / "command-runtime",
            self.repository,
        )
        runtime.engineering_task_service = self.tasks
        runtime.engineering_orchestration_service = orchestrator
        response = RuntimeCommandAPI(runtime).handle(
            {
                "command": "engineering_tasks.dispatch",
                "task_id": "eng-81",
                "command_id": "gateway-dispatch-81",
            }
        )
        self.assertTrue(response["ok"])
        self.assertEqual(
            response["data"]["state"],
            "implementation_complete",
        )
        with self.assertRaisesRegex(TypeError, "unexpected keyword"):
            orchestrator.dispatch(
                "eng-81",
                command_id="unsafe",
                prompt="arbitrary",
            )

    def test_mission_control_projects_run_without_routine_notification(self):
        self.bind()
        result = self.service(FakeCodexRunner()).dispatch(
            "eng-81",
            command_id="dispatch-mission",
        )
        progress = ProgressSnapshot(
            status="empty",
            campaigns=(),
            validation=ValidationReport(
                status="pass",
                objects_validated=0,
                errors=(),
                warnings=(),
            ),
        )
        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-25T12:00:00Z",
            progress=progress,
            engineering_runs=(result,),
        )
        response = MissionControlService().respond(snapshot)
        self.assertEqual(
            response.data["engineering_runs"][0]["state"],
            "implementation_complete",
        )
        self.assertEqual(response.data["summary"]["engineering_runs"], 1)
        self.assertNotIn(
            "Engineering decisions:",
            MissionControlService().telegram_reply(snapshot),
        )


class SubprocessCodexRunnerTests(unittest.TestCase):
    def test_timeout_terminates_the_entire_process_group(self):
        process = Mock()
        process.pid = 991
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(("codex", "exec"), 1, "out", "err"),
            ("after-term", "after-term-err"),
        ]
        with patch("runtime.codex_adapter.subprocess.Popen", return_value=process) as popen:
            with patch("runtime.codex_adapter.os.killpg") as killpg:
                with self.assertRaises(CodexTimeoutError):
                    SubprocessCodexRunner().run(
                        ("codex", "exec", "-"),
                        cwd=Path.cwd(),
                        prompt="approved prompt",
                        output_path=Path("unused"),
                        timeout_seconds=1,
                        environment={"PATH": os.environ.get("PATH", "")},
                    )
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        killpg.assert_called_once_with(991, signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
