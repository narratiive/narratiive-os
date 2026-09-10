import json
import tempfile
import unittest
from pathlib import Path

from runtime.agency_state_projection import AgencyStateProjector
from runtime.inbound_leads import FileInboundLeadStore, InboundLead
from runtime.lead_attention import LeadAttentionService


class LeadAttentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.store = FileInboundLeadStore(root / "leads.json"); self.events = root / "events.jsonl"
        self.store.replace([
            InboundLead("safe-1", "Test", company="SAFE TEST CO", email="safe@example.invalid", source="SAFE test"),
            InboundLead("real-1", "Alex", company="Warm Co", email="alex@example.com", lead_temperature="Warm"),
        ])
        self.service = LeadAttentionService(self.store, self.events)

    def tearDown(self): self.tmp.cleanup()

    def test_batch_safe_archive_is_reversible_and_audited(self):
        result = self.service.batch_safe(); self.assertEqual(result["count"], 1)
        self.assertEqual([x.lead_id for x in self.service.list()], ["real-1"])
        self.assertTrue(self.service.mutate("safe-1", "restore")["ok"])
        self.assertEqual(next(x for x in self.store.read() if x.lead_id == "safe-1").disposition, "active")
        self.assertEqual(len(self.events.read_text().splitlines()), 2)

    def test_ambiguous_reference_fails_without_mutation(self):
        self.store.upsert(InboundLead("real-2", "Alex", company="Other Co", email="other@example.com"))
        result = self.service.mutate("Alex", "suppressed")
        self.assertEqual(result["error"], "ambiguous_lead_reference")
        self.assertTrue(all(x.disposition == "active" for x in self.store.read()))

    def test_projection_excludes_suppressed_test_archived(self):
        self.service.mutate("safe-1", "suppressed")
        state = AgencyStateProjector().project(type("S", (), {"workstreams": (), "approvals_required": (), "generated_at": "now"})(), self.store.read(), lead_source_available=True)
        self.assertFalse(any("safe-1" in item.item_id for item in state.executive_items))


if __name__ == "__main__": unittest.main()
