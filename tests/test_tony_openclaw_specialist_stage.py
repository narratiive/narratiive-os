from __future__ import annotations

import unittest

from scripts.probe_tony_openclaw_specialist_stage import run_specialist_stage_probe


class TonyOpenClawSpecialistStageTests(unittest.TestCase):
    def test_context_timeout_stops_before_specialist_delegation(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, body, dict(headers or {}), timeout))
            if len(calls) == 1:
                return {"id": "resp-1", "output_text": "Understood."}
            raise RuntimeError("timed out")

        report = run_specialist_stage_probe(
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="stage-session",
            gateway_token="secret",
            transport=transport,
        )

        self.assertFalse(report["specialist_stage_ready"])
        self.assertEqual(report["failure_stage"], "durable_context")
        self.assertFalse(report["context_passed"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1]["previous_response_id"], "resp-1")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer secret")

    def test_specialist_timeout_is_classified_after_context_succeeds(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, body, dict(headers or {}), timeout))
            if len(calls) == 1:
                return {"id": "resp-1", "output_text": "Understood."}
            if len(calls) == 2:
                return {"id": "resp-2", "output_text": "Cedar"}
            raise RuntimeError("timed out")

        report = run_specialist_stage_probe(
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="stage-session",
            gateway_token="",
            transport=transport,
        )

        self.assertFalse(report["specialist_stage_ready"])
        self.assertEqual(report["failure_stage"], "specialist_delegation")
        self.assertTrue(report["context_passed"])
        self.assertFalse(report["specialist_passed"])
        self.assertEqual(calls[2][1]["previous_response_id"], "resp-2")
        self.assertIn("Research Agent", calls[2][1]["input"])

    def test_context_and_research_delegation_use_openclaw_workspace_path(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, body, dict(headers or {}), timeout))
            replies = ["Understood.", "Cedar", "Research is responsible for market intelligence."]
            return {"id": f"resp-{len(calls)}", "output_text": replies[len(calls) - 1]}

        report = run_specialist_stage_probe(
            responses_url="http://openclaw/v1/responses",
            agent_id="tony",
            session_key="stage-session",
            gateway_token="token",
            transport=transport,
        )

        self.assertTrue(report["specialist_stage_ready"])
        self.assertIsNone(report["failure_stage"])
        self.assertTrue(report["context_passed"])
        self.assertTrue(report["specialist_passed"])
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("instructions" not in call[1] for call in calls))
        self.assertTrue(all(call[1]["model"] == "openclaw/tony" for call in calls))
        self.assertEqual(calls[1][1]["previous_response_id"], "resp-1")
        self.assertEqual(calls[2][1]["previous_response_id"], "resp-2")


if __name__ == "__main__":
    unittest.main()
