import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from runtime.mission_control import MissionControlSnapshot
from runtime.proactive_executive_delivery import (
    DeliveryStatusRecord,
    FileDeliveryKeyStore,
    FileLastEscalationStore,
    InMemoryDeliveryKeyStore,
    LatestDeliveryStatusStore,
    MaterialEscalationService,
    ProactiveDeliveryStorageError,
    ProactiveExecutiveDeliveryService,
    describe_delivery_status,
)
from runtime.tony_command_service import CommandResponse


class ProactiveExecutiveDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = []
        self.sent = []
        self.store = InMemoryDeliveryKeyStore()
        self.now = datetime(2026, 7, 27, 8, 0, 0)

    def service(self, execute, send=None, max_attempts=3):
        return ProactiveExecutiveDeliveryService(
            execute_command=execute,
            send_message=send or (lambda chat_id, message: self.sent.append((chat_id, message))),
            key_store=self.store,
            record_event=self.events.append,
            clock=lambda: self.now,
            max_attempts=max_attempts,
        )

    @staticmethod
    def healthy_response(command="morning"):
        return CommandResponse(
            command=command,
            status="healthy",
            message="Three priorities. One blocker. No approvals waiting.",
            data={"evidence": ["mission-control/2026-07-27"]},
        )

    def test_delivers_once_and_records_immutable_success_event(self):
        service = self.service(lambda command, objects: self.healthy_response())

        result = service.deliver(
            workspace_id="narratiive",
            chat_id="12345",
            command="/morning",
        )

        self.assertEqual(result.status, "delivered")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(
            result.delivery_key,
            "narratiive:morning:2026-07-27",
        )
        self.assertEqual(
            self.sent,
            [("12345", "Three priorities. One blocker. No approvals waiting.")],
        )
        self.assertEqual(self.events[-1]["event_type"], "executive_brief.delivered")
        self.assertEqual(self.events[-1]["delivery_key"], result.delivery_key)

    def test_suppresses_duplicate_without_regenerating_or_sending(self):
        calls = []

        def execute(command, objects):
            calls.append(command)
            return self.healthy_response()

        service = self.service(execute)
        first = service.deliver(
            workspace_id="narratiive", chat_id="12345", command="morning"
        )
        second = service.deliver(
            workspace_id="narratiive", chat_id="12345", command="morning"
        )

        self.assertEqual(first.status, "delivered")
        self.assertEqual(second.status, "duplicate_suppressed")
        self.assertEqual(second.attempts, 0)
        self.assertEqual(calls, ["/morning"])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(
            self.events[-1]["event_type"],
            "executive_brief.delivery_suppressed",
        )

    def test_retries_transient_transport_failure_then_succeeds(self):
        attempts = []

        def send(chat_id, message):
            attempts.append((chat_id, message))
            if len(attempts) < 3:
                raise ConnectionError("temporary Telegram failure")

        service = self.service(
            lambda command, objects: self.healthy_response(),
            send=send,
            max_attempts=3,
        )
        result = service.deliver(
            workspace_id="narratiive", chat_id="12345", command="evening"
        )

        self.assertEqual(result.status, "delivered")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(self.events[-1]["event_type"], "executive_brief.delivered")

    def test_fails_closed_after_retry_limit_without_marking_delivered(self):
        def send(chat_id, message):
            raise ConnectionError("Telegram unavailable")

        service = self.service(
            lambda command, objects: self.healthy_response(),
            send=send,
            max_attempts=2,
        )
        result = service.deliver(
            workspace_id="narratiive", chat_id="12345", command="morning"
        )

        self.assertEqual(result.status, "delivery_failed")
        self.assertEqual(result.attempts, 2)
        self.assertIn("Telegram unavailable", result.error)
        self.assertFalse(self.store.contains(result.delivery_key))
        self.assertEqual(
            self.events[-1]["event_type"],
            "executive_brief.delivery_failed",
        )

    def test_does_not_send_untrusted_generated_brief(self):
        service = self.service(
            lambda command, objects: CommandResponse(
                command="morning",
                status="error",
                message="Tony could not build a trusted daily brief",
                data={"error_code": "executive_brief_untrusted"},
            )
        )
        result = service.deliver(
            workspace_id="narratiive", chat_id="12345", command="morning"
        )

        self.assertEqual(result.status, "generation_failed")
        self.assertEqual(result.attempts, 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(result.error, "executive_brief_untrusted")

    def test_delivery_key_is_scoped_by_workspace_command_and_date(self):
        self.assertEqual(
            ProactiveExecutiveDeliveryService.build_delivery_key(
                workspace_id="client-a",
                command="morning",
                delivery_date=date(2026, 7, 28),
            ),
            "client-a:morning:2026-07-28",
        )

    def test_rejects_unsupported_commands_and_missing_identity(self):
        service = self.service(lambda command, objects: self.healthy_response())

        with self.assertRaisesRegex(ValueError, "Unsupported proactive command"):
            service.deliver(
                workspace_id="narratiive", chat_id="12345", command="friday"
            )
        with self.assertRaisesRegex(ValueError, "workspace_id is required"):
            service.deliver(workspace_id=" ", chat_id="12345", command="morning")
        with self.assertRaisesRegex(ValueError, "chat_id is required"):
            service.deliver(workspace_id="narratiive", chat_id=" ", command="morning")


class FileDeliveryKeyStoreTests(unittest.TestCase):
    def test_persists_keys_across_separate_store_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keys.json"
            first = FileDeliveryKeyStore(path)
            self.assertFalse(first.contains("narratiive:morning:2026-07-27"))
            first.add("narratiive:morning:2026-07-27")

            second = FileDeliveryKeyStore(path)
            self.assertTrue(second.contains("narratiive:morning:2026-07-27"))

    def test_add_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileDeliveryKeyStore(Path(directory) / "keys.json")
            store.add("a")
            store.add("a")
            self.assertTrue(store.contains("a"))

    def test_corrupt_store_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keys.json"
            path.write_text("not json", encoding="utf-8")
            store = FileDeliveryKeyStore(path)
            with self.assertRaises(ProactiveDeliveryStorageError):
                store.contains("a")


class LatestDeliveryStatusStoreTests(unittest.TestCase):
    def test_read_returns_none_when_never_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LatestDeliveryStatusStore(Path(directory) / "status.json")
            self.assertIsNone(store.read())
            self.assertEqual(
                describe_delivery_status(store.read())["state"], "not_connected"
            )

    def test_round_trips_latest_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            store = LatestDeliveryStatusStore(path)
            store.record(
                DeliveryStatusRecord(
                    kind="brief",
                    command="morning",
                    status="delivered",
                    recorded_at="2026-07-27T08:00:00+00:00",
                )
            )
            record = LatestDeliveryStatusStore(path).read()
            self.assertEqual(record.status, "delivered")
            self.assertEqual(describe_delivery_status(record)["state"], "connected")

    def test_failure_status_reports_degraded_connection(self):
        record = DeliveryStatusRecord(
            kind="brief",
            command="morning",
            status="delivery_failed",
            recorded_at="2026-07-27T08:00:00+00:00",
            error="Telegram unavailable",
        )
        status = describe_delivery_status(record)
        self.assertEqual(status["state"], "degraded")
        self.assertIn("Telegram unavailable", status["evidence"])

    def test_corrupt_status_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ProactiveDeliveryStorageError):
                LatestDeliveryStatusStore(path).read()


