from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import run_policy_governed_escalation


class RunPolicyGovernedEscalationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.workspace_runtime = SimpleNamespace(
            paths=SimpleNamespace(root=root),
            workspace=SimpleNamespace(workspace_id="workspace-1"),
            event_log=Mock(),
        )
        self.telegram = SimpleNamespace(
            config=SimpleNamespace(default_chat_id="12345"),
            send=Mock(),
        )
        self.result = SimpleNamespace(to_dict=lambda: {"status": "escalated"})

    def test_cli_composes_policy_governed_service_from_canonical_cooldown_env(self):
        service = Mock()
        service.escalate.return_value = self.result
        mission_control_loader = Mock()

        with patch.dict(
            os.environ,
            {
                "TONY_EXECUTIVE_WORKSPACE_ID": "workspace-1",
                "TONY_PROACTIVE_ESCALATION_MIN_INTERVAL_SECONDS": "900",
                "TONY_PROACTIVE_MAX_ATTEMPTS": "2",
            },
            clear=False,
        ), patch.object(
            run_policy_governed_escalation,
            "build_components",
            return_value=(self.workspace_runtime, Mock(), mission_control_loader),
        ), patch.object(
            run_policy_governed_escalation.TelegramConfig,
            "from_env",
            return_value=self.telegram.config,
        ), patch.object(
            run_policy_governed_escalation,
            "TelegramSender",
            return_value=self.telegram,
        ), patch.object(
            run_policy_governed_escalation,
            "WorkspaceDeliveryLock",
        ), patch.object(
            run_policy_governed_escalation,
            "PolicyGovernedMaterialEscalationService",
            return_value=service,
        ) as service_type:
            result = run_policy_governed_escalation.run()

        self.assertEqual(result, {"status": "escalated"})
        service_type.assert_called_once()
        kwargs = service_type.call_args.kwargs
        self.assertIs(kwargs["mission_control_loader"], mission_control_loader)
        self.assertEqual(kwargs["max_attempts"], 2)
        self.assertEqual(kwargs["interruption_policy"].min_interval_seconds, 900)
        service.escalate.assert_called_once_with(
            workspace_id="workspace-1", chat_id="12345"
        )

    def test_missing_workspace_fails_closed_before_transport_composition(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            run_policy_governed_escalation,
            "build_components",
            side_effect=run_policy_governed_escalation.ProactiveBriefConfigurationError(
                "workspace is required"
            ),
        ), patch.object(run_policy_governed_escalation, "TelegramSender") as sender:
            result = run_policy_governed_escalation.run()

        self.assertEqual(result["status"], "configuration_blocked")
        self.assertIn("workspace is required", result["error"])
        sender.assert_not_called()

    def test_transport_failure_is_reported_without_advancing_success(self):
        service = Mock()
        service.escalate.return_value = SimpleNamespace(
            to_dict=lambda: {"status": "delivery_failed", "attempts": 3}
        )

        with patch.dict(
            os.environ,
            {"TONY_EXECUTIVE_WORKSPACE_ID": "workspace-1"},
            clear=False,
        ), patch.object(
            run_policy_governed_escalation,
            "build_components",
            return_value=(self.workspace_runtime, Mock(), Mock()),
        ), patch.object(
            run_policy_governed_escalation.TelegramConfig,
            "from_env",
            return_value=self.telegram.config,
        ), patch.object(
            run_policy_governed_escalation,
            "TelegramSender",
            return_value=self.telegram,
        ), patch.object(
            run_policy_governed_escalation,
            "WorkspaceDeliveryLock",
        ), patch.object(
            run_policy_governed_escalation,
            "PolicyGovernedMaterialEscalationService",
            return_value=service,
        ):
            result = run_policy_governed_escalation.run(
                simulate_transport_failure=True
            )

        self.assertEqual(result["status"], "delivery_failed")


if __name__ == "__main__":
    unittest.main()
