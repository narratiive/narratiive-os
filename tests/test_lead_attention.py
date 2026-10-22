import json
import tempfile
import unittest
from pathlib import Path

from runtime.agency_state_projection import AgencyStateProjector
from runtime.inbound_leads import FileInboundLeadStore, InboundLead
from runtime.lead_attention import LeadAttentionService
from runtime.executive_visibility import ExecutiveVisibilityPolicy
from runtime.agency_state import AgencyArea, AgencyItem
from runtime.briefing_intelligence import FileBriefingDecisionRegister


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

    def test_executive_inputs_exclude_hidden_and_completed_without_deleting_them(self):
        self.store.replace([
            InboundLead("suppressed", "Test", company="SAFE fixture", disposition="suppressed"),
            InboundLead("archived", "Test", company="Archived fixture", disposition="archived"),
            InboundLead("complete", "Alex", company="Finished Co", status="Completed"),
            InboundLead("active", "Sam", company="Active Co", status="New"),
        ])

        visible = ExecutiveVisibilityPolicy().visible_leads(self.store.read())

        self.assertEqual([lead.lead_id for lead in visible], ["active"])
        self.assertEqual(
            {lead.lead_id for lead in FileInboundLeadStore(self.store.path).read()},
            {"suppressed", "archived", "complete", "active"},
        )

    def test_non_lead_briefing_entity_is_resolved_and_suppressed_without_source_mutation(self):
        register = FileBriefingDecisionRegister(self.store.path.parent / "decisions.jsonl")
        workflow = AgencyItem(
            "workflow-current",
            AgencyArea.DELIVERY,
            "Current account delivery",
            "active",
            "Complete the current evidence pack.",
            entity_id="account-1",
            aliases=("Account One",),
            significance="P3",
        )
        service = LeadAttentionService(
            self.store,
            self.events,
            decision_register=register,
            entity_loader=lambda: (workflow,),
        )

        result = service.mutate(
            "Account One",
            "suppressed",
            "Founder asked Tony to stop reporting this.",
            decision_type="suppress",
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["source_record_mutated"])
        self.assertEqual(register.read()[0].entity_id, "account-1")
        self.assertEqual({lead.lead_id for lead in self.store.read()}, {"safe-1", "real-1"})


if __name__ == "__main__": unittest.main()
