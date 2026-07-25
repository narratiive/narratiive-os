from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "operational_acceptance.py"
SPEC = importlib.util.spec_from_file_location("operational_acceptance", MODULE_PATH)
assert SPEC and SPEC.loader
operational_acceptance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = operational_acceptance
SPEC.loader.exec_module(operational_acceptance)


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class OperationalAcceptanceTests(unittest.TestCase):
    def test_http_health_requires_200_and_ok_true(self) -> None:
        good = operational_acceptance.check_http(
            "service", "http://service/health", opener=lambda *_args, **_kwargs: FakeResponse({"ok": True})
        )
        bad = operational_acceptance.check_http(
            "service", "http://service/health", opener=lambda *_args, **_kwargs: FakeResponse({"ok": False})
        )
        self.assertTrue(good.ok)
        self.assertFalse(bad.ok)

    def test_tony_roundtrip_posts_authenticated_health_command(self) -> None:
        captured = {}

        def opener(request, **_kwargs):
            captured["method"] = request.get_method()
            captured["authorization"] = request.headers.get("Authorization")
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"ok": True, "command": "health"})

        result = operational_acceptance.check_tony_roundtrip(
            "http://bridge/",
            "bridge-secret",
            "system",
            "system",
            opener=opener,
        )
        self.assertTrue(result.ok)
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["authorization"], "Bearer bridge-secret")
        self.assertEqual(captured["payload"]["action"], "health")
        self.assertNotIn("bridge-secret", result.detail)

    def test_tony_roundtrip_requires_bridge_token(self) -> None:
        result = operational_acceptance.check_tony_roundtrip(
            "http://bridge/", "", "system", "system", opener=lambda *_args, **_kwargs: None
        )
        self.assertFalse(result.ok)
        self.assertIn("not configured", result.detail)

    def test_secret_file_requires_mode_600(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.env"
            path.write_text("TONY_BRIDGE_TOKEN=secret\n", encoding="utf-8")
            path.chmod(0o600)
            self.assertTrue(operational_acceptance.check_secret_file(path).ok)
            path.chmod(0o644)
            result = operational_acceptance.check_secret_file(path)
            self.assertFalse(result.ok)
            self.assertIn("unsafe permissions", result.detail)

    def test_reads_exported_and_quoted_environment_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.env"
            path.write_text(
                "# comment\nexport TONY_BRIDGE_TOKEN='bridge-secret'\nNARRATIIVE_API_KEY=api-secret\n",
                encoding="utf-8",
            )
            values = operational_acceptance.read_env_file(path)
        self.assertEqual(values["TONY_BRIDGE_TOKEN"], "bridge-secret")
        self.assertEqual(values["NARRATIIVE_API_KEY"], "api-secret")

    def test_launch_agent_check_uses_user_domain_on_macos(self) -> None:
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(operational_acceptance.platform, "system", return_value="Darwin"):
            with mock.patch.object(operational_acceptance.os, "getuid", return_value=501):
                result = operational_acceptance.check_launch_agent("com.narratiive.runtime", runner=runner)
        self.assertTrue(result.ok)
        self.assertEqual(calls, [["launchctl", "print", "gui/501/com.narratiive.runtime"]])

    def test_run_checks_returns_nonzero_when_any_required_check_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "runtime.env"
            secret.write_text("TONY_BRIDGE_TOKEN=secret\n", encoding="utf-8")
            secret.chmod(0o600)
            responses = iter(
                [
                    FakeResponse({"ok": True}),
                    FakeResponse({"ok": False}),
                    FakeResponse({"ok": True, "command": "health"}),
                ]
            )
            with mock.patch.object(operational_acceptance.platform, "system", return_value="Linux"):
                exit_code, report = operational_acceptance.run_checks(
                    "http://runtime/health",
                    "http://bridge/health",
                    secret,
                    opener=lambda *_args, **_kwargs: next(responses),
                    bridge_token="secret",
                )
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["status"], "not_ready")

    def test_run_checks_reports_ready_when_all_checks_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "runtime.env"
            secret.write_text("TONY_BRIDGE_TOKEN=secret\n", encoding="utf-8")
            secret.chmod(0o600)

            def opener(request, **_kwargs):
                if hasattr(request, "get_method") and request.get_method() == "POST":
                    return FakeResponse({"ok": True, "command": "health"})
                return FakeResponse({"ok": True, "status": "alive"})

            with mock.patch.object(operational_acceptance.platform, "system", return_value="Linux"):
                exit_code, report = operational_acceptance.run_checks(
                    "http://runtime/health",
                    "http://bridge/health",
                    secret,
                    opener=opener,
                    bridge_token="secret",
                )
        self.assertEqual(exit_code, 0)
        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "ready")
        self.assertTrue(next(item for item in report["checks"] if item["name"] == "tony-roundtrip")["ok"])


if __name__ == "__main__":
    unittest.main()
