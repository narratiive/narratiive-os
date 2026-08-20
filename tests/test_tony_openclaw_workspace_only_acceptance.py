from __future__ import annotations

import unittest

from scripts.check_tony_openclaw_live import SCENARIOS, run_live_probe


class TonyOpenClawWorkspaceOnlyAcceptanceTests(unittest.TestCase):
    def test_shared_live_probe_never_injects_behaviour_instructions(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, dict(body or {}), dict(headers or {}), timeout))
            index = len(calls)
            text = (
                "Research inspected its mission and is responsible for evidence-backed market intelligence."
                if index in {3, 4}
                else f"natural reply {index}"
            )
            return {"id": f"resp-{index}", "output_text": text}

        results = run_live_probe(
            responses_url="http://127.0.0.1:18789/v1/responses",
            agent_id="tony",
            session_key="acceptance-session",
            gateway_token="token",
            transport=transport,
        )

        self.assertEqual(len(results), len(SCENARIOS))
        self.assertTrue(all(item["passed"] for item in results))
        self.assertTrue(all("instructions" not in body for _, body, _, _ in calls))
        self.assertEqual(calls[0][1]["model"], "openclaw/tony")
        self.assertEqual(calls[0][1]["input"], "Morning Tony, anything important?")
        self.assertEqual(calls[0][2]["x-openclaw-message-channel"], "telegram")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer token")

    def test_shared_live_probe_preserves_response_chain_without_prompt_shim(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append(dict(body or {}))
            index = len(calls)
            text = (
                "Research completed its read-only mission inspection."
                if index in {3, 4}
                else f"natural reply {index}"
            )
            return {"id": f"resp-{index}", "output_text": text}

        run_live_probe(
            responses_url="http://127.0.0.1:18789/v1/responses",
            agent_id="tony",
            session_key="acceptance-session",
            gateway_token="",
            transport=transport,
        )

        self.assertNotIn("previous_response_id", calls[0])
        for index in range(1, len(calls)):
            self.assertEqual(calls[index]["previous_response_id"], f"resp-{index}")
        self.assertTrue(all(set(body).issubset({"model", "input", "previous_response_id"}) for body in calls))


if __name__ == "__main__":
    unittest.main()
