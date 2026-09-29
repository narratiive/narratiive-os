from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openclaw.tony_live_bridge import LeadAwareTonyApplication
from runtime.inbound_leads import FileInboundLeadStore


class MediaMonitorBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = mock.Mock()
        base.bridge_token = "bridge-secret"
        self.media = mock.Mock()
        self.media.persist_monitoring_report.return_value = {
            "report_id": "media-daily-test",
            "status": "clear",
            "cadence": "daily",
            "generated_at": "2026-09-29T08:00:00Z",
            "facts": [],
            "exceptions": [],
        }
        self.app = LeadAwareTonyApplication(
            base,
            FileInboundLeadStore(Path(self.temporary.name) / "leads.json"),
            media_control=self.media,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, payload, token="Bearer bridge-secret"):
        raw = json.dumps(payload).encode("utf-8")
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/media/monitor",
            "CONTENT_LENGTH": str(len(raw)),
            "HTTP_AUTHORIZATION": token,
            "wsgi.input": io.BytesIO(raw),
        }
        status = {}
        response = self.app(environ, lambda value, headers: status.update(value=value))
        return status["value"], json.loads(b"".join(response))

    def test_monitor_requires_authentication_and_persists_no_external_action(self):
        denied, _ = self.call({"cadence": "daily", "request_id": "daily-1"}, token="")
        self.assertTrue(denied.startswith("401"))
        status, payload = self.call({"cadence": "daily", "request_id": "daily-1"})
        self.assertTrue(status.startswith("200"))
        self.assertFalse(payload["external_action_taken"])
        self.assertFalse(payload["publication_authorised"])
        self.assertFalse(payload["media_spend_authorised"])
        self.media.persist_monitoring_report.assert_called_once_with(
            cadence="daily", request_id="daily-1", query=""
        )


if __name__ == "__main__":
    unittest.main()
