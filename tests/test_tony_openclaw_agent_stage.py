from __future__ import annotations

import unittest

from scripts.probe_tony_openclaw_agent_stage import run_agent_stage_probe


class TonyOpenClawAgentStageTests(unittest.TestCase):
    def test_baseline_failure_stops_before_business_state_turn(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, body, dict(headers or {}), timeout))
            raise RuntimeError("timed out")

        report = run_agent_stage_probe(
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="stage-session",
            gateway_token="secret",
            transport=transport,
        )

        self.assertFalse(report["agent_stage_ready"])
        self.assertEqual(report["failure_stage"], "agent_workspace_or_session")
        self.assertFalse(report["baseline_passed"])
        self.assertEqual(len(calls), 1)
        self.assertNotIn("instructions", calls[0][1])
        self.assertEqual(calls[0][2]["Authorization"], "Bearer secret")

    def test_business_state_timeout_is_classified_after_baseline_succeeds(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, body, dict(headers or {}), timeout))
            if len(calls) == 1:
                return {"id": "resp-1", "output_text": "I am Narratiive's Chief of Staff."}
            raise RuntimeError("timed out")

        report = run_agent_stage_probe(
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="stage-session",
            gateway_token="",
            transport=transport,
        )

        self.assertFalse(report["agent_stage_ready"])
        self.assertEqual(report["failure_stage"], "business_state_or_tool_path")
        self.assertTrue(report["baseline_passed"])
        self.assertFalse(report["business_state_passed"])
        self.assertEqual(calls[1][1]["previous_response_id"], "resp-1")
        self.assertEqual(calls[1][1]["input"], "Morning Tony, anything important?")

    def test_both_stages_use_workspace_owned_natural_language_path(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, body, dict(headers or {}), timeout))
            index = len(calls)
            return {"id": f"resp-{index}", "output_text": f"natural reply {index}"}

        report = run_agent_stage_probe(
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="stage-session",
            gateway_token="token",
            transport=transport,
        )

        self.assertTrue(report["agent_stage_ready"])
        self.assertIsNone(report["failure_stage"])
        self.assertTrue(report["baseline_passed"])
        self.assertTrue(report["business_state_passed"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("instructions" not in call[1] for call in calls))
        self.assertTrue(all(call[1]["model"] == "openclaw/tony" for call in calls))
        self.assertEqual(calls[0][2]["x-openclaw-message-channel"], "telegram")
        self.assertEqual(calls[1][1]["previous_response_id"], "resp-1")


if __name__ == "__main__":
    unittest.main()
