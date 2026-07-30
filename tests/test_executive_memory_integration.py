import tempfile
import unittest
from pathlib import Path

from runtime.executive_brief import BriefPeriod
from runtime.executive_integration import (
    ExecutiveMemoryIntegration,
    IntegratedExecutiveBriefService,
)
from runtime.executive_memory import ExecutiveMemoryStore, MemoryKind, MemoryScope
from runtime.mission_control import MissionControlBuilder
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationReport


class ExecutiveMemoryIntegrationTests(unittest.TestCase):
    @staticmethod
    def progress():
        return ProgressSnapshot(
            status="healthy",
            campaigns=(),
            validation=ValidationReport(
                status="pass",
                objects_validated=0,
                errors=(),
                warnings=(),
            ),
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "executive-memory.jsonl"
        self.scope = MemoryScope(agency_id="narratiive", client_id="rave")
        self.store = ExecutiveMemoryStore(self.path)
        self.memory = ExecutiveMemoryIntegration(self.store, scope=self.scope)
        self.snapshot = MissionControlBuilder().build(
            generated_at="2026-07-30T08:00:00Z",
            progress=self.progress(),
            workstreams=(),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_morning_brief_recalls_durable_commitment_after_restart(self):
        self.store.append(
            kind=MemoryKind.COMMITMENT,
            summary="Send the Rave proposal on Thursday",
            scope=self.scope,
            importance=5,
        )
        restarted_store = ExecutiveMemoryStore(self.path)
        service = IntegratedExecutiveBriefService(
            memory=ExecutiveMemoryIntegration(restarted_store, scope=self.scope)
        )

        brief = service.build(self.snapshot, BriefPeriod.MORNING)

        self.assertIn(
            "Memory — commitment: Send the Rave proposal on Thursday",
            brief.priorities,
        )
        self.assertTrue(restarted_store.verify())

    def test_required_decision_is_carried_into_approvals(self):
        self.store.append(
            kind=MemoryKind.DECISION,
            summary="Approve the revised commercial offer",
            scope=self.scope,
            importance=4,
            requires_matt=True,
        )
        brief = IntegratedExecutiveBriefService(memory=self.memory).build(
            self.snapshot, BriefPeriod.MORNING
        )

        self.assertIn(
            "Memory — decision: Approve the revised commercial offer",
            brief.approvals,
        )

    def test_evening_brief_carries_memory_forward(self):
        self.store.append(
            kind=MemoryKind.CONTEXT,
            summary="Client is waiting for final proof",
            scope=self.scope,
            importance=4,
        )
        brief = IntegratedExecutiveBriefService(memory=self.memory).build(
            self.snapshot, BriefPeriod.EVENING
        )

        self.assertIn(
            "Memory — context: Client is waiting for final proof",
            brief.carry_forward,
        )

    def test_generated_brief_is_recorded_once_when_unchanged(self):
        service = IntegratedExecutiveBriefService(memory=self.memory)
        service.build(self.snapshot, BriefPeriod.MORNING)
        service.build(self.snapshot, BriefPeriod.MORNING)

        outcomes = self.store.select(
            scope=self.scope,
            kinds=(MemoryKind.OUTCOME,),
            limit=10,
        )
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].source, "executive_brief")

    def test_client_scope_isolation_is_preserved(self):
        other_scope = MemoryScope(agency_id="narratiive", client_id="other")
        self.store.append(
            kind=MemoryKind.COMMITMENT,
            summary="Private commitment for another client",
            scope=other_scope,
            importance=5,
        )
        brief = IntegratedExecutiveBriefService(memory=self.memory).build(
            self.snapshot, BriefPeriod.MORNING
        )

        rendered = "\n".join(brief.priorities)
        self.assertNotIn("another client", rendered)


if __name__ == "__main__":
    unittest.main()
