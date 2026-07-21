from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "service_supervisor.py"
SPEC = importlib.util.spec_from_file_location("service_supervisor", MODULE_PATH)
assert SPEC and SPEC.loader
service_supervisor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = service_supervisor
SPEC.loader.exec_module(service_supervisor)


class RecordingRunner:
    def __init__(self, return_codes: list[int] | None = None, error: Exception | None = None) -> None:
        self.return_codes = list(return_codes or [0])
        self.error = error
        self.calls: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        if self.error:
            raise self.error
        return_code = self.return_codes.pop(0) if self.return_codes else 0
        return SimpleNamespace(returncode=return_code, stdout="", stderr="")


class ServiceSupervisorTests(unittest.TestCase):
    def test_healthy_services_require_no_restart(self) -> None:
        runner = RecordingRunner()
        exit_code, report = service_supervisor.ServiceSupervisor(runner=runner).run(0, {})
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["restarts"], [])
        self.assertEqual(runner.calls, [])

    def test_runtime_only_failure_restarts_runtime_only(self) -> None:
        runner = RecordingRunner()
        commands = {
            "runtime-gateway": ["launchctl", "kickstart", "gui/501/com.narratiive.runtime"],
            "tony-http-bridge": ["launchctl", "kickstart", "gui/501/com.narratiive.tony"],
        }
        exit_code, report = service_supervisor.ServiceSupervisor(runner=runner).run(10, commands)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "restarted")
        self.assertEqual(runner.calls, [commands["runtime-gateway"]])

    def test_bridge_only_failure_restarts_bridge_only(self) -> None:
        runner = RecordingRunner()
        commands = {
            "runtime-gateway": ["restart-runtime"],
            "tony-http-bridge": ["restart-bridge"],
        }
        exit_code, _ = service_supervisor.ServiceSupervisor(runner=runner).run(20, commands)
        self.assertEqual(exit_code, 0)
        self.assertEqual(runner.calls, [["restart-bridge"]])

    def test_combined_failure_restarts_both_in_stable_order(self) -> None:
        runner = RecordingRunner(return_codes=[0, 0])
        commands = {
            "runtime-gateway": ["restart-runtime"],
            "tony-http-bridge": ["restart-bridge"],
        }
        exit_code, report = service_supervisor.ServiceSupervisor(runner=runner).run(30, commands)
        self.assertEqual(exit_code, 0)
        self.assertEqual(runner.calls, [["restart-runtime"], ["restart-bridge"]])
        self.assertTrue(all(item["succeeded"] for item in report["restarts"]))

    def test_missing_restart_command_is_a_recovery_failure(self) -> None:
        exit_code, report = service_supervisor.ServiceSupervisor(runner=RecordingRunner()).run(10, {})
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "recovery_failed")
        self.assertFalse(report["restarts"][0]["attempted"])

    def test_failed_restart_does_not_report_success(self) -> None:
        runner = RecordingRunner(return_codes=[3])
        exit_code, report = service_supervisor.ServiceSupervisor(runner=runner).run(
            20, {"tony-http-bridge": ["restart-bridge"]}
        )
        self.assertEqual(exit_code, 1)
        self.assertFalse(report["ok"])
        self.assertEqual(report["restarts"][0]["return_code"], 3)

    def test_process_error_is_safely_reported(self) -> None:
        runner = RecordingRunner(error=subprocess.TimeoutExpired(["restart"], timeout=2))
        exit_code, report = service_supervisor.ServiceSupervisor(runner=runner).run(
            10, {"runtime-gateway": ["restart"]}
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("restart error", report["restarts"][0]["error"])

    def test_unknown_doctor_code_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported service doctor exit code"):
            service_supervisor.ServiceSupervisor().run(99, {})

    def test_restart_command_env_requires_json_argument_array(self) -> None:
        with mock.patch.dict("os.environ", {"TEST_COMMAND": '["launchctl", "kickstart"]'}):
            self.assertEqual(
                service_supervisor._command_from_env("TEST_COMMAND"),
                ["launchctl", "kickstart"],
            )
        for invalid in ('"launchctl kickstart"', "[]", '["launchctl", ""]'):
            with mock.patch.dict("os.environ", {"TEST_COMMAND": invalid}):
                with self.assertRaises(ValueError):
                    service_supervisor._command_from_env("TEST_COMMAND")

    def test_event_log_is_append_only_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events" / "supervisor.jsonl"
            service_supervisor._append_event(str(path), {"status": "first"})
            service_supervisor._append_event(str(path), {"status": "second"})
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows, [{"status": "first"}, {"status": "second"}])


if __name__ == "__main__":
    unittest.main()
