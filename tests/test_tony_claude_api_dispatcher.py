from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from runtime.tony_claude_api_dispatcher import ClaudeDispatcherConfigError, build_claude_api_dispatcher
from runtime.tony_dispatch_adapters import build_http_dispatchers


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._raw


class TonyClaudeAPIDispatcherTests(unittest.TestCase):
    def _env(self):
        return {
            "TONY_DISPATCH_CLAUDE_MODE": "anthropic_api",
            "ANTHROPIC_API_KEY": "test-key",
            "TONY_DISPATCH_CLAUDE_MODEL": "claude-test-model",
        }

    def _contract(self):
        return {
            "worker": "Claude",
            "execution_mode": "autonomous_prepare",
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "execution_truth": "not_dispatched",
            "instruction": "Prepare a first-pass Growth Blueprint. Do not send anything or change external state.",
            "target": {"area": "commercial", "contact": "Lesley", "company": "Acme"},
        }

    def test_direct_claude_dispatch_is_opt_in_even_when_api_key_exists(self):
        handlers = build_http_dispatchers({"ANTHROPIC_API_KEY": "test-key", "TONY_DISPATCH_CLAUDE_MODEL": "model"})
        self.assertNotIn("Claude", handlers)

    def test_direct_claude_dispatch_requires_explicit_model_and_key(self):
        with self.assertRaises(ClaudeDispatcherConfigError):
            build_http_dispatchers({"TONY_DISPATCH_CLAUDE_MODE": "anthropic_api", "ANTHROPIC_API_KEY": "test-key"})
        with self.assertRaises(ClaudeDispatcherConfigError):
            build_http_dispatchers({"TONY_DISPATCH_CLAUDE_MODE": "anthropic_api", "TONY_DISPATCH_CLAUDE_MODEL": "model"})

    @mock.patch("runtime.tony_claude_api_dispatcher.request.urlopen")
    def test_safe_prepare_calls_anthropic_messages_api_and_returns_structured_evidence(self, urlopen):
        urlopen.return_value = _Response(
            {
                "id": "msg_123",
                "model": "claude-test-model",
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "growth_blueprint": "A substantive evidence-grounded blueprint " + "word " * 50,
                                "sources": ["https://example.com/source"],
                                "evidence_gaps": ["Current pricing is unverified"],
                                "narratiive_fit": "Strong strategic fit",
                                "strategic_growth_opportunity": "Own a clearer national growth position",
                                "recommendation": "advance",
                            }
                        ),
                    }
                ],
            }
        )
        handler = build_http_dispatchers(self._env())["Claude"]
        evidence = handler(self._contract())

        self.assertTrue(evidence["verified"])
        self.assertEqual(evidence["provider"], "anthropic")
        self.assertEqual(evidence["provider_message_id"], "msg_123")
        self.assertEqual(evidence["recommendation"], "advance")
        self.assertIn("growth_blueprint", evidence)

        req = urlopen.call_args.args[0]
        sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(sent["model"], "claude-test-model")
        self.assertEqual(sent["messages"][0]["role"], "user")
        prompt = sent["messages"][0]["content"]
        self.assertIn("Do not send email", prompt)
        self.assertIn("Growth Blueprint", prompt)

    def test_dispatcher_rejects_any_non_prepare_or_unapproved_contract_shape(self):
        handler = build_claude_api_dispatcher(self._env())
        for change in (
            {"execution_mode": "approval_gated_write"},
            {"eligible": False},
            {"state": "approved_pending_execution"},
            {"execution_truth": "verified_dispatch"},
            {"worker": "Gmail"},
        ):
            contract = self._contract()
            contract.update(change)
            with self.assertRaises(RuntimeError):
                handler(contract)

    @mock.patch("runtime.tony_claude_api_dispatcher.request.urlopen")
    def test_plain_text_return_is_preserved_as_internal_work_product(self, urlopen):
        urlopen.return_value = _Response(
            {
                "id": "msg_plain",
                "model": "claude-test-model",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Prepared draft content"}],
            }
        )
        evidence = build_claude_api_dispatcher(self._env())(self._contract())
        self.assertEqual(evidence["work_product"], "Prepared draft content")
        self.assertTrue(evidence["verified"])


if __name__ == "__main__":
    unittest.main()
