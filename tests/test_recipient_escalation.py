from __future__ import annotations

from unittest import TestCase

from runtime.proactive_executive_delivery import EscalationResult
from runtime.recipient_escalation import RecipientMaterialEscalationService
from runtime.recipients import Recipient, RecipientAddress, RecipientDirectory


class RecordingEscalationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def escalate(self, *, workspace_id: str, chat_id: str) -> EscalationResult:
        self.calls.append((workspace_id, chat_id))
        return EscalationResult(
            workspace_id,
            chat_id,
            "escalated",
            1,
            1,
            "digest",
        )


class RecipientMaterialEscalationServiceTests(TestCase):
    def service(self, recipient: Recipient, *, channel: str = "telegram"):
        transport = RecordingEscalationService()
        service = RecipientMaterialEscalationService(
            service=transport,
            recipients=RecipientDirectory((recipient,)),
            channel=channel,
        )
        return service, transport

    def test_resolves_recipient_to_enabled_channel_target(self) -> None:
        service, transport = self.service(
            Recipient(
                recipient_id="matt",
                display_name="Matt",
                addresses=(
                    RecipientAddress("email", "matt@example.com"),
                    RecipientAddress("telegram", "12345"),
                ),
            )
        )

        result = service.escalate(
            workspace_id=" narratiive ",
            recipient_id=" MATT ",
        )

        self.assertEqual(result.status, "escalated")
        self.assertEqual(transport.calls, [("narratiive", "12345")])

    def test_disabled_target_fails_closed_without_dispatch(self) -> None:
        service, transport = self.service(
            Recipient(
                recipient_id="matt",
                display_name="Matt",
                addresses=(RecipientAddress("telegram", "12345", enabled=False),),
            )
        )

        with self.assertRaisesRegex(
            LookupError,
            "no enabled telegram target",
        ):
            service.escalate(workspace_id="narratiive", recipient_id="matt")

        self.assertEqual(transport.calls, [])

    def test_missing_requested_channel_fails_closed_without_dispatch(self) -> None:
        service, transport = self.service(
            Recipient(
                recipient_id="matt",
                display_name="Matt",
                addresses=(RecipientAddress("email", "matt@example.com"),),
            )
        )

        with self.assertRaisesRegex(
            LookupError,
            "no enabled telegram target",
        ):
            service.escalate(workspace_id="narratiive", recipient_id="matt")

        self.assertEqual(transport.calls, [])

    def test_multiple_targets_for_same_channel_fail_closed(self) -> None:
        service, transport = self.service(
            Recipient(
                recipient_id="matt",
                display_name="Matt",
                addresses=(
                    RecipientAddress("telegram", "12345"),
                    RecipientAddress("telegram", "67890"),
                ),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "multiple enabled telegram targets",
        ):
            service.escalate(workspace_id="narratiive", recipient_id="matt")

        self.assertEqual(transport.calls, [])

    def test_unknown_recipient_fails_before_dispatch(self) -> None:
        service, transport = self.service(
            Recipient(
                recipient_id="matt",
                display_name="Matt",
                addresses=(RecipientAddress("telegram", "12345"),),
            )
        )

        with self.assertRaisesRegex(KeyError, "unknown recipient_id"):
            service.escalate(workspace_id="narratiive", recipient_id="someone-else")

        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    import unittest

    unittest.main()
