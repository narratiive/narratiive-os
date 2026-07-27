from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from openclaw.tony_http_bridge import build_proactive_delivery_status_loader
from runtime.workspaces import WorkspaceRuntimeManager
from scripts import run_proactive_brief

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class _FakeTelegramResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeTelegramResponse":
        return self

    def __exit__(self, *exc_info) -> None:
        return None


class _ProactiveBriefTestEnvironment:
    """Shared workspace/env/Telegram-mock fixture for proactive-brief tests.

    Not a TestCase itself, so unittest does not double-discover its (nonexistent)
    test methods when both concrete TestCase classes below mix it in.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.runtime_root = root / "runtime"
        objects_root = root / "clients"
        objects_root.mkdir(parents=True)

        WorkspaceRuntimeManager(self.runtime_root, REPOSITORY_ROOT).create(
            "test-workspace", "test-client", "Test Workspace"
        )

        self._env = patch.dict(
            os.environ,
            {
                "NARRATIIVE_RUNTIME_ROOT": str(self.runtime_root),
                "TONY_OBJECTS_ROOT": str(objects_root),
                "TONY_EXECUTIVE_WORKSPACE_ID": "test-workspace",
                "TONY_TELEGRAM_BOT_TOKEN": "test-token",
                "TONY_TELEGRAM_CHAT_ID": "12345",
                "NARRATIIVE_GATEWAY_HEALTH_ENDPOINT": "http://127.0.0.1:1/health",
                "NARRATIIVE_DOCTOR_TIMEOUT_SECONDS": "0.2",
            },
            clear=False,
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        self._telegram_patch = patch("openclaw.telegram_outbound.urlopen")
        self.mock_urlopen = self._telegram_patch.start()
        self.mock_urlopen.return_value = _FakeTelegramResponse({"ok": True})
        self.addCleanup(self._telegram_patch.stop)

    def status_state(self) -> str | None:
        loader = build_proactive_delivery_status_loader(
            runtime_root=self.runtime_root, repository_root=REPOSITORY_ROOT
        )
        assert loader is not None
        return loader()["state"]


class RunProactiveBriefTests(_ProactiveBriefTestEnvironment, unittest.TestCase):
    def test_first_run_delivers_brief_and_records_success_evidence(self):
        exit_code = run_proactive_brief.main(["--mode", "brief", "--command", "morning"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.mock_urlopen.call_count, 1)
        self.assertEqual(self.status_state(), "connected")

    def test_repeated_invocation_suppresses_duplicate_delivery(self):
        first = run_proactive_brief.main(["--mode", "brief", "--command", "morning"])
        second = run_proactive_brief.main(["--mode", "brief", "--command", "morning"])

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        # Only the first invocation should have reached Telegram.
        self.assertEqual(self.mock_urlopen.call_count, 1)

    def test_simulated_transport_failure_fails_closed_and_surfaces_evidence(self):
        exit_code = run_proactive_brief.main(
            [
                "--mode",
                "brief",
                "--command",
                "morning",
                "--simulate-transport-failure",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(self.mock_urlopen.call_count, 0)
        self.assertEqual(self.status_state(), "degraded")

    def test_missing_telegram_configuration_fails_closed(self):
        del os.environ["TONY_TELEGRAM_BOT_TOKEN"]

        exit_code = run_proactive_brief.main(["--mode", "brief", "--command", "morning"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(self.mock_urlopen.call_count, 0)
        self.assertEqual(self.status_state(), "degraded")

    def test_missing_workspace_configuration_fails_closed_without_crashing(self):
        del os.environ["TONY_EXECUTIVE_WORKSPACE_ID"]

        exit_code = run_proactive_brief.main(["--mode", "brief", "--command", "morning"])

        self.assertEqual(exit_code, 1)

    def test_escalation_mode_runs_independently_of_brief_mode(self):
        exit_code = run_proactive_brief.main(["--mode", "escalation"])

        # No command is required for escalation-only invocations.
        self.assertIn(exit_code, (0, 1))

    def test_command_is_required_for_brief_mode(self):
        with self.assertRaises(SystemExit):
            run_proactive_brief.main(["--mode", "brief"])


class ConcurrentProactiveBriefTests(_ProactiveBriefTestEnvironment, unittest.TestCase):
    """Proves the workspace lock actually prevents a double send under real
    OS-level contention, not just sequential re-invocation.

    Two threads each independently ``open()`` the same lock file, which
    produces genuine ``fcntl.flock`` contention between distinct open file
    descriptions — the same mechanism that applies across two separate
    scheduler/manual/n8n processes — so this exercises the real lock, not a
    stand-in for it. Ordering between the two attempts is made deterministic
    with events rather than relying on incidental thread-scheduling timing.
    """

    def test_two_concurrent_invocations_result_in_exactly_one_transport_send(self):
        first_call_started = threading.Event()
        release_first_call = threading.Event()

        def blocking_send(request, timeout=None):
            # Simulates an in-flight, slow outbound send: the contending
            # invocation must be attempted *while* this one still holds the
            # workspace lock, not after it has already released it.
            first_call_started.set()
            if not release_first_call.wait(timeout=5):
                raise AssertionError("test did not release the first call in time")
            return _FakeTelegramResponse({"ok": True})

        self.mock_urlopen.side_effect = blocking_send

        results: dict[str, dict] = {}

        def invoke_first():
            results["first"] = run_proactive_brief.run_brief(
                command="morning", simulate_transport_failure=False
            )

        def invoke_second():
            self.assertTrue(
                first_call_started.wait(timeout=5),
                "first invocation never reached the in-flight send",
            )
            results["second"] = run_proactive_brief.run_brief(
                command="morning", simulate_transport_failure=False
            )

        first_thread = threading.Thread(target=invoke_first)
        second_thread = threading.Thread(target=invoke_second)
        first_thread.start()
        second_thread.start()

        # The contending invocation must resolve immediately (non-blocking
        # lock acquisition) without waiting for the first to finish.
        second_thread.join(timeout=5)
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(results["second"]["status"], "already_running")

        release_first_call.set()
        first_thread.join(timeout=5)
        self.assertFalse(first_thread.is_alive())

        self.assertEqual(results["first"]["status"], "delivered")
        self.assertEqual(self.mock_urlopen.call_count, 1)

        # The winner's success is still visible in Mission Control; the
        # loser did not overwrite it with a spurious failure status.
        self.assertEqual(self.status_state(), "connected")


if __name__ == "__main__":
    unittest.main()
