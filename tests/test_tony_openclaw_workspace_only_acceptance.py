from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.check_tony_openclaw_live_authenticated import workspace_only_transport


class TonyOpenClawWorkspaceOnlyAcceptanceTests(unittest.TestCase):
    def test_transport_removes_per_request_behaviour_instructions(self) -> None:
        body = {
            "model": "openclaw/tony",
            "input": "Morning Tony, anything important?",
            "instructions": "duplicate behaviour contract",
            "previous_response_id": "resp-1",
        }
        with patch("scripts.check_tony_openclaw_live_authenticated.http_json") as http_json:
            http_json.return_value = {"id": "resp-2", "output_text": "Morning."}
            result = workspace_only_transport(
                "http://127.0.0.1:18789/v1/responses",
                body,
                headers={"Authorization": "Bearer secret"},
                timeout=120.0,
            )

        self.assertEqual(result["id"], "resp-2")
        sent_body = http_json.call_args.args[1]
        self.assertNotIn("instructions", sent_body)
        self.assertEqual(sent_body["model"], "openclaw/tony")
        self.assertEqual(sent_body["input"], "Morning Tony, anything important?")
        self.assertEqual(sent_body["previous_response_id"], "resp-1")
        self.assertEqual(body["instructions"], "duplicate behaviour contract")

    def test_transport_leaves_inventory_get_unchanged(self) -> None:
        with patch("scripts.check_tony_openclaw_live_authenticated.http_json") as http_json:
            http_json.return_value = {"models": []}
            workspace_only_transport("http://127.0.0.1:11434/api/tags", None, headers={}, timeout=10.0)

        self.assertIsNone(http_json.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
