from __future__ import annotations

import socket
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.tony_conversation_work import (
    FileConversationWorkStore,
    SubstantiveConversationRouter,
    TonyConversationIngress,
    TonyConversationWorker,
)


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


class TonyConversationWorkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.clock = MutableClock()
        self.store = FileConversationWorkStore(Path(self.temporary.name), clock=self.clock)
        self.ingress = TonyConversationIngress(self.store, workspace_id="narratiive")

    @staticmethod
    def request(message_id: str = "738") -> dict[str, str]:
        return {"chat_id": "12345", "message_id": message_id, "update_id": "451999302"}

    def test_normal_short_conversation_remains_synchronous(self) -> None:
        router = SubstantiveConversationRouter()
        self.assertFalse(router.requires_durable_work("Tony, are you there?"))
        self.assertFalse(router.requires_durable_work("Here is a long conversational observation " * 40))
        self.assertEqual(list((Path(self.temporary.name) / "jobs").glob("*.json")), [])

    def test_simulated_task_over_120_seconds_is_acknowledged_then_delivered(self) -> None:
        accepted = self.ingress.accept(
            self.request(),
            "Please commission the Research Analyst and propose a suitable UK growth company.",
        )
        self.assertIn("come back here", accepted.acknowledgement)
        sent: list[tuple[str, str]] = []

        def execute(text: str, work_id: str) -> str:
            self.clock.now += timedelta(seconds=121)
            return "I propose Example Growth Ltd because it fits the stated criteria."

        result = TonyConversationWorker(
            self.store, execute, lambda chat, text: sent.append((chat, text)), worker_id="worker-a", lease_seconds=300
        ).run_once()
        self.assertEqual(result["state"], "completed")
        self.assertTrue(result["external_action_taken"])
        self.assertEqual(sent, [("12345", "I propose Example Growth Ltd because it fits the stated criteria.")])
        self.assertGreater((self.clock.now - datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)).total_seconds(), 120)

    def test_restart_recovers_expired_generation_lease(self) -> None:
        accepted = self.ingress.accept(self.request(), "Please research a suitable company.")
        first = self.store.claim_next("worker-before-restart", lease_seconds=60)
        self.assertEqual(first["state"], "running")
        self.clock.now += timedelta(seconds=61)
        calls: list[str] = []
        result = TonyConversationWorker(
            self.store,
            lambda text, work_id: calls.append(work_id) or "Recovered result",
            lambda chat, text: None,
            worker_id="worker-after-restart",
        ).run_once()
        self.assertEqual(result["state"], "completed")
        self.assertEqual(calls, [accepted.work_id])
        events = (Path(self.temporary.name) / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn("conversation_work.recovered", events)

    def test_restart_immediately_recovers_live_lease_owned_by_dead_local_process(self) -> None:
        store = FileConversationWorkStore(
            Path(self.temporary.name),
            clock=self.clock,
            process_alive=lambda pid: pid != 41001,
        )
        ingress = TonyConversationIngress(store, workspace_id="narratiive")
        accepted = ingress.accept(self.request(), "Please research a suitable company.")
        first = store.claim_next(f"{socket.gethostname()}:41001", lease_seconds=2100)
        self.assertEqual(first["state"], "running")

        calls: list[str] = []
        result = TonyConversationWorker(
            store,
            lambda text, work_id: calls.append(work_id) or "Recovered result",
            lambda chat, text: None,
            worker_id=f"{socket.gethostname()}:41002",
        ).run_once()

        self.assertEqual(result["state"], "completed")
        self.assertEqual(calls, [accepted.work_id])
        events = (Path(self.temporary.name) / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn("conversation_work.recovered", events)

    def test_restart_does_not_steal_live_local_process_lease(self) -> None:
        store = FileConversationWorkStore(
            Path(self.temporary.name),
            clock=self.clock,
            process_alive=lambda _pid: True,
        )
        ingress = TonyConversationIngress(store, workspace_id="narratiive")
        ingress.accept(self.request(), "Please research a suitable company.")
        store.claim_next(f"{socket.gethostname()}:41001", lease_seconds=2100)

        self.assertIsNone(store.claim_next(f"{socket.gethostname()}:41002", lease_seconds=2100))

    def test_specialist_failure_produces_useful_followup(self) -> None:
        self.ingress.accept(self.request(), "Please ask a specialist to investigate this.")
        sent: list[tuple[str, str]] = []

        def fail(_text: str, _work_id: str) -> str:
            raise RuntimeError("specialist unavailable")

        worker = TonyConversationWorker(
            self.store, fail, lambda chat, text: sent.append((chat, text)), worker_id="worker-a", max_attempts=2
        )
        self.assertEqual(worker.run_once()["state"], "queued")
        self.assertEqual(worker.run_once()["state"], "failed")
        self.assertEqual(len(sent), 1)
        self.assertIn("couldn’t complete", sent[0][1])
        self.assertIn("failure evidence", sent[0][1])
        self.assertTrue(next(iter(self.store.jobs.glob("*.json"))).read_text(encoding="utf-8").find('"external_action_taken": true') > 0)

    def test_replay_and_active_lease_do_not_duplicate_execution(self) -> None:
        first = self.ingress.accept(self.request(), "Please research a suitable company.")
        replay = self.ingress.accept(self.request(), "Please research a suitable company.")
        self.assertTrue(replay.replay)
        self.assertEqual(first.work_id, replay.work_id)
        self.assertIsNotNone(self.store.claim_next("worker-a", lease_seconds=300))
        self.assertIsNone(self.store.claim_next("worker-b", lease_seconds=300))
        self.assertEqual(len(list((Path(self.temporary.name) / "jobs").glob("*.json"))), 1)

    def test_delivery_retry_uses_stored_result_without_duplicate_model_execution(self) -> None:
        self.ingress.accept(self.request(), "Please research a suitable company.")
        executions: list[str] = []
        deliveries: list[str] = []

        def execute(_text: str, work_id: str) -> str:
            executions.append(work_id)
            return "Durable final result"

        def transient_send(_chat_id: str, text: str) -> None:
            deliveries.append(text)
            if len(deliveries) == 1:
                raise RuntimeError("temporary Telegram failure")

        worker = TonyConversationWorker(
            self.store,
            execute,
            transient_send,
            worker_id="worker-a",
            max_attempts=3,
        )
        self.assertEqual(worker.run_once()["state"], "ready_to_deliver")
        self.assertEqual(worker.run_once()["state"], "completed")
        self.assertEqual(len(executions), 1)
        self.assertEqual(deliveries, ["Durable final result", "Durable final result"])


if __name__ == "__main__":
    unittest.main()
