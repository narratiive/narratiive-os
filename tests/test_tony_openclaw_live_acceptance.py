from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_tony_openclaw_live import (
    EXPECTED_AGENT_IDS,
    SCENARIOS,
    build_report,
    extract_configured_agent_ids,
    extract_configured_models,
    extract_ollama_models,
    extract_runtime_agent_ids,
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

    def test_extracts_configured_agent_ids_from_stable_and_legacy_shapes(self) -> None:
        self.assertEqual(
            extract_configured_agent_ids({"agents": {"list": [{"id": "tony"}, {"id": "research"}]}}),
            ["research", "tony"],
        )
        self.assertEqual(
            extract_configured_agent_ids({"agents": {"entries": {"tony": {}, "strategy": {}}}}),
            ["strategy", "tony"],
        )

    def test_extracts_runtime_agent_ids_from_cli_json(self) -> None:
        payload = [{"id": "tony", "model": "ollama/qwen3.5:latest"}, {"id": "research"}]
        self.assertEqual(extract_runtime_agent_ids(payload), ["research", "tony"])
        self.assertEqual(extract_runtime_agent_ids({"agents": payload}), ["research", "tony"])

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

    def test_rejects_old_command_parser_and_specialist_false_positives(self) -> None:
        self.assertTrue(scenario_passes("I checked the current work and research is still running.", "specialist_status"))
        self.assertFalse(scenario_passes("Unknown command: whta"))
        self.assertFalse(scenario_passes(""))
        self.assertFalse(
            scenario_passes(
                "Nothing's spawned yet — still blocked by the requireAgentId restriction, and currently only `tony` exists.",
                "specialist_delegation",
            )
        )
        self.assertFalse(scenario_passes("No active Research Agent session.", "specialist_status"))
        self.assertFalse(
            scenario_passes(
                "I can spawn one to check its mission. Want me to spawn a Research sub-agent?",
                "specialist_delegation",
            )
        )

    def test_live_probe_preserves_one_response_chain_across_all_followups(self) -> None:
        calls = []

        def transport(url, body=None, *, headers=None, timeout=0):
            calls.append((url, body, dict(headers or {}), timeout))
            index = len(calls)
            text = "Research inspected its mission and is responsible for evidence-backed market intelligence." if index in {3, 4} else f"natural reply {index}"
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
        self.assertNotIn("previous_response_id", calls[0][1])
        for index in range(1, len(calls)):
            self.assertEqual(calls[index][1]["previous_response_id"], f"resp-{index}")
        self.assertEqual(calls[0][2]["x-openclaw-agent-id"], "tony")
        self.assertEqual(calls[0][2]["x-openclaw-session-key"], "acceptance-session")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer token")
        self.assertTrue(all("instructions" not in call[1] for call in calls))
        self.assertTrue(all(set(call[1]).issubset({"model", "input", "previous_response_id"}) for call in calls))

    def test_report_requires_runtime_fleet_not_just_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "openclaw.json"
            config_path.write_text(
                json.dumps({"agents": {"list": [{"id": agent_id} for agent_id in EXPECTED_AGENT_IDS]}}),
                encoding="utf-8",
            )

            def transport(url, body=None, *, headers=None, timeout=0):
                if body is None:
                    return {"models": [{"name": "qwen3.5:latest"}]}
                text = "Research is active and returned its mission." if "Research Agent" in str(body.get("input")) else "Natural response with evidence."
                return {"id": "r-1", "output_text": text}

            report = build_report(
                config_path=config_path,
                responses_url="http://openclaw/v1/responses",
                agent_id="tony",
                session_key="session",
                gateway_token="",
                ollama_tags_url="http://ollama/api/tags",
                live=True,
                transport=transport,
                agent_inventory=lambda: ["tony"],
            )
            self.assertFalse(report["runtime_fleet_ready"])
            self.assertFalse(report["live_passed"])

    def test_report_inventory_and_live_probe_are_decoupled(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "openclaw.json"
            config_path.write_text(
                json.dumps(
                    {
                        "agents": {
                            "defaults": {"model": {"primary": "ollama/qwen3.5:latest"}},
                            "list": [{"id": agent_id} for agent_id in EXPECTED_AGENT_IDS],
                        }
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            def transport(url, body=None, *, headers=None, timeout=0):
                calls.append((url, body))
                if body is None:
                    return {"models": [{"name": "qwen3.5:latest"}]}
                text = "Research completed its read-only mission inspection." if "Research Agent" in str(body.get("input")) else "Natural response with evidence."
                return {"id": f"r-{len(calls)}", "output_text": text}

            inventory = build_report(
                config_path=config_path,
                responses_url="http://openclaw/v1/responses",
                agent_id="tony",
                session_key="session",
                gateway_token="",
                ollama_tags_url="http://ollama/api/tags",
                live=False,
                transport=transport,
                agent_inventory=lambda: list(EXPECTED_AGENT_IDS),
            )
            self.assertTrue(inventory["ollama_reachable"])
            self.assertEqual(inventory["ollama_models"], ["qwen3.5:latest"])
            self.assertTrue(inventory["runtime_fleet_ready"])
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
                agent_inventory=lambda: list(EXPECTED_AGENT_IDS),
            )
            self.assertTrue(live["live_passed"])
            self.assertEqual(len(live["scenarios"]), len(SCENARIOS))


if __name__ == "__main__":
    unittest.main()
