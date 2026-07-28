from __future__ import annotations

from unittest import TestCase

from runtime.executive_delivery import (
    CallableTextChannelAdapter,
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
