import unittest

from runtime.executive_delivery_contract import (
    DeliveryTarget,
    ExecutiveMessageContent,
    RenderedMessage,
    TelegramExecutiveRenderer,
)


class DeliveryTargetTests(unittest.TestCase):
    def test_normalises_channel_and_address(self):
        target = DeliveryTarget(channel=" Telegram ", address=" 12345 ")
        self.assertEqual(target.channel, "telegram")
        self.assertEqual(target.address, "12345")

    def test_rejects_unknown_channel_and_missing_address(self):
        with self.assertRaisesRegex(ValueError, "Unsupported delivery channel"):
            DeliveryTarget(channel="carrier-pigeon", address="matt")
        with self.assertRaisesRegex(ValueError, "address is required"):
            DeliveryTarget(channel="telegram", address=" ")


class ExecutiveMessageContentTests(unittest.TestCase):
    def test_builds_structured_brief_from_command_response(self):
        content = ExecutiveMessageContent.from_command_response(
            command="/morning",
            message="Three priorities. One decision waiting.",
            data={"evidence": ["mission-control/2026-07-30"], "status": "healthy"},
        )

        self.assertEqual(content.kind, "brief")
        self.assertEqual(content.title, "Morning executive brief")
        self.assertEqual(content.summary, "Three priorities. One decision waiting.")
        self.assertEqual(content.evidence, ("mission-control/2026-07-30",))
        self.assertEqual(content.data["status"], "healthy")

    def test_materials_are_deduplicated_and_sorted(self):
        content = ExecutiveMessageContent.from_materials(
            ["approval:proposal", " blocker:delivery ", "approval:proposal"]
        )

        self.assertEqual(content.kind, "escalation")
        self.assertEqual(
            content.data["materials"],
            ["approval:proposal", "blocker:delivery"],
        )
        self.assertEqual(
            content.evidence,
            ("approval:proposal", "blocker:delivery"),
        )

    def test_rejects_empty_material_escalation(self):
        with self.assertRaisesRegex(ValueError, "at least one item"):
            ExecutiveMessageContent.from_materials([" "])

    def test_rejects_retired_language_in_executive_brief(self):
        with self.assertRaisesRegex(
            ValueError,
            "retired terminology: Opportunity Card",
        ):
            ExecutiveMessageContent.from_command_response(
                command="morning",
                message="Send the Opportunity Card today.",
                data={"evidence": ["issue:58"]},
            )

    def test_rejects_retired_language_in_rendered_escalation_material(self):
        with self.assertRaisesRegex(
            ValueError,
            "retired terminology: Growth Sprint",
        ):
            ExecutiveMessageContent.from_materials(
                ["approval: Growth Sprint proposal"]
            )


class TelegramExecutiveRendererTests(unittest.TestCase):
    def setUp(self):
        self.renderer = TelegramExecutiveRenderer()

    def test_brief_preserves_compact_canonical_message(self):
        content = ExecutiveMessageContent.from_command_response(
            command="evening",
            message="Two outcomes recorded. No blocker requiring Matt.",
            data={"evidence": ["executive-memory/outcomes/42"]},
        )

        rendered = self.renderer.render(content)

        self.assertEqual(rendered.text, content.summary)
        self.assertEqual(rendered.metadata["kind"], "brief")
        self.assertEqual(
            rendered.metadata["evidence"],
            ["executive-memory/outcomes/42"],
        )

    def test_escalation_renders_bounded_material_digest(self):
        content = ExecutiveMessageContent.from_materials(
            [f"blocker:{index:02d}" for index in range(12)]
        )

        rendered = self.renderer.render(content)

        self.assertTrue(rendered.text.startswith("Material escalation — Matt review needed."))
        self.assertIn("- blocker:00", rendered.text)
        self.assertIn("...and 2 more.", rendered.text)
        self.assertNotIn("- blocker:11", rendered.text)
        self.assertLessEqual(len(rendered.text), 3500)

    def test_rendered_message_rejects_empty_text(self):
        with self.assertRaisesRegex(ValueError, "text is required"):
            RenderedMessage(text=" ")


if __name__ == "__main__":
    unittest.main()
