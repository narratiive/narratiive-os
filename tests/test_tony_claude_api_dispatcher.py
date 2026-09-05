from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from runtime.tony_blueprint_lite_inbound import TonyInboundBlueprintLiteService
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

    def _blueprint_lite_contract(self):
        contract = self._contract()
        contract["instruction"] = (
            "Use the completed Growth Diagnostic and verified public sources to prepare a Blueprint Lite for Acme. "
            "Preserve evidence lineage, separate facts, interpretations and hypotheses, and move the result only to human review. "
            "Do not send anything or change external state."
        )
        contract["target"] = {
            "area": "commercial",
            "lead_id": "lead-1",
            "contact": "Lesley",
            "company": "Acme",
            "source": "Growth Diagnostic",
        }
        return contract

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
        self.assertEqual(sent["max_tokens"], 8192)
        self.assertEqual(sent["messages"][0]["role"], "user")
        prompt = sent["messages"][0]["content"]
        self.assertIn("Do not send email", prompt)
        self.assertIn("Growth Blueprint", prompt)

    @mock.patch("runtime.tony_claude_api_dispatcher.request.urlopen")
    def test_blueprint_lite_prepare_receives_canonical_inbound_return_contract(self, urlopen):
        urlopen.return_value = _Response(
            {
                "id": "msg_lite",
                "model": "claude-test-model",
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "blueprint_lite": "A concise outside-in Blueprint Lite",
                                "source_backed_evidence": ["https://example.com/source"],
                                "evidence_gaps": ["Internal customer data is unavailable"],
                                "fact_interpretation_hypothesis_lineage": {
                                    "fact": ["Diagnostic input supplied by prospect"],
                                    "interpretation": ["Positioning appears fragmented"],
                                    "hypothesis": ["A sharper category position may improve choice"],
                                },
                                "growth_tension": "Growth has outpaced message clarity",
                                "provisional_opportunity": "Test a clearer national growth position",
                                "questions_to_answer_next": ["Which customer need most strongly predicts choice?"],
                                "quality_gate": {"human_review_ready": True},
                                "recommendation": "advance",
                            }
                        ),
                    }
                ],
            }
        )

        evidence = build_http_dispatchers(self._env())["Claude"](self._blueprint_lite_contract())
        self.assertTrue(evidence["verified"])
        self.assertIn("blueprint_lite", evidence)

        req = urlopen.call_args.args[0]
        sent = json.loads(req.data.decode("utf-8"))
        prompt = sent["messages"][0]["content"]
        self.assertIn("For Blueprint Lite work", prompt)
        self.assertIn("facts, interpretations and hypotheses", prompt)
        self.assertIn("growth_tension", prompt)
        self.assertIn("provisional_opportunity", prompt)
        self.assertIn("questions_to_answer_next", prompt)
        self.assertIn("human-review-ready", prompt)
        self.assertIn("at the top level", prompt)
        self.assertIn("Do not turn Blueprint Lite into the paid Growth Blueprint", prompt)

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

    @mock.patch("runtime.tony_claude_api_dispatcher.request.urlopen")
    def test_blueprint_lite_json_after_model_preamble_is_parsed(self, urlopen):
        work_product = {
            "blueprint_lite": "A concise synthetic Blueprint Lite",
            "diagnostic_signals_used": ["Synthetic diagnostic signal"],
            "recommendation": "advance",
        }
        urlopen.return_value = _Response(
            {
                "id": "msg_preamble",
                "model": "claude-test-model",
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": "Prepared internal work product:\n" + json.dumps(work_product),
                    }
                ],
            }
        )

        evidence = build_http_dispatchers(self._env())["Claude"](self._blueprint_lite_contract())

        self.assertEqual(evidence["blueprint_lite"], work_product["blueprint_lite"])
        self.assertEqual(evidence["diagnostic_signals_used"], work_product["diagnostic_signals_used"])
        self.assertEqual(evidence["recommendation"], "advance")

    @mock.patch("runtime.tony_claude_api_dispatcher.request.urlopen")
    def test_model_added_work_product_envelope_is_promoted_for_quality_validation(self, urlopen):
        work_product = {
            "blueprint_lite": "A concise synthetic Blueprint Lite",
            "diagnostic_signals_used": ["Synthetic diagnostic signal"],
            "diagnostic_input_coverage": {"complete": True, "missing_inputs": []},
            "source_backed_evidence": ["https://example.invalid/source"],
            "evidence_gaps": ["Private commercial evidence is unavailable"],
            "fact_interpretation_hypothesis_lineage": {
                "fact": ["Synthetic diagnostic input was supplied"],
                "interpretation": ["Synthetic interpretation"],
                "hypothesis": ["Synthetic hypothesis to test"],
            },
            "growth_tension": "Synthetic company-specific tension",
            "provisional_opportunity": "A synthetic opportunity to test",
            "questions_to_answer_next": [
                "Synthetic question one?",
                "Synthetic question two?",
                "Synthetic question three?",
            ],
            "quality_gate": {"human_review_ready": True},
            "recommendation": "advance",
        }
        urlopen.return_value = _Response(
            {
                "id": "msg_wrapped",
                "model": "claude-test-model",
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"work_product": work_product}),
                    }
                ],
            }
        )

        evidence = build_http_dispatchers(self._env())["Claude"](self._blueprint_lite_contract())

        self.assertEqual(evidence["blueprint_lite"], work_product["blueprint_lite"])
        self.assertEqual(evidence["diagnostic_signals_used"], work_product["diagnostic_signals_used"])
        self.assertEqual(evidence["recommendation"], "advance")
        self.assertEqual(evidence["work_product"], work_product)
        self.assertTrue(TonyInboundBlueprintLiteService._quality_gate(evidence)["passed"])

    @mock.patch("runtime.tony_claude_api_dispatcher.request.urlopen")
    def test_truncated_claude_response_fails_before_partial_work_can_reach_quality_gate(self, urlopen):
        urlopen.return_value = _Response(
            {
                "id": "msg_truncated",
                "model": "claude-test-model",
                "stop_reason": "max_tokens",
                "content": [{"type": "text", "text": '{"blueprint_lite":"incomplete'}],
            }
        )

        with self.assertRaisesRegex(RuntimeError, "truncated at the configured max_tokens limit"):
            build_http_dispatchers(self._env())["Claude"](self._blueprint_lite_contract())


if __name__ == "__main__":
    unittest.main()
