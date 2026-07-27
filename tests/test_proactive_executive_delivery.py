import unittest
from datetime import date, datetime

from runtime.proactive_executive_delivery import (
    InMemoryDeliveryKeyStore,
    ProactiveExecutiveDeliveryService,
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


if __name__ == "__main__":
    unittest.main()
