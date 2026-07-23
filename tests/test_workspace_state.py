from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from runtime.workspace_state import WorkspaceStateError, WorkspaceStateRepository


class WorkspaceStateRepositoryTests(unittest.TestCase):
    def repository(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return WorkspaceStateRepository(Path(temporary.name))

    def test_state_survives_repository_recreation_and_replay(self):
        repository = self.repository()
        repository.append("workspace.initialized", workspace_id="agency")
        repository.append("client.activated", workspace_id="agency", client_id="rave")
        repository.append(
            "run.started",
            workspace_id="agency",
            client_id="rave",
            payload={"run_id": "run-1", "stage": "growth_blueprint"},
        )

        restored = WorkspaceStateRepository(repository.state_dir).load("agency")

        self.assertEqual(restored.active_client_id, "rave")
        self.assertEqual(restored.active_run_id, "run-1")
        self.assertEqual(restored.runs["run-1"]["status"], "active")
        self.assertEqual(restored.last_sequence, 3)

    def test_approval_and_action_lifecycle_is_deterministic(self):
        repository = self.repository()
        repository.append("workspace.initialized", workspace_id="agency")
        repository.append(
            "approval.requested",
            workspace_id="agency",
            client_id="rave",
            payload={"approval_id": "approval-1", "artifact": "blueprint"},
        )
        repository.append(
            "approval.decided",
            workspace_id="agency",
            client_id="rave",
            payload={"approval_id": "approval-1", "decision": "approved", "reviewer_id": "matt"},
        )
        repository.append(
            "action.queued",
            workspace_id="agency",
            client_id="rave",
            payload={"action_id": "action-1", "action": "generate_campaign_world"},
        )
        snapshot = repository.append(
            "action.completed",
            workspace_id="agency",
            client_id="rave",
            payload={"action_id": "action-1", "result": "campaign-world.md"},
        )

        self.assertEqual(snapshot.approvals["approval-1"]["status"], "approved")
        self.assertEqual(snapshot.queued_actions, [])
        self.assertEqual(snapshot.completed_actions[0]["result"], "campaign-world.md")

    def test_snapshot_is_atomic_and_contains_integrity_hash(self):
        repository = self.repository()
        repository.append("workspace.initialized", workspace_id="agency")

        envelope = json.loads(repository.snapshot_path.read_text(encoding="utf-8"))

        self.assertEqual(envelope["state"]["workspace_id"], "agency")
        self.assertEqual(len(envelope["sha256"]), 64)
        self.assertFalse(repository.snapshot_path.with_suffix(".tmp").exists())

    def test_corrupt_log_is_rejected_instead_of_silently_reset(self):
        repository = self.repository()
        repository.state_dir.mkdir(parents=True, exist_ok=True)
        repository.events_path.write_text('{"sequence":1}\nnot-json\n', encoding="utf-8")

        with self.assertRaises(WorkspaceStateError):
            repository.read_events()

    def test_unknown_references_are_rejected(self):
        repository = self.repository()
        repository.append("workspace.initialized", workspace_id="agency")

        with self.assertRaises(WorkspaceStateError):
            repository.append(
                "run.completed",
                workspace_id="agency",
                client_id="rave",
                payload={"run_id": "missing"},
            )

        with self.assertRaises(WorkspaceStateError):
            repository.append(
                "approval.decided",
                workspace_id="agency",
                client_id="rave",
                payload={"approval_id": "missing", "decision": "approved"},
            )

    def test_duplicate_event_ids_are_detected_during_replay(self):
        repository = self.repository()
        repository.append(
            "workspace.initialized",
            workspace_id="agency",
            event_id="same-id",
        )
        with self.assertRaises(WorkspaceStateError):
            repository.append(
                "client.activated",
                workspace_id="agency",
                client_id="rave",
                event_id="same-id",
            )

    def test_threaded_appends_receive_contiguous_sequences(self):
        repository = self.repository()
        repository.append("workspace.initialized", workspace_id="agency")
        failures: list[Exception] = []

        def append_action(index: int) -> None:
            try:
                repository.append(
                    "action.queued",
                    workspace_id="agency",
                    client_id="rave",
                    payload={"action_id": f"action-{index}"},
                )
            except Exception as exc:  # pragma: no cover - assertion reports captured failures
                failures.append(exc)

        threads = [threading.Thread(target=append_action, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(failures, [])
        events = repository.read_events()
        self.assertEqual([event.sequence for event in events], list(range(1, 10)))
        self.assertEqual(len(repository.load("agency").queued_actions), 8)

    def test_rebuild_snapshot_recovers_deleted_read_model(self):
        repository = self.repository()
        repository.append("workspace.initialized", workspace_id="agency")
        repository.append("client.activated", workspace_id="agency", client_id="rave")
        repository.snapshot_path.unlink()

        rebuilt = repository.rebuild_snapshot("agency")

        self.assertTrue(repository.snapshot_path.exists())
        self.assertEqual(rebuilt.active_client_id, "rave")


if __name__ == "__main__":
    unittest.main()
