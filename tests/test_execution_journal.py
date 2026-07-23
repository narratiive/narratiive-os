import json
import tempfile
import unittest
from pathlib import Path

from runtime.execution_journal import ExecutionJournal, ExecutionJournalError


class ExecutionJournalTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tempdir.name)
        self.journal = ExecutionJournal(self.state_dir)

    def tearDown(self):
        self.tempdir.cleanup()

    def append(self, **overrides):
        values = {
            "decision_id": "decision-1",
            "workspace_id": "narratiive",
            "client_id": "rave",
            "action": "generate-growth-blueprint",
            "rationale": "Growth Specification is approved",
            "actor": "claude",
            "status": "selected",
            "repository_revision": "abc123",
            "state_hash": "state-1",
            "occurred_at": "2026-07-23T20:00:00Z",
        }
        values.update(overrides)
        return self.journal.append(**values)

    def test_append_and_restart_recovery(self):
        first = self.append(record_id="record-1")
        second = self.append(
            record_id="record-2",
            status="dispatched",
            occurred_at="2026-07-23T20:01:00Z",
        )
        recovered = ExecutionJournal(self.state_dir).read_all()
        self.assertEqual([item.record_id for item in recovered], ["record-1", "record-2"])
        self.assertEqual(second.previous_hash, first.record_hash)

    def test_history_reconstructs_decision_provenance(self):
        self.append(record_id="record-1")
        self.append(
            record_id="record-2",
            status="completed",
            artifacts=["clients/rave/blueprint.md"],
            metadata={"duration_seconds": 42},
        )
        self.append(record_id="record-3", decision_id="decision-2")
        history = self.journal.history("decision-1")
        self.assertEqual([item.status for item in history], ["selected", "completed"])
        self.assertEqual(history[-1].artifacts, ("clients/rave/blueprint.md",))
        self.assertEqual(history[-1].metadata["duration_seconds"], 42)

    def test_verify_returns_machine_readable_integrity_summary(self):
        self.append(record_id="record-1")
        self.append(record_id="record-2", decision_id="decision-2")
        result = self.journal.verify()
        self.assertTrue(result["ok"])
        self.assertEqual(result["records"], 2)
        self.assertEqual(result["decisions"], 2)
        self.assertEqual(len(result["head_hash"]), 64)

    def test_tampering_is_detected(self):
        self.append(record_id="record-1")
        line = json.loads(self.journal.path.read_text(encoding="utf-8"))
        line["rationale"] = "tampered"
        self.journal.path.write_text(json.dumps(line) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ExecutionJournalError, "hash mismatch"):
            self.journal.read_all()

    def test_chain_break_is_detected(self):
        self.append(record_id="record-1")
        self.append(record_id="record-2", status="completed")
        lines = self.journal.path.read_text(encoding="utf-8").splitlines()
        second = json.loads(lines[1])
        second["previous_hash"] = "wrong"
        lines[1] = json.dumps(second)
        self.journal.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ExecutionJournalError, "chain break"):
            self.journal.read_all()

    def test_invalid_record_is_rejected_before_persistence(self):
        with self.assertRaisesRegex(ExecutionJournalError, "unsupported execution status"):
            self.append(status="invented")
        self.assertFalse(self.journal.path.exists())

    def test_duplicate_record_id_is_rejected(self):
        self.append(record_id="record-1")
        with self.assertRaisesRegex(ExecutionJournalError, "duplicate execution record id"):
            self.append(record_id="record-1", status="completed")
        self.assertEqual(len(self.journal.read_all()), 1)

    def test_latest_returns_current_decision_state(self):
        self.assertIsNone(self.journal.latest("missing"))
        self.append(record_id="record-1")
        completed = self.append(record_id="record-2", status="completed")
        self.assertEqual(self.journal.latest("decision-1"), completed)


if __name__ == "__main__":
    unittest.main()
