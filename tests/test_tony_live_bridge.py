from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw import tony_live_bridge
from runtime.tony_adaptive_response import TonyAdaptiveResponseCommandService
from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_commercial_watch import TonyCommercialWatchCommandService
from runtime.tony_executive_commands import TonyExecutiveCommandService
from runtime.tony_executive_learning import TonyExecutiveLearningCommandService
from runtime.tony_memory_commands import TonyMemoryCommandService
from runtime.tony_outcome_accountability import TonyOutcomeAccountabilityCommandService
from runtime.tony_outcome_evidence import TonyOutcomeEvidenceCommandService
from runtime.tony_persistent_agency_focus import TonyPersistentAgencyFocusCommandService
from runtime.tony_terminology_commands import TonyTerminologyCommandService
from runtime.tony_verified_execution_status import TonyVerifiedExecutionStatusCommandService


class TonyLiveBridgeTests(unittest.TestCase):
    def test_build_app_composes_terminology_dispatch_memory_focus_commercial_capability_and_executive_commands(self) -> None:
        base_app = mock.Mock()
        base_service = mock.Mock()
        base_app.command_service = base_service
        base_app.bridge_token = ""
        archive = mock.Mock()
        base_app.brief_archive = archive

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            tony_live_bridge, "build_base_app", return_value=base_app
        ), mock.patch.dict(
            "os.environ",
            {
                "TONY_INBOUND_LEADS_PATH": str(Path(tmp) / "leads.json"),
                "TONY_AGENCY_FOCUS_CONTEXT_PATH": str(Path(tmp) / "focus.json"),
                "TONY_EXECUTIVE_OUTCOMES_PATH": str(Path(tmp) / "outcomes.json"),
                "TONY_EXECUTIVE_LEARNING_PATH": str(Path(tmp) / "learning.json"),
            },
            clear=True,
        ):
            app = tony_live_bridge.build_app()

        self.assertIs(app.base, base_app)
        self.assertIsInstance(app.command_service, TonyTerminologyCommandService)
        execution_status = app.command_service.command_service
        self.assertIsInstance(execution_status, TonyVerifiedExecutionStatusCommandService)
        dispatch = execution_status.command_service
        self.assertIsInstance(dispatch, TonyAutonomousDispatchCommandService)
        self.assertEqual(dispatch.dispatchers, {})
        memory = dispatch.command_service
        self.assertIsInstance(memory, TonyMemoryCommandService)
        adaptive = memory.command_service
        self.assertIsInstance(adaptive, TonyAdaptiveResponseCommandService)
        learning = adaptive.command_service
        self.assertIsInstance(learning, TonyExecutiveLearningCommandService)
        outcome_evidence = learning.command_service
        self.assertIsInstance(outcome_evidence, TonyOutcomeEvidenceCommandService)
        outcomes = outcome_evidence.command_service
        self.assertIsInstance(outcomes, TonyOutcomeAccountabilityCommandService)
        focus = outcomes.command_service
        self.assertIsInstance(focus, TonyPersistentAgencyFocusCommandService)
        commercial_watch = focus.command_service
        self.assertIsInstance(commercial_watch, TonyCommercialWatchCommandService)
        capability = commercial_watch.command_service
        self.assertIsInstance(capability, TonyCapabilityCommandService)
        executive = capability.command_service
        self.assertIsInstance(executive, TonyExecutiveCommandService)
        self.assertIs(executive.command_service, base_service)
        self.assertIs(executive.brief_archive, archive)

    def test_build_app_configures_explicit_live_dispatchers(self) -> None:
        base_app = mock.Mock()
        base_app.command_service = mock.Mock()
        base_app.bridge_token = ""
        base_app.brief_archive = mock.Mock()

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            tony_live_bridge, "build_base_app", return_value=base_app
        ), mock.patch.dict(
            "os.environ",
            {
                "TONY_INBOUND_LEADS_PATH": str(Path(tmp) / "leads.json"),
                "TONY_AGENCY_FOCUS_CONTEXT_PATH": str(Path(tmp) / "focus.json"),
                "TONY_EXECUTIVE_OUTCOMES_PATH": str(Path(tmp) / "outcomes.json"),
                "TONY_EXECUTIVE_LEARNING_PATH": str(Path(tmp) / "learning.json"),
                "TONY_DISPATCH_GMAIL_URL": "http://127.0.0.1:9999/gmail/read",
            },
            clear=True,
        ):
            app = tony_live_bridge.build_app()

        execution_status = app.command_service.command_service
        self.assertIsInstance(execution_status, TonyVerifiedExecutionStatusCommandService)
        dispatch = execution_status.command_service
        self.assertIsInstance(dispatch, TonyAutonomousDispatchCommandService)
        self.assertEqual(set(dispatch.dispatchers), {"Gmail"})

    def test_build_app_preserves_mission_control_health_configuration(self) -> None:
        base_app = mock.Mock()
        base_service = mock.Mock()
        loader = mock.Mock()
        base_service.mission_control_loader = loader
        base_app.command_service = base_service
        base_app.bridge_token = ""

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            tony_live_bridge, "build_base_app", return_value=base_app
        ), mock.patch.dict(
            "os.environ",
            {
                "TONY_INBOUND_LEADS_PATH": str(Path(tmp) / "leads.json"),
                "TONY_AGENCY_FOCUS_CONTEXT_PATH": str(Path(tmp) / "focus.json"),
                "TONY_EXECUTIVE_OUTCOMES_PATH": str(Path(tmp) / "outcomes.json"),
                "TONY_EXECUTIVE_LEARNING_PATH": str(Path(tmp) / "learning.json"),
            },
            clear=True,
        ):
            app = tony_live_bridge.build_app()

        self.assertIs(app.command_service.mission_control_loader, loader)

    def test_lead_ingestion_is_authenticated_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_app = mock.Mock()
            base_app.bridge_token = "secret"
            base_app.command_service = mock.Mock()
            base_app.brief_archive = mock.Mock()
            store = tony_live_bridge.FileInboundLeadStore(Path(tmp) / "leads.json")
            app = tony_live_bridge.LeadAwareTonyApplication(base_app, store)
            payload = json.dumps(
                {
                    "lead_id": "lead-1",
                    "contact": "Steve",
                    "company": "Steve Company",
                    "source": "Growth Diagnostic",
                    "status": "New",
                }
            ).encode("utf-8")
            environ = {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/leads/ingest",
                "CONTENT_LENGTH": str(len(payload)),
                "CONTENT_TYPE": "application/json",
                "HTTP_AUTHORIZATION": "Bearer secret",
                "wsgi.input": io.BytesIO(payload),
            }
            status = {}

            response = app(environ, lambda value, headers: status.update(value=value, headers=headers))

            self.assertTrue(status["value"].startswith("200"))
            body = json.loads(b"".join(response).decode("utf-8"))
            self.assertTrue(body["ok"])
            saved = store.read()
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].contact, "Steve")

    def test_build_app_fails_closed_without_command_service(self) -> None:
        base_app = mock.Mock()
        base_app.command_service = None

        with mock.patch.object(tony_live_bridge, "build_base_app", return_value=base_app):
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                tony_live_bridge.build_app()


if __name__ == "__main__":
    unittest.main()
