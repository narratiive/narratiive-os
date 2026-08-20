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
    def test_scenarios_lock_full_chief_of_staff_conversation(self) -> None:
        names = [scenario.name for scenario in SCENARIOS]
        self.assertEqual(
            names,
            [
                "natural_priority",
                "typo_tolerance",
                "specialist_delegation",
                "specialist_status",
                "strategy_status",
                "creative_status",
                "production_status",
                "context_followup",
                "contextual_action",
                "context_revision",
                "execution_truth",
            ],
        )
        typo = next(item for item in SCENARIOS if item.name == "typo_tolerance")
        self.assertIn("Whta shoudl", typo.text)
        for name, agent in (
            ("specialist_status", "Research Agent"),
            ("strategy_status", "Strategy Agent"),
            ("creative_status", "Creative Director Agent"),
            ("production_status", "Production Agent"),
        ):
            self.assertIn(agent, next(item for item in SCENARIOS if item.name == name).text)
        self.assertIn("Sort that out", next(item for item in SCENARIOS if item.name == "contextual_action").text)
        self.assertIn("Thursday", next(item for item in SCENARIOS if item.name == "context_revision").text)
        self.assertIn("Did it go", next(item for item in SCENARIOS if item.name == "execution_truth").text)

    def test_extracts_models_without_exposing_unrelated_config(self) -> None:
        config = {
            "models": {"providers": {"ollama": {"models": [{"model": "qwen3.5:latest"}]}}},
            "agents": {"entries": {"tony": {"model": "ollama/qwen3.5:latest"}}},
            "channels": {"telegram": {"token": "secret-value"}},
        }
        self.assertEqual(extract_configured_models(config), ["ollama/qwen3.5:latest", "qwen3.5:latest"])

    def test_extracts_ollama_inventory(self) -> None:
        payload = {"models": [{"name": "qwen3.5:latest"}, {"model": "gemma3:12b"}]}
        self.assertEqual(extract_ollama_models(payload), ["gemma3:12b", "qwen3.5:latest"])

    def test_response_text_supports_openresponses_shapes(self) -> None:
        self.assertEqual(response_text({"output_text": "Ready"}), "Ready")
        payload = {"output": [
            {"content": [{"type": "output_text", "text": "Research is running."}]},
            {"content": [{"type": "output_text", "text": "No blocker."}]},
        ]}
        self.assertEqual(response_text(payload), "Research is running.\nNo blocker.")

    def test_rejects_old_command_parser_failures(self) -> None:
        self.assertTrue(scenario_passes("I checked the current work and research is still running."))
        self.assertFalse(scenario_passes("Unknown command: whta"))
        self.assertFalse(scenario_passes(""))

    def test_live_probe_preserves_one_response_chain_across_all_followups(self) -> None:
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
        for index in range(1, len(calls)):
            self.assertEqual(calls[index][1]["previous_response_id"], f"resp-{index}")
        self.assertEqual(calls[0][2]["x-openclaw-agent-id"], "tony")
        self.assertEqual(calls[0][2]["x-openclaw-session-key"], "acceptance-session")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer token")
        self.assertIn("non-destructive acceptance probe", calls[-1][1]["instructions"])
        self.assertIn("Never invent execution evidence", calls[-1][1]["instructions"])

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
