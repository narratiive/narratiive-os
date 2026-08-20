from __future__ import annotations

import unittest

from scripts.diagnose_tony_openclaw_model import configured_primary


class TonyOpenClawModelDiagnosticsTests(unittest.TestCase):
    def test_tony_explicit_model_wins_over_defaults(self) -> None:
        config = {
            "agents": {
                "defaults": {"model": {"primary": "openai/gpt-5.6-sol"}},
                "list": [
                    {"id": "research"},
                    {"id": "tony", "model": {"primary": "ollama/qwen3.5:latest"}},
                ],
            }
        }
        self.assertEqual(
            configured_primary(config),
            ("ollama/qwen3.5:latest", "agents.list[tony].model"),
        )

    def test_shared_default_is_reported_when_tony_has_no_override(self) -> None:
        config = {
            "agents": {
                "defaults": {"model": {"primary": "anthropic/claude-sonnet-5"}},
                "list": [{"id": "tony"}],
            }
        }
        self.assertEqual(
            configured_primary(config),
            ("anthropic/claude-sonnet-5", "agents.defaults.model"),
        )

    def test_unset_model_fails_closed_instead_of_guessing_ollama(self) -> None:
        config = {"agents": {"list": [{"id": "tony"}]}}
        self.assertEqual(configured_primary(config), ("", "unset"))

    def test_legacy_entries_shape_remains_diagnostic_only(self) -> None:
        config = {"agents": {"entries": {"tony": {"model": "openai/gpt-5.6-sol"}}}}
        self.assertEqual(
            configured_primary(config),
            ("openai/gpt-5.6-sol", "agents.entries.tony.model"),
        )


if __name__ == "__main__":
    unittest.main()
