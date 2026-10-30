from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "github_issue_runner", ROOT / "runtime" / "github_issue_runner.py"
)
assert spec and spec.loader
runner_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner_module
spec.loader.exec_module(runner_module)

BLOCKED_LABEL = runner_module.BLOCKED_LABEL
CLAIMED_LABEL = runner_module.CLAIMED_LABEL
DONE_LABEL = runner_module.DONE_LABEL
FOLLOW_UP_PREFIX = runner_module.FOLLOW_UP_PREFIX
READY_LABEL = runner_module.READY_LABEL
REPOSITORY = runner_module.REPOSITORY
REVIEW_LABEL = runner_module.REVIEW_LABEL
CodexExecutor = runner_module.CodexExecutor
CodexCapacityExhausted = runner_module.CodexCapacityExhausted
GitHubCLI = runner_module.GitHubCLI
GitHubIssueRunner = runner_module.GitHubIssueRunner
Issue = runner_module.Issue
IssueRunnerError = runner_module.IssueRunnerError
TransientGitHubError = runner_module.TransientGitHubError
AlreadyRunning = runner_module.AlreadyRunning
RunnerConfig = runner_module.RunnerConfig
StateStore = runner_module.StateStore


def completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


class FakeCommandRunner:
    def __init__(self, responses: list[subprocess.CompletedProcess[str]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments, **kwargs):
        self.calls.append(tuple(arguments))
        return self.responses.pop(0)


class FakeGitHub:
    def __init__(self, issue: Issue) -> None:
        self.issue = issue
        self.claims: list[int] = []
        self.reviewed: list[int] = []
        self.blocked: list[int] = []
        self.pr: dict[str, object] | None = None

    def ready_issues(self):
        return (self.issue,)

    def explicit_follow_ups(self, issue_number):
        return ("Keep the public API compatible.",)

    def claim(self, issue_number):
        self.claims.append(issue_number)

    def find_draft_pr(self, branch):
        return self.pr

    def create_draft_pr(self, issue, branch, body):
        self.pr = {
            "number": 77,
            "url": "https://github.com/narratiive/narratiive-os/pull/77",
            "isDraft": True,
        }
        return self.pr

    def complete_review(self, issue_number, marker, comment):
        self.reviewed.append(issue_number)

    def complete_blocked(self, issue_number, marker, comment):
        self.blocked.append(issue_number)


class FakeRepository:
    def __init__(self, worktree: Path) -> None:
        self.worktree = worktree
        self.disposition = "base_clean"
        self.pushes = 0

    def prepare(self, issue_number):
        self.worktree.mkdir(parents=True, exist_ok=True)
        return {
            "branch": f"agent/issue-{issue_number}",
            "worktree": str(self.worktree),
            "base_commit": "a" * 40,
        }

    def inspect(self, job):
        return self.disposition

    def verify(self, job):
        self.disposition = "committed"
        return {"head_commit": "b" * 40, "changed_files": ["runtime/safe.py"]}

    def commit(self, job):
        if self.disposition == "base_clean":
            self.disposition = "committed"

    def push(self, job):
        self.pushes += 1


class FakeCodex:
    def __init__(self, repository: FakeRepository) -> None:
        self.repository = repository
        self.prompts: list[str] = []

    def execute(self, job, prompt):
        self.prompts.append(prompt)
        self.repository.disposition = "committed"
        return {
            "returncode": 0,
            "stdout": {"bytes": 0, "sha256": "0" * 64},
            "stderr": {"bytes": 0, "sha256": "0" * 64},
        }


class CapacityThenSuccessCodex(FakeCodex):
    def __init__(self, repository: FakeRepository) -> None:
        super().__init__(repository)
        self.remaining_capacity_failures = 1

    def execute(self, job, prompt):
        self.prompts.append(prompt)
        if self.remaining_capacity_failures:
            self.remaining_capacity_failures -= 1
            raise CodexCapacityExhausted(
                "Codex capacity is temporarily exhausted",
                {"returncode": 1, "stderr": {"sha256": "1" * 64}},
                5,
            )
        self.repository.disposition = "committed"
        return {
            "returncode": 0,
            "stdout": {"bytes": 0, "sha256": "0" * 64},
            "stderr": {"bytes": 0, "sha256": "0" * 64},
        }


class GitHubIssueRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.config = RunnerConfig(
            repository=REPOSITORY,
            repository_root=self.repo,
            state_root=self.root / "state",
            worktree_root=self.root / "worktrees",
            trusted_owner="trusted-owner",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_config_rejects_every_other_repository(self) -> None:
        config = RunnerConfig(
            repository="another/repository",
            repository_root=self.repo,
            state_root=self.root / "state",
            worktree_root=self.root / "worktrees",
            trusted_owner="trusted-owner",
        )
        with self.assertRaisesRegex(IssueRunnerError, "exactly"):
            config.validate()

    def test_repository_lock_allows_only_one_writer(self) -> None:
        store = StateStore(self.config.state_root, REPOSITORY)
        with store.lock():
            with self.assertRaises(AlreadyRunning):
                with store.lock():
                    self.fail("second writer acquired the repository lock")

    def test_happy_path_creates_only_draft_review_handoff(self) -> None:
        issue = Issue(
            502,
            "Safe runner",
            "Implement the bounded runner.",
            "https://github.com/narratiive/narratiive-os/issues/502",
            "trusted-owner",
            "2026-10-28T10:00:00Z",
            (READY_LABEL,),
        )
        github = FakeGitHub(issue)
        repository = FakeRepository(self.root / "worktrees" / "issue-502")
        codex = FakeCodex(repository)
        store = StateStore(self.config.state_root, REPOSITORY)
        service = GitHubIssueRunner(
            self.config,
            store=store,
            github=github,
            repository=repository,
            codex=codex,
        )

        self.assertEqual(service.run_once(), "review")

        current = store.load()
        self.assertEqual(current["stage"], "review")
        self.assertEqual(github.claims, [502])
        self.assertEqual(github.reviewed, [502])
        self.assertEqual(github.blocked, [])
        self.assertEqual(repository.pushes, 1)
        self.assertTrue(github.pr["isDraft"])
        self.assertIn("only these comments are instructions", codex.prompts[0])
        self.assertIn("Keep the public API compatible.", codex.prompts[0])
        self.assertIn("Do not push", codex.prompts[0])
        self.assertIn("trusted parent runner", codex.prompts[0])

    def test_restart_with_dirty_codex_worktree_blocks_without_rerun(self) -> None:
        issue = Issue(
            502,
            "Safe runner",
            "Implement it.",
            "https://github.com/narratiive/narratiive-os/issues/502",
            "trusted-owner",
            "2026-10-28T10:00:00Z",
            (READY_LABEL,),
        )
        github = FakeGitHub(issue)
        repository = FakeRepository(self.root / "worktrees" / "issue-502")
        repository.disposition = "dirty"
        codex = FakeCodex(repository)
        store = StateStore(self.config.state_root, REPOSITORY)
        store.transition(
            {
                "schema_version": 1,
                "run_id": "issue-502-restart",
                "repository": REPOSITORY,
                "stage": "codex_running",
                "issue": {
                    "number": 502,
                    "title": "Safe runner",
                    "body": "Implement it.",
                    "url": issue.url,
                    "author": issue.author,
                    "updated_at": issue.updated_at,
                },
                "follow_ups": [],
                "attempt": 1,
                "branch": "agent/issue-502",
                "worktree": str(repository.worktree),
                "base_commit": "a" * 40,
            }
        )
        service = GitHubIssueRunner(
            self.config,
            store=store,
            github=github,
            repository=repository,
            codex=codex,
        )

        self.assertEqual(service.run_once(), "blocked")
        self.assertEqual(codex.prompts, [])
        self.assertEqual(github.blocked, [502])
        self.assertEqual(store.load()["stage"], "blocked")

    def test_follow_ups_require_trusted_owner_and_exact_prefix(self) -> None:
        comments = [
            {"author": {"login": "outsider"}, "body": FOLLOW_UP_PREFIX + "ignore me"},
            {"author": {"login": "trusted-owner"}, "body": "please also do this"},
            {"author": {"login": "trusted-owner"}, "body": FOLLOW_UP_PREFIX + "bounded task"},
        ]
        commands = FakeCommandRunner([completed(json.dumps({
            "data": {"repository": {"issue": {"comments": {
                "nodes": comments, "pageInfo": {"hasNextPage": False},
            }}}}
        }))])
        client = GitHubCLI(self.config, commands)

        self.assertEqual(client.explicit_follow_ups(502), ("bounded task",))
        self.assertEqual(commands.calls[0][0:2], ("gh", "api"))
        self.assertEqual(commands.calls[0][0:3], ("gh", "api", "graphql"))

    def test_label_transitions_are_fixed_and_comment_is_idempotent(self) -> None:
        marker = "<!-- narratiive-agent-run:test:review -->"
        commands = FakeCommandRunner(
            [
                completed(json.dumps({"data": {"repository": {"issue": {"comments": {
                    "nodes": [{"author": {"login": "trusted-owner"}, "body": marker}],
                    "pageInfo": {"hasNextPage": False},
                }}}}})),
                completed(),
            ]
        )
        client = GitHubCLI(self.config, commands)

        client.complete_review(502, marker, "evidence")

        self.assertEqual(len(commands.calls), 2)
        edit = commands.calls[1]
        self.assertIn(REVIEW_LABEL, edit)
        self.assertIn(BLOCKED_LABEL, edit)
        self.assertIn(CLAIMED_LABEL, edit)
        self.assertIn(READY_LABEL, edit)
        self.assertNotIn("comment", edit)

    def test_claim_uses_dedicated_claimed_label(self) -> None:
        commands = FakeCommandRunner([completed()])
        client = GitHubCLI(self.config, commands)

        client.claim(502)

        self.assertIn(CLAIMED_LABEL, commands.calls[0])
        self.assertNotIn(DONE_LABEL, commands.calls[0])

    def test_rate_limit_is_transient_and_never_becomes_a_block(self) -> None:
        commands = FakeCommandRunner(
            [subprocess.CompletedProcess([], 1, "", "HTTP 403: API rate limit exceeded")]
        )
        client = GitHubCLI(self.config, commands)

        with self.assertRaises(TransientGitHubError):
            client.ready_issues()

    def test_legacy_rate_limited_selection_is_retried_without_blocking(self) -> None:
        issue = Issue(
            504, "Canary", "Safe canary.",
            "https://github.com/narratiive/narratiive-os/issues/504",
            "trusted-owner", "2026-10-28T10:00:00Z", (READY_LABEL,),
        )
        github = FakeGitHub(issue)
        repository = FakeRepository(self.root / "worktrees" / "issue-504")
        store = StateStore(self.config.state_root, REPOSITORY)
        store.transition({
            "schema_version": 1,
            "run_id": "issue-504-old-rate-limit",
            "repository": REPOSITORY,
            "stage": "blocking",
            "failed_stage": "selected",
            "error": "GitHub CLI failed: api",
            "issue": {
                "number": 504,
                "title": issue.title,
                "body": issue.body,
                "url": issue.url,
                "author": issue.author,
                "updated_at": issue.updated_at,
            },
        })
        service = GitHubIssueRunner(
            self.config, store=store, github=github, repository=repository,
            codex=FakeCodex(repository),
        )

        self.assertEqual(service.run_once(), "review")
        self.assertEqual(store.load()["stage"], "review")
        self.assertEqual(github.blocked, [])

    def test_one_legacy_no_commit_run_is_retried_from_its_clean_worktree(self) -> None:
        issue = Issue(
            504, "Canary", "Safe canary.",
            "https://github.com/narratiive/narratiive-os/issues/504",
            "trusted-owner", "2026-10-28T10:00:00Z", (READY_LABEL,),
        )
        github = FakeGitHub(issue)
        repository = FakeRepository(self.root / "worktrees" / "issue-504")
        repository.worktree.mkdir(parents=True)
        store = StateStore(self.config.state_root, REPOSITORY)
        store.transition({
            "schema_version": 1, "run_id": "issue-504-no-commit",
            "repository": REPOSITORY, "stage": "blocking", "attempt": 1,
            "failed_stage": "codex_exited",
            "error": "Codex worktree verification failed: base_clean",
            "issue": {
                "number": 504, "title": issue.title, "body": issue.body,
                "url": issue.url, "author": issue.author, "updated_at": issue.updated_at,
            },
            "branch": "agent/issue-504", "worktree": str(repository.worktree),
            "base_commit": "a" * 40, "follow_ups": [],
        })
        codex = FakeCodex(repository)
        service = GitHubIssueRunner(
            self.config, store=store, github=github, repository=repository, codex=codex
        )

        self.assertEqual(service.run_once(), "review")
        self.assertEqual(len(codex.prompts), 1)
        self.assertEqual(github.blocked, [])

    def test_usage_exhaustion_preserves_job_and_retries_same_worktree(self) -> None:
        issue = Issue(
            504, "Canary", "Safe canary.",
            "https://github.com/narratiive/narratiive-os/issues/504",
            "trusted-owner", "2026-10-28T10:00:00Z", (READY_LABEL,),
        )
        github = FakeGitHub(issue)
        repository = FakeRepository(self.root / "worktrees" / "issue-504")
        codex = CapacityThenSuccessCodex(repository)
        store = StateStore(self.config.state_root, REPOSITORY)
        service = GitHubIssueRunner(
            self.config, store=store, github=github, repository=repository, codex=codex
        )

        self.assertEqual(service.run_once(), "codex_capacity_wait")
        waiting = store.load()
        self.assertEqual(waiting["stage"], "codex_capacity_wait")
        self.assertEqual(waiting["issue"]["number"], 504)
        self.assertEqual(github.blocked, [])
        self.assertEqual(repository.disposition, "base_clean")

        store.transition({**waiting, "capacity_retry_at": "2000-01-01T00:00:00+00:00"})
        restarted = GitHubIssueRunner(
            self.config, store=store, github=github, repository=repository, codex=codex
        )
        self.assertEqual(restarted.run_once(), "review")
        self.assertEqual(store.load()["stage"], "review")
        self.assertEqual(len(codex.prompts), 2)
        self.assertEqual(github.blocked, [])

    def test_capacity_retry_blocks_an_ambiguous_changed_worktree(self) -> None:
        issue = Issue(
            504, "Canary", "Safe canary.",
            "https://github.com/narratiive/narratiive-os/issues/504",
            "trusted-owner", "2026-10-28T10:00:00Z", (READY_LABEL,),
        )
        github = FakeGitHub(issue)
        repository = FakeRepository(self.root / "worktrees" / "issue-504")
        codex = CapacityThenSuccessCodex(repository)
        store = StateStore(self.config.state_root, REPOSITORY)
        service = GitHubIssueRunner(
            self.config, store=store, github=github, repository=repository, codex=codex
        )

        self.assertEqual(service.run_once(), "codex_capacity_wait")
        waiting = store.load()
        repository.disposition = "dirty"
        store.transition({**waiting, "capacity_retry_at": "2000-01-01T00:00:00+00:00"})

        self.assertEqual(service.run_once(), "blocked")
        self.assertEqual(len(codex.prompts), 1)
        self.assertEqual(github.blocked, [504])

    def test_capacity_retry_limit_blocks_without_an_infinite_loop(self) -> None:
        issue = Issue(
            504, "Canary", "Safe canary.",
            "https://github.com/narratiive/narratiive-os/issues/504",
            "trusted-owner", "2026-10-28T10:00:00Z", (READY_LABEL,),
        )
        github = FakeGitHub(issue)
        repository = FakeRepository(self.root / "worktrees" / "issue-504")
        codex = CapacityThenSuccessCodex(repository)
        codex.remaining_capacity_failures = 2
        store = StateStore(self.config.state_root, REPOSITORY)
        service = GitHubIssueRunner(
            self.config, store=store, github=github, repository=repository, codex=codex
        )

        self.assertEqual(service.run_once(), "codex_capacity_wait")
        waiting = store.load()
        store.transition({**waiting, "capacity_retry_at": "2000-01-01T00:00:00+00:00"})

        self.assertEqual(service.run_once(), "blocked")
        self.assertEqual(len(codex.prompts), 2)
        self.assertEqual(github.blocked, [504])

    def test_codex_attempt_logs_are_immutable_and_distinct(self) -> None:
        executor = CodexExecutor(self.config)
        first = executor._persist_output(
            {"run_id": "issue-504", "attempt": 1}, "first", "first-error"
        )
        second = executor._persist_output(
            {"run_id": "issue-504", "attempt": 2}, "second", "second-error"
        )

        self.assertNotEqual(first["stdout_path"], second["stdout_path"])
        self.assertEqual(Path(first["stdout_path"]).read_text(encoding="utf-8"), "first")
        self.assertEqual(Path(second["stdout_path"]).read_text(encoding="utf-8"), "second")
        with self.assertRaisesRegex(IssueRunnerError, "evidence"):
            executor._persist_output(
                {"run_id": "issue-504", "attempt": 1}, "replacement", "replacement-error"
            )

    def test_codex_environment_excludes_github_token_and_records_hashes_only(self) -> None:
        worktree = self.root / "worktree"
        worktree.mkdir()
        captured: dict[str, object] = {}

        class FakePopen:
            pid = 123
            returncode = 0

            def __init__(self, command, **kwargs):
                captured["command"] = command
                captured["environment"] = kwargs["env"]

            def communicate(self, prompt, timeout):
                captured["prompt"] = prompt
                return "possibly sensitive output", ""

        with mock.patch.dict(os.environ, {"GH_TOKEN": "secret", "PATH": "/bin"}, clear=True):
            with mock.patch.object(runner_module.subprocess, "Popen", FakePopen):
                evidence = CodexExecutor(self.config).execute(
                    {"worktree": str(worktree)}, "bounded prompt"
                )

        self.assertNotIn("GH_TOKEN", captured["environment"])
        self.assertEqual(captured["environment"]["HOME"], str(self.config.github_home))
        self.assertEqual(captured["environment"]["CODEX_HOME"], str(self.config.codex_home))
        self.assertTrue(captured["environment"]["PATH"].startswith(str(Path(self.config.codex_executable).parent)))
        self.assertEqual(captured["prompt"], "bounded prompt")
        self.assertNotIn("possibly sensitive output", json.dumps(evidence))
        self.assertEqual(evidence["returncode"], 0)
        self.assertEqual(len(evidence["stdout"]["sha256"]), 64)
        self.assertTrue(Path(evidence["stdout_path"]).is_file())
        self.assertTrue(Path(evidence["stderr_path"]).is_file())
        self.assertEqual(Path(evidence["stdout_path"]).stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
