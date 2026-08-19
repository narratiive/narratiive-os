from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_tony_openclaw_live import (
    SCENARIOS,
    build_report,
    extract_configured_models,
    extract_ollama_models,
    response_text,
    run_live_probe,
    scenario_passes,
)


class TonyOpenClawLiveAcceptanceTests(unittest.TestCase):
    def test_scenarios_lock_natural_language_typo_and_specialist_followups(self) -> None:
        names = [scenario.name for scenario in SCENARIOS]
        self.assertEqual(
            names,
            [
                "natural_priority",
                "typo_tolerance",
                "specialist_delegation",
                "specialist_status",
                "context_followup",
            ],
        )
        typo = next(item for item in SCENARIOS if item.name == "typo_tolerance")
        self.assertIn("Whta shoudl", typo.text)
        status = next(item for item in SCENARIOS if item.name == "specialist_status")
        self.assertIn("Research Agent", status.text)

    def test_extracts_models_without_exposing_unrelated_config(self) -> None:
        config = {
            "models": {"providers": {"ollama": {"models": [{"model": "qwen3.5:latest"}]}}},
            "agents": {"entries": {"tony": {"model": "ollama/qwen3.5:latest"}}},
            "channels": {"telegram": {"token": "secret-value"}},
        }
        self.assertEqual(
            extract_configured_models(config),
            ["ollama/qwen3.5:latest", "qwen3.5:latest"],
        )

    def test_extracts_ollama_inventory(self) -> None:
        payload = {"models": [{"name": "qwen3.5:latest"}, {"model": "gemma3:12b"}]}
        self.assertEqual(extract_ollama_models(payload), ["gemma3:12b", "qwen3.5:latest"])

    def test_response_text_supports_openresponses_shapes(self) -> None:
        self.assertEqual(response_text({"output_text": "Ready"}), "Ready")
        payload = {
            "output": [
                {"content": [{"type": "output_text", "text": "Research is running."}]},
                {"content": [{"type": "output_text", "text": "No blocker."}]},
            ]
        }
        self.assertEqual(response_text(payload), "Research is running.\nNo blocker.")

    def test_rejects_old_command_parser_failures(self) -> None:
        self.assertTrue(scenario_passes("I checked the current work and research is still running."))
        self.assertFalse(scenario_passes("Unknown command: whta"))
        self.assertFalse(scenario_passes(""))

    def test_live_probe_preserves_one_response_chain_across_followups(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, body, dict(headers or {}), timeout))
            index = len(calls)
            return {"id": f"resp-{index}", "output_text": f"natural reply {index}"}

        results = run_live_probe(
            responses_url="http://127.0.0.1:18789/v1/responses",
            agent_id="tony",
            session_key="acceptance-session",
            gateway_token="token",
            transport=transport,
        )

        self.assertEqual(len(results), len(SCENARIOS))
        self.assertTrue(all(item["passed"] for item in results))
        self.assertNotIn("previous_response_id", calls[0][1])
        self.assertEqual(calls[1][1]["previous_response_id"], "resp-1")
        self.assertEqual(calls[-1][1]["previous_response_id"], f"resp-{len(SCENARIOS) - 1}")
        self.assertEqual(calls[0][2]["x-openclaw-agent-id"], "tony")
        self.assertEqual(calls[0][2]["x-openclaw-session-key"], "acceptance-session")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer token")

    def test_report_inventory_and_live_probe_are_decoupled(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "openclaw.json"
            config_path.write_text(json.dumps({"agent": {"model": "ollama/qwen3.5:latest"}}), encoding="utf-8")
            calls = []

            def transport(url, body=None, *, headers=None, timeout=0):
                calls.append((url, body))
                if body is None:
                    return {"models": [{"name": "qwen3.5:latest"}]}
                return {"id": f"r-{len(calls)}", "output_text": "Natural response with evidence."}

            inventory = build_report(
                config_path=config_path,
                responses_url="http://openclaw/v1/responses",
                agent_id="tony",
                session_key="session",
                gateway_token="",
                ollama_tags_url="http://ollama/api/tags",
                live=False,
                transport=transport,
            )
            self.assertTrue(inventory["ollama_reachable"])
            self.assertEqual(inventory["ollama_models"], ["qwen3.5:latest"])
            self.assertNotIn("scenarios", inventory)

            live = build_report(
                config_path=config_path,
                responses_url="http://openclaw/v1/responses",
                agent_id="tony",
                session_key="session",
                gateway_token="",
                ollama_tags_url="http://ollama/api/tags",
                live=True,
                transport=transport,
            )
            self.assertTrue(live["live_passed"])
            self.assertEqual(len(live["scenarios"]), len(SCENARIOS))


if __name__ == "__main__":
    unittest.main()
