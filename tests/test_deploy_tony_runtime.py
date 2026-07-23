from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.deploy_tony_runtime import (
    DeploymentError,
    assert_safe_repository,
    deploy,
    restart_services,
    wait_for_health,
)


class FakeRunner:
    def __init__(self, *, dirty: bool = False, current: str = "old", target: str = "new") -> None:
        self.dirty = dirty
        self.current = current
        self.target = target
        self.calls: list[tuple[str, ...]] = []
        self.fail_tests = False

    def __call__(self, command, cwd):
        command = tuple(command)
        self.calls.append(command)
        if command[:3] == ("git", "branch", "--show-current"):
            output = "main\n"
        elif command[:3] == ("git", "status", "--porcelain"):
            output = " M runtime.py\n" if self.dirty else ""
        elif command[:3] == ("git", "rev-parse", "HEAD"):
            output = f"{self.current}\n"
        elif command[:3] == ("git", "rev-parse", "origin/main"):
            output = f"{self.target}\n"
        elif command[:3] == ("git", "merge", "--ff-only"):
            self.current = self.target
            output = ""
        elif command[:3] == ("git", "reset", "--hard"):
            self.current = command[3]
            output = ""
        elif len(command) > 2 and command[1:3] == ("-m", "unittest") and self.fail_tests:
            raise subprocess.CalledProcessError(1, command)
        else:
            output = ""
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")


class DeployTonyRuntimeTests(unittest.TestCase):
    def repository(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / ".git").mkdir()
        self.addCleanup(temporary.cleanup)
        return root

    def test_refuses_dirty_working_tree(self):
        root = self.repository()
        runner = FakeRunner(dirty=True)
        with self.assertRaisesRegex(DeploymentError, "uncommitted changes"):
            assert_safe_repository(root, runner)

    def test_restart_uses_user_launchd_domain(self):
        root = self.repository()
        runner = FakeRunner()
        restarted = restart_services(("com.narratiive.runtime",), runner, cwd=root, uid=501)
        self.assertEqual(restarted, ("com.narratiive.runtime",))
        self.assertIn(
            ("launchctl", "kickstart", "-k", "gui/501/com.narratiive.runtime"),
            runner.calls,
        )

    def test_wait_for_health_retries_transient_failure(self):
        attempts = {"count": 0}

        def checker(endpoint, timeout):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise DeploymentError("not ready")

        wait_for_health(("http://service/health",), checker, attempts=2, interval_seconds=0)
        self.assertEqual(attempts["count"], 2)

    def test_deploy_fast_forwards_tests_restarts_and_checks_health(self):
        root = self.repository()
        runner = FakeRunner(current="old", target="new")
        checked: list[str] = []

        result = deploy(
            root,
            runner=runner,
            checker=lambda endpoint, timeout: checked.append(endpoint),
            labels=("runtime", "bridge"),
            endpoints=("http://runtime/health", "http://bridge/health"),
        )

        self.assertEqual(result.previous_revision, "old")
        self.assertEqual(result.deployed_revision, "new")
        self.assertFalse(result.rolled_back)
        self.assertEqual(set(checked), {"http://runtime/health", "http://bridge/health"})
        self.assertTrue(any(call[:3] == ("git", "merge", "--ff-only") for call in runner.calls))
        self.assertTrue(any(len(call) > 2 and call[1:3] == ("-m", "unittest") for call in runner.calls))

    def test_failed_tests_roll_back_before_reporting_failure(self):
        root = self.repository()
        runner = FakeRunner(current="old", target="new")
        runner.fail_tests = True

        with self.assertRaisesRegex(DeploymentError, "rolled back to old"):
            deploy(
                root,
                runner=runner,
                checker=lambda endpoint, timeout: None,
                labels=("runtime",),
                endpoints=("http://runtime/health",),
            )

        self.assertEqual(runner.current, "old")
        self.assertIn(("git", "reset", "--hard", "old"), runner.calls)


if __name__ == "__main__":
    unittest.main()
