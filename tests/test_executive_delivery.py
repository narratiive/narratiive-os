from __future__ import annotations

from unittest import TestCase

from runtime.executive_delivery import (
    CallableTextChannelAdapter,
    DeliveryReceipt,
    DeliveryTarget,
    ExecutiveMessageContent,
    RenderedMessage,
    TelegramTextRenderer,
)


class ExecutiveDeliveryTests(TestCase):
    def test_content_is_canonical_and_deduplicated(self) -> None:
        content = ExecutiveMessageContent(
            kind=" material_escalation ",
            title=" Review needed ",
            items=(" blocker:a ", "", "blocker:a", "approval:b"),
            metadata={"workspace_id": "narratiive"},
        )

        self.assertEqual(content.kind, "material_escalation")
        self.assertEqual(content.title, "Review needed")
        self.assertEqual(content.items, ("blocker:a", "approval:b"))

    def test_telegram_renderer_bounds_items_and_characters(self) -> None:
        renderer = TelegramTextRenderer(max_items=2, max_characters=60)
        content = ExecutiveMessageContent(
            kind="material_escalation",
            title="Review needed:",
            items=("one", "two", "three"),
        )

        message = renderer.render(content)

        self.assertLessEqual(len(message.text), 60)
        self.assertIn("- one", message.text)
        self.assertIn("- two", message.text)
        self.assertIn("...and 1 more.", message.text)
        self.assertNotIn("- three", message.text)

    def test_delivery_receipt_is_canonical(self) -> None:
        receipt = DeliveryReceipt(
            channel=" Telegram ",
            address=" 12345 ",
            provider_message_id=" message-7 ",
        )

        self.assertEqual(receipt.channel, "telegram")
        self.assertEqual(receipt.address, "12345")
        self.assertEqual(receipt.provider_message_id, "message-7")

    def test_delivery_receipt_fails_closed_without_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "channel is required"):
            DeliveryReceipt(channel=" ", address="12345")
        with self.assertRaisesRegex(ValueError, "address is required"):
            DeliveryReceipt(channel="telegram", address=" ")

    def test_callable_adapter_preserves_existing_sender_shape(self) -> None:
        sent: list[tuple[str, str]] = []
        adapter = CallableTextChannelAdapter(
            channel="telegram",
            send_text=lambda address, text: sent.append((address, text)),
        )

        receipt = adapter.send(
            DeliveryTarget(channel=" telegram ", address=" 12345 "),
            RenderedMessage(text=" Hello "),
        )

        self.assertEqual(sent, [("12345", "Hello")])
        self.assertEqual(receipt.channel, "telegram")
        self.assertEqual(receipt.address, "12345")

    def test_callable_adapter_requires_callable_sender(self) -> None:
        with self.assertRaisesRegex(TypeError, "send_text must be callable"):
            CallableTextChannelAdapter(channel="telegram", send_text=None)

    def test_callable_adapter_fails_closed_for_wrong_channel(self) -> None:
        adapter = CallableTextChannelAdapter(channel="telegram", send_text=lambda *_: None)

        with self.assertRaisesRegex(ValueError, "not supported"):
            adapter.send(
                DeliveryTarget(channel="email", address="matt@example.com"),
                RenderedMessage(text="Hello"),
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
