from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_tony_openclaw_live import EXPECTED_AGENT_IDS, SCENARIOS, build_report
from scripts.pin_tony_openclaw_model import pin_model


class TonyOpenClawModelPinAcceptanceTests(unittest.TestCase):
    def test_explicit_runtime_model_pin_unlocks_full_chief_of_staff_probe(self) -> None:
        base = {"agents": {"list": [{"id": agent_id} for agent_id in EXPECTED_AGENT_IDS]}}
        pinned, target = pin_model(base, "anthropic/claude-sonnet-4-6", "tony")
        self.assertEqual(target, "agents.defaults.model.primary")

        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "openclaw.json"
            config_path.write_text(json.dumps(pinned), encoding="utf-8")
            calls: list[dict[str, object] | None] = []

            def transport(url, body=None, *, headers=None, timeout=0):
                calls.append(body)
                if body is None:
                    return {"models": []}
                text = (
                    "Research completed its delegated inspection and returned evidence."
                    if "Research Agent" in str(body.get("input"))
                    else "Natural Chief of Staff response grounded in current evidence."
                )
                return {"id": f"resp-{len(calls)}", "output_text": text}

            report = build_report(
                config_path=config_path,
                responses_url="http://openclaw/v1/responses",
                agent_id="tony",
                session_key="acceptance-session",
                gateway_token="token",
                ollama_tags_url="http://ollama/api/tags",
                live=True,
                transport=transport,
                agent_inventory=lambda: list(EXPECTED_AGENT_IDS),
            )

        self.assertTrue(report["model_selection_ready"])
        self.assertEqual(report["configured_primary_model"], "anthropic/claude-sonnet-4-6")
        self.assertEqual(report["configured_primary_source"], "agents.defaults.model")
        self.assertTrue(report["runtime_fleet_ready"])
        self.assertTrue(report["live_passed"])
        self.assertEqual(len(report["scenarios"]), len(SCENARIOS))
        self.assertTrue(all("instructions" not in (body or {}) for body in calls if body is not None))


if __name__ == "__main__":
    unittest.main()
