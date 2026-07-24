from __future__ import annotations

import unittest
from unittest import mock

from openclaw import tony_live_bridge
from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_executive_commands import TonyExecutiveCommandService
from runtime.tony_terminology_commands import TonyTerminologyCommandService


class TonyLiveBridgeTests(unittest.TestCase):
    def test_build_app_composes_terminology_capability_and_executive_commands(self) -> None:
        base_app = mock.Mock()
        base_service = mock.Mock()
        base_app.command_service = base_service

        with mock.patch.object(tony_live_bridge, "build_base_app", return_value=base_app):
            app = tony_live_bridge.build_app()

        self.assertIs(app, base_app)
        self.assertIsInstance(app.command_service, TonyTerminologyCommandService)
        capability = app.command_service.command_service
        self.assertIsInstance(capability, TonyCapabilityCommandService)
        executive = capability.command_service
        self.assertIsInstance(executive, TonyExecutiveCommandService)
        self.assertIs(executive.command_service, base_service)

    def test_build_app_preserves_mission_control_health_configuration(self) -> None:
        base_app = mock.Mock()
        base_service = mock.Mock()
        loader = mock.Mock()
        base_service.mission_control_loader = loader
        base_app.command_service = base_service

        with mock.patch.object(tony_live_bridge, "build_base_app", return_value=base_app):
            app = tony_live_bridge.build_app()

        self.assertIs(app.command_service.mission_control_loader, loader)

    def test_build_app_fails_closed_without_command_service(self) -> None:
        base_app = mock.Mock()
        base_app.command_service = None

        with mock.patch.object(tony_live_bridge, "build_base_app", return_value=base_app):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                tony_live_bridge.build_app()


if __name__ == "__main__":
    unittest.main()
