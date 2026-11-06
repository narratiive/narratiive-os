from __future__ import annotations

import unittest

from openclaw.telegram_output_policy import TELEGRAM_SAFE_CHARACTERS, protect_telegram_output


class TelegramOutputPolicyTests(unittest.TestCase):
    def test_short_conversation_remains_unchanged(self) -> None:
        message = "Yes — I’m here. What would you like to work through?"
        self.assertEqual(protect_telegram_output(message), message)

    def test_semantic_review_artefact_is_not_dumped_into_telegram(self) -> None:
        document = (
            "**KATKIN — BLUEPRINT LITE**\n" +
            "**1. SITUATION**\n" + "Substantial evidence. " * 30 +
            "\n**2. CENTRAL DIAGNOSIS**\n" + "A specific diagnosis. " * 30 +
            "\n**3. GROWTH CONSTRAINT**\n" + "A commercial constraint. " * 30 +
            "\n**4. OPPORTUNITY**\n" + "A provisional opportunity. " * 30
        )
        protected = protect_telegram_output(document)
        self.assertEqual(protect_telegram_output(document,literal=True),protected)
        self.assertLess(len(protected), 600)
        self.assertNotIn("Substantial evidence", protected)
        self.assertIn("kept the full review artefact out of Telegram", protected)
        self.assertIn("not been represented as emailed", protected)

    def test_literal_coo_summary_removes_html_and_escapes_legacy_markdown(self):
        import re
        text=protect_telegram_output('<b>Origin</b>: PDF_ready [review]* `exact`',literal=True)
        self.assertNotIn('<b>',text)
        self.assertNotRegex(re.sub(r'\\.', '', text),r'[_*`\[]')
        long=protect_telegram_output('_'*4000,literal=True)
        self.assertLessEqual(len(long),TELEGRAM_SAFE_CHARACTERS)

    def test_hard_envelope_is_only_the_final_safeguard(self) -> None:
        protected = protect_telegram_output("Conversational detail. " * 300)
        self.assertLessEqual(len(protected), TELEGRAM_SAFE_CHARACTERS)
        self.assertIn("shortened this conversational reply", protected)


if __name__ == "__main__":
    unittest.main()