def escalation_snapshot(*, blockers=(), approvals=()) -> MissionControlSnapshot:
    return MissionControlSnapshot(
        generated_at="2026-07-27T08:00:00Z",
        status="blocked" if blockers else "healthy",
        progress={"status": "healthy"},
        workstreams=(),
        connections=(),
        approvals_required=tuple(approvals),
        blockers=tuple(blockers),
    )


class MaterialEscalationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = []
        self.sent = []
        self.key_store = InMemoryDeliveryKeyStore()
        self.now = datetime(2026, 7, 27, 8, 0, 0)

    def service(self, loader, send=None, last_sent_store=None, min_interval_seconds=1800):
        return MaterialEscalationService(
            mission_control_loader=loader,
            send_message=send or (lambda chat_id, message: self.sent.append((chat_id, message))),
            key_store=self.key_store,
            last_sent_store=last_sent_store or FileLastEscalationStore(self._tmp_path()),
            record_event=self.events.append,
            clock=lambda: self.now,
            min_interval_seconds=min_interval_seconds,
        )

    def _tmp_path(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name) / "last-sent.json"

    def test_escalates_new_blockers_and_approvals(self):
        service = self.service(
            lambda: escalation_snapshot(
                blockers=("workstream:x:blocked",), approvals=("pr:12",)
            )
        )
        result = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(result.status, "escalated")
        self.assertEqual(result.material_count, 2)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("workstream:x:blocked", self.sent[0][1])
        self.assertEqual(self.events[-1]["event_type"], "executive_escalation.sent")

    def test_no_material_produces_no_send(self):
        service = self.service(lambda: escalation_snapshot())
        result = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(result.status, "no_new_material")
        self.assertEqual(self.sent, [])

    def test_unchanged_material_is_deduplicated(self):
        loader = lambda: escalation_snapshot(blockers=("workstream:x:blocked",))
        service = self.service(loader)
        first = service.escalate(workspace_id="narratiive", chat_id="12345")
        second = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(first.status, "escalated")
        self.assertEqual(second.status, "duplicate_suppressed")
        self.assertEqual(len(self.sent), 1)

    def test_changed_material_within_interruption_window_is_rate_limited(self):
        last_sent_store = FileLastEscalationStore(self._tmp_path())
        blockers = ["workstream:x:blocked"]

        def loader():
            return escalation_snapshot(blockers=tuple(blockers))

        service = self.service(loader, last_sent_store=last_sent_store, min_interval_seconds=1800)
        first = service.escalate(workspace_id="narratiive", chat_id="12345")
        blockers.append("workstream:y:blocked")
        second = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(first.status, "escalated")
        self.assertEqual(second.status, "rate_limited")
        self.assertEqual(len(self.sent), 1)

    def test_retries_then_fails_closed_without_marking_escalated(self):
        def send(chat_id, message):
            raise ConnectionError("Telegram unavailable")

        service = self.service(
            lambda: escalation_snapshot(blockers=("workstream:x:blocked",)),
            send=send,
        )
        service.max_attempts = 2
        result = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(result.status, "delivery_failed")
        self.assertFalse(self.key_store.contains(result.digest_key))
        self.assertEqual(
            self.events[-1]["event_type"], "executive_escalation.delivery_failed"
        )

    def test_untrusted_mission_control_fails_closed(self):
        def broken_loader():
            raise ValueError("invalid snapshot")

        service = self.service(broken_loader)
        result = service.escalate(workspace_id="narratiive", chat_id="12345")

        self.assertEqual(result.status, "generation_failed")
        self.assertEqual(self.sent, [])

    def test_rejects_missing_identity(self):
        service = self.service(lambda: escalation_snapshot(blockers=("x",)))
        with self.assertRaisesRegex(ValueError, "workspace_id is required"):
            service.escalate(workspace_id=" ", chat_id="12345")
        with self.assertRaisesRegex(ValueError, "chat_id is required"):
            service.escalate(workspace_id="narratiive", chat_id=" ")


if __name__ == "__main__":
    unittest.main()
