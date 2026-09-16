from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.inbound_leads import FileInboundLeadStore, InboundLead
from runtime.proactive_executive_delivery import FileDeliveryKeyStore
from scripts.accept_attention_suppression import (
    AttentionAcceptanceError,
    accept_attention_suppression,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class AttentionSuppressionAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.lead_path = self.root / "leads.json"
        FileInboundLeadStore(self.lead_path).replace(
            [
                InboundLead("visible", "Sam", company="Live Co"),
                InboundLead(
                    "hidden",
                    "Test",
                    company="SAFE fixture",
                    disposition="suppressed",
                ),
            ]
        )
        self.now = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)
        FileDeliveryKeyStore(
            self.root / "workspaces/agency/proactive-delivery/brief-delivery-keys.json"
        ).add("agency:morning:2026-09-16")

    def tearDown(self):
        self.temporary.cleanup()

    def opener(self, probe, **kwargs):
        command = json.loads(probe.data.decode("utf-8"))["text"]
        if command == "/morning":
            return FakeResponse(
                {
                    "ok": True,
                    "status": "healthy",
                    "data": {
                        "inbound_leads_loaded": 1,
                        "agency_state": {
                            "executive_items": [{"item_id": "lead-visible"}]
                        },
                    },
                }
            )
        return FakeResponse(
            {
                "ok": True,
                "status": "healthy",
                "data": {"leads": [{"lead_id": "visible"}]},
            }
        )

    def accept(self, **overrides):
        arguments = {
            "lead_path": self.lead_path,
            "runtime_root": self.root,
            "workspace_id": "agency",
            "bridge_url": "http://bridge/",
            "bridge_token": "secret",
            "deployment": {"status": "deployed", "deployed_revision": "safe-revision"},
            "receipt_path": self.root / "receipt.json",
            "opener": self.opener,
            "brief_runner": lambda **kwargs: {
                "status": "duplicate_suppressed",
                "attempts": 0,
            },
            "now": self.now,
        }
        arguments.update(overrides)
        return accept_attention_suppression(**arguments)

    def test_records_revision_bound_live_filter_and_duplicate_evidence(self):
        receipt = self.accept()

        self.assertEqual(receipt["status"], "accepted")
        self.assertEqual(receipt["visible_lead_ids"], ["visible"])
        self.assertEqual(receipt["hidden_lead_ids"], ["hidden"])
        self.assertEqual(receipt["duplicate_status"], "duplicate_suppressed")
        self.assertFalse(receipt["external_action_taken"])
        self.assertEqual(json.loads((self.root / "receipt.json").read_text()), receipt)

    def test_documented_direct_entrypoint_has_safe_dry_run(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, str(root / "scripts/accept_attention_suppression.py")],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ready")
        self.assertIn("never sends a new brief", payload["safety"])

    def test_refuses_to_run_when_today_has_not_already_been_delivered(self):
        with self.assertRaisesRegex(AttentionAcceptanceError, "refusing a probe that could send"):
            self.accept(runtime_root=self.root / "empty")

    def test_fails_when_hidden_record_escapes_live_projection(self):
        def unsafe_opener(probe, **kwargs):
            command = json.loads(probe.data.decode("utf-8"))["text"]
            if command == "/morning":
                return FakeResponse(
                    {
                        "ok": True,
                        "status": "healthy",
                        "data": {
                            "inbound_leads_loaded": 1,
                            "agency_state": {"executive_items": [{"item_id": "lead-hidden"}]},
                        },
                    }
                )
            return FakeResponse(
                {
                    "ok": True,
                    "status": "healthy",
                    "data": {"leads": [{"lead_id": "hidden"}]},
                }
            )

        with self.assertRaisesRegex(AttentionAcceptanceError, "do not match"):
            self.accept(opener=unsafe_opener)


if __name__ == "__main__":
    unittest.main()
