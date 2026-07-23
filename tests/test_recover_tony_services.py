from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.recover_tony_services import RecoveryError, recover


class FakeDoctor:
    def __init__(self, reports):
        self.reports = list(reports)
        self.calls = []

    def run(self, gateway_endpoint, bridge_endpoint, **kwargs):
        self.calls.append((gateway_endpoint, bridge_endpoint, kwargs))
        if not self.reports:
            raise AssertionError("unexpected doctor call")
        return self.reports.pop(0)


def report(*, gateway=True, bridge=True, deployment=True):
    exit_code = (0 if gateway else 10) + (0 if bridge else 20) + (0 if deployment else 40)
    return exit_code, {
        "ok": exit_code == 0,
        "status": "healthy" if exit_code == 0 else "degraded",
        "exit_code": exit_code,
        "services": [
            {"name": "runtime-gateway", "healthy": gateway},
            {"name": "tony-http-bridge", "healthy": bridge},
        ],
        "deployment": {"name": "deployment-state", "healthy": deployment},
    }


class RecoveryTests(unittest.TestCase):
    def runner(self, calls):
        def run(command, cwd):
            calls.append((tuple(command), cwd))
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return run

    def test_healthy_stack_does_not_restart_services(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            result = recover(root, doctor=FakeDoctor([report()]), runner=self.runner(calls))
            self.assertEqual(result.status, "healthy")
            self.assertEqual(result.restarted_services, ())
            self.assertEqual(calls, [])
            receipt = json.loads((root / "runtime-state/recovery.json").read_text())
            self.assertEqual(receipt["status"], "healthy")

    def test_stale_deployment_is_reported_but_never_auto_deployed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            result = recover(
                root,
                doctor=FakeDoctor([report(deployment=False)]),
                runner=self.runner(calls),
            )
            self.assertEqual(result.status, "deployment_action_required")
            self.assertFalse(result.deployment_healthy)
            self.assertEqual(calls, [])

    def test_restarts_only_failed_gateway(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            doctor = FakeDoctor([report(gateway=False), report()])
            result = recover(root, doctor=doctor, runner=self.runner(calls), sleeper=lambda _: None)
            self.assertEqual(result.status, "recovered")
            self.assertEqual(result.restarted_services, ("com.narratiive.runtime",))
            self.assertEqual(calls[0][0][:3], ("launchctl", "kickstart", "-k"))
            self.assertTrue(calls[0][0][3].endswith("/com.narratiive.runtime"))

    def test_restarts_only_failed_bridge(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            doctor = FakeDoctor([report(bridge=False), report()])
            result = recover(root, doctor=doctor, runner=self.runner(calls), sleeper=lambda _: None)
            self.assertEqual(result.restarted_services, ("com.narratiive.tony-http-bridge",))
            self.assertTrue(calls[0][0][3].endswith("/com.narratiive.tony-http-bridge"))

    def test_recovers_processes_but_preserves_stale_deployment_warning(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            doctor = FakeDoctor([
                report(gateway=False, deployment=False),
                report(deployment=False),
            ])
            result = recover(root, doctor=doctor, runner=self.runner(calls), sleeper=lambda _: None)
            self.assertEqual(result.status, "recovered_deployment_action_required")
            self.assertFalse(result.deployment_healthy)
            self.assertEqual(result.exit_code_after, 40)

    def test_failed_restart_raises_and_writes_failure_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            doctor = FakeDoctor([
                report(gateway=False),
                report(gateway=False),
                report(gateway=False),
            ])
            with self.assertRaises(RecoveryError):
                recover(
                    root,
                    doctor=doctor,
                    runner=self.runner(calls),
                    sleeper=lambda _: None,
                    attempts=2,
                )
            receipt = json.loads((root / "runtime-state/recovery.json").read_text())
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["restarted_services"], ["com.narratiive.runtime"])


if __name__ == "__main__":
    unittest.main()
