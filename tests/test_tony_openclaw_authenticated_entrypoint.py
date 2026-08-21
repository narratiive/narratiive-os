from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

from scripts.check_tony_openclaw_live_authenticated import (
    diagnose_timeout_boundary,
    refine_agent_timeout_boundary,
)


class TonyAuthenticatedEntrypointTests(unittest.TestCase):
    def test_entrypoint_uses_shared_gateway_auth_resolver_without_printing_secret(self):
        path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_tony_openclaw_live_authenticated.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("resolve_gateway_bearer", source)
        self.assertIn('report["gateway_auth_present"]', source)
        self.assertIn('report["gateway_auth_source"]', source)
        self.assertNotIn('report["gateway_token"]', source)
        self.assertNotIn('report["gateway_password"]', source)

    def test_entrypoint_can_be_invoked_directly_from_outside_repo(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        script = root / "scripts" / "check_tony_openclaw_live_authenticated.py"
        with tempfile.TemporaryDirectory() as cwd:
            completed = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Run Tony's live OpenClaw acceptance probe", completed.stdout)
        self.assertNotIn("ModuleNotFoundError", completed.stderr)

    def test_agent_timeout_with_healthy_raw_model_is_classified_after_model_boundary(self):
        report = {
            "live_passed": False,
            "model_selection_ready": True,
            "live_error": "timed out",
        }
        calls: list[tuple[str, int]] = []

        def resolver(agent_id: str) -> tuple[str, str]:
            self.assertEqual(agent_id, "tony")
            return "ollama/qwen3.5:latest", "runtime:tony"

        def smoke(model_ref: str, timeout_seconds: int):
            calls.append((model_ref, timeout_seconds))
            return {
                "model": model_ref,
                "model_inference_ready": True,
                "failure_stage": None,
                "elapsed_seconds": 4.2,
                "response_json_valid": True,
                "error": "must not leak",
            }

        diagnose_timeout_boundary(
            report,
            "tony",
            timeout_seconds=45,
            resolver=resolver,
            smoke=smoke,
        )
        self.assertEqual(calls, [("ollama/qwen3.5:latest", 45)])
        self.assertEqual(report["failure_boundary"], "agent_tool_session")
        self.assertTrue(report["model_smoke"]["model_inference_ready"])
        self.assertNotIn("error", report["model_smoke"])

    def test_healthy_model_but_baseline_agent_failure_is_narrowed_to_workspace_session(self):
        report = {"failure_boundary": "agent_tool_session"}

        def stage_probe(**kwargs):
            self.assertEqual(kwargs["agent_id"], "tony")
            self.assertTrue(kwargs["session_key"].endswith(":stage"))
            return {
                "agent_stage_ready": False,
                "failure_stage": "agent_workspace_or_session",
                "baseline_passed": False,
                "business_state_passed": False,
                "baseline_error": "must not leak",
            }

        refine_agent_timeout_boundary(
            report,
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="acceptance",
            gateway_token="secret",
            stage_probe=stage_probe,
        )
        self.assertEqual(report["failure_boundary"], "agent_workspace_or_session")
        self.assertFalse(report["agent_stage_probe"]["baseline_passed"])
        self.assertNotIn("baseline_error", report["agent_stage_probe"])

    def test_healthy_baseline_but_business_state_failure_is_narrowed_to_tool_path(self):
        report = {"failure_boundary": "agent_tool_session"}

        refine_agent_timeout_boundary(
            report,
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="acceptance",
            gateway_token="",
            stage_probe=lambda **kwargs: {
                "agent_stage_ready": False,
                "failure_stage": "business_state_or_tool_path",
                "baseline_passed": True,
                "business_state_passed": False,
            },
        )
        self.assertEqual(report["failure_boundary"], "business_state_or_tool_path")
        self.assertTrue(report["agent_stage_probe"]["baseline_passed"])

    def test_healthy_two_stage_agent_probe_moves_boundary_to_later_acceptance(self):
        report = {"failure_boundary": "agent_tool_session"}

        refine_agent_timeout_boundary(
            report,
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="acceptance",
            gateway_token="",
            stage_probe=lambda **kwargs: {
                "agent_stage_ready": True,
                "failure_stage": None,
                "baseline_passed": True,
                "business_state_passed": True,
            },
        )
        self.assertEqual(report["failure_boundary"], "later_acceptance_or_specialist_path")
        self.assertTrue(report["agent_stage_probe"]["business_state_passed"])

    def test_agent_timeout_with_failed_raw_model_is_classified_as_provider_boundary(self):
        report = {
            "live_passed": False,
            "model_selection_ready": True,
            "live_error": "request timeout",
        }

        diagnose_timeout_boundary(
            report,
            "tony",
            resolver=lambda agent_id: ("anthropic/claude-sonnet-4-6", "runtime:tony"),
            smoke=lambda model_ref, timeout_seconds: {
                "model": model_ref,
                "model_inference_ready": False,
                "failure_stage": "model_inference_timeout",
                "timeout_seconds": timeout_seconds,
            },
        )
        self.assertEqual(report["failure_boundary"], "model_provider")
        self.assertEqual(report["model_smoke"]["failure_stage"], "model_inference_timeout")

    def test_non_timeout_failure_does_not_run_model_smoke(self):
        report = {
            "live_passed": False,
            "model_selection_ready": True,
            "live_error": "HTTP 401: Unauthorized",
        }

        def unexpected_resolver(agent_id: str):
            raise AssertionError("resolver should not run for non-timeout failures")

        diagnose_timeout_boundary(report, "tony", resolver=unexpected_resolver)
        self.assertNotIn("failure_boundary", report)
        self.assertNotIn("model_smoke", report)


if __name__ == "__main__":
    unittest.main()
