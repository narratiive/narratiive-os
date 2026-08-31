from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw.tony_live_bridge import LeadAwareTonyApplication
from runtime.inbound_leads import FileInboundLeadStore


class TonyLiveBlueprintLiteIngestTests(unittest.TestCase):
    @staticmethod
    def _environ() -> dict:
        payload = json.dumps(
            {
                "lead_id": "lead-live-1",
                "contact": "Jamie Example",
                "company": "Example Co",
                "source": "Growth Diagnostic",
                "status": "New",
                "Notes": "Completed Growth Diagnostic",
            }
        ).encode("utf-8")
        return {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/leads/ingest",
            "REMOTE_ADDR": "127.0.0.1",
            "CONTENT_LENGTH": str(len(payload)),
            "CONTENT_TYPE": "application/json",
            "HTTP_AUTHORIZATION": "Bearer bridge-secret",
            "wsgi.input": io.BytesIO(payload),
        }

    @staticmethod
    def _call(app: LeadAwareTonyApplication) -> tuple[str, dict]:
        observed: dict[str, object] = {}
        response = app(
            TonyLiveBlueprintLiteIngestTests._environ(),
            lambda status, headers: observed.update(status=status, headers=headers),
        )
        return str(observed["status"]), json.loads(b"".join(response))

    def test_authenticated_lead_ingest_queues_blueprint_lite_without_waiting_for_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = mock.Mock()
            base.bridge_token = "bridge-secret"
            store = FileInboundLeadStore(Path(tmp) / "leads.json")
            preparation = mock.Mock()
            preparation.enqueue_and_start.return_value = {
                "state": "preparation_queued",
                "lead_id": "lead-live-1",
                "approval_required": False,
                "external_action_taken": False,
            }
            app = LeadAwareTonyApplication(
                base,
                store,
                agent_gateway=mock.Mock(),
                blueprint_lite_service=preparation,
            )

            status, payload = self._call(app)

            self.assertTrue(status.startswith("200"))
            self.assertEqual(payload["status"], "lead_ingested")
            self.assertEqual(payload["preparation_status"], "preparation_queued")
            self.assertFalse(payload["preparation"]["external_action_taken"])
            self.assertEqual(len(store.read()), 1)
            preparation.enqueue_and_start.assert_called_once()

    def test_preparation_exception_does_not_erase_successful_lead_ingestion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = mock.Mock()
            base.bridge_token = "bridge-secret"
            store = FileInboundLeadStore(Path(tmp) / "leads.json")
            preparation = mock.Mock()
            preparation.enqueue_and_start.side_effect = RuntimeError("worker unavailable")
            app = LeadAwareTonyApplication(
                base,
                store,
                agent_gateway=mock.Mock(),
                blueprint_lite_service=preparation,
            )

            status, payload = self._call(app)

            self.assertTrue(status.startswith("200"))
            self.assertEqual(payload["status"], "lead_ingested")
            self.assertEqual(payload["preparation_status"], "blocked")
            self.assertEqual(payload["preparation"]["blocker"], "blueprint_lite_orchestration_error")
            self.assertEqual(len(store.read()), 1)


if __name__ == "__main__":
    unittest.main()
