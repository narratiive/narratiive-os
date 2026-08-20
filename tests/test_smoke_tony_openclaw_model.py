from __future__ import annotations

import json
import unittest
from unittest import mock

from scripts.smoke_tony_openclaw_model import smoke_model


class TonyOpenClawModelSmokeTests(unittest.TestCase):
    def test_smoke_uses_direct_model_inference_without_agent_tools(self) -> None:
        completed = mock.Mock(returncode=0, stdout=json.dumps({"text": "pong"}), stderr="")
        with mock.patch("scripts.smoke_tony_openclaw_model.subprocess.run", return_value=completed) as run:
            report = smoke_model("anthropic/claude-sonnet-4-6", 45)
        self.assertTrue(report["model_inference_ready"])
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["openclaw", "infer", "model", "run"])
        self.assertIn("anthropic/claude-sonnet-4-6", command)
        self.assertNotIn("agent", command)
        self.assertNotIn("sessions_spawn", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 45)

    def test_smoke_classifies_timeout_as_model_inference(self) -> None:
        with mock.patch(
            "scripts.smoke_tony_openclaw_model.subprocess.run",
            side_effect=__import__("subprocess").TimeoutExpired(["openclaw"], 30),
        ):
            report = smoke_model("ollama/qwen3.5:latest", 30)
        self.assertFalse(report["model_inference_ready"])
        self.assertEqual(report["failure_stage"], "model_inference_timeout")
        self.assertEqual(report["timeout_seconds"], 30)

    def test_smoke_classifies_provider_error_without_exposing_more_than_detail(self) -> None:
        completed = mock.Mock(returncode=1, stdout="", stderr="provider unavailable")
        with mock.patch("scripts.smoke_tony_openclaw_model.subprocess.run", return_value=completed):
            report = smoke_model("ollama/qwen3.5:latest")
        self.assertFalse(report["model_inference_ready"])
        self.assertEqual(report["failure_stage"], "model_inference_error")
        self.assertEqual(report["error"], "provider unavailable")

    def test_smoke_refuses_ambiguous_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit provider/model"):
            smoke_model("qwen3.5:latest")


if __name__ == "__main__":
    unittest.main()
