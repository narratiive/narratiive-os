import unittest

from runtime.executive_delivery import DeliveryTarget
from runtime.recipients import Recipient, RecipientAddress, RecipientDirectory


class RecipientTests(unittest.TestCase):
    def test_canonicalises_and_deduplicates_addresses(self) -> None:
        recipient = Recipient(
            recipient_id=" Matt ",
            display_name=" Matt ",
            addresses=(
                RecipientAddress(channel=" Telegram ", address=" 12345 "),
                RecipientAddress(channel="telegram", address="12345"),
                RecipientAddress(channel="email", address="matt@example.com"),
            ),
        )

        self.assertEqual(recipient.recipient_id, "matt")
        self.assertEqual(recipient.display_name, "Matt")
        self.assertEqual(
            recipient.addresses,
            (
                RecipientAddress(channel="email", address="matt@example.com"),
                RecipientAddress(channel="telegram", address="12345"),
            ),
        )

    def test_resolves_enabled_targets_in_preferred_channel_order(self) -> None:
        recipient = Recipient(
            recipient_id="matt",
            display_name="Matt",
            addresses=(
                RecipientAddress(channel="email", address="matt@example.com"),
                RecipientAddress(channel="telegram", address="12345"),
                RecipientAddress(channel="slack", address="U123", enabled=False),
            ),
        )

        self.assertEqual(
            recipient.resolve_targets(preferred_channels=("telegram", "email")),
            (
                DeliveryTarget(channel="telegram", address="12345"),
                DeliveryTarget(channel="email", address="matt@example.com"),
            ),
        )

    def test_resolution_is_deterministic_without_preferences(self) -> None:
        first = Recipient(
            recipient_id="matt",
            display_name="Matt",
            addresses=(
                RecipientAddress(channel="telegram", address="2"),
                RecipientAddress(channel="email", address="matt@example.com"),
                RecipientAddress(channel="telegram", address="1"),
            ),
        )
        second = Recipient(
            recipient_id="matt",
            display_name="Matt",
            addresses=tuple(reversed(first.addresses)),
        )

        self.assertEqual(first.resolve_targets(), second.resolve_targets())
        self.assertEqual(
            first.resolve_targets(),
            (
                DeliveryTarget(channel="email", address="matt@example.com"),
                DeliveryTarget(channel="telegram", address="1"),
                DeliveryTarget(channel="telegram", address="2"),
            ),
        )

    def test_directory_rejects_duplicate_identity_and_fails_closed_for_unknown(self) -> None:
        matt = Recipient(
            recipient_id="matt",
            display_name="Matt",
            addresses=(RecipientAddress(channel="telegram", address="12345"),),
        )

        with self.assertRaisesRegex(ValueError, "duplicate recipient_id"):
            RecipientDirectory((matt, matt))

        directory = RecipientDirectory((matt,))
        self.assertIs(directory.get(" MATT "), matt)
        with self.assertRaisesRegex(KeyError, "unknown recipient_id"):
            directory.get("unknown")

    def test_rejects_blank_required_identity_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "channel is required"):
            RecipientAddress(channel=" ", address="12345")
        with self.assertRaisesRegex(ValueError, "address is required"):
            RecipientAddress(channel="telegram", address=" ")
        with self.assertRaisesRegex(ValueError, "recipient_id is required"):
            Recipient(
                recipient_id=" ",
                display_name="Matt",
                addresses=(),
            )
        with self.assertRaisesRegex(ValueError, "display_name is required"):
            Recipient(
                recipient_id="matt",
                display_name=" ",
                addresses=(),
            )


if __name__ == "__main__":
    unittest.main()
