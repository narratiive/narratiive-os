from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import Mock, patch

from runtime.synthetic_invitation_preview import PREFIX, build_invitation_preview
from runtime.tony_structured_action_execution import (
    StructuredActionExecutionError, TonyStructuredActionExecutor,
)


class SyntheticInvitationPreviewTests(unittest.TestCase):
    def setUp(self):
        self.config = {PREFIX + key: value for key, value in {
            "WORKSPACE_ID": "synthetic-test",
            "RECIPIENT": "synthetic-prospect@example.net",
            "GMAIL_SENDER": "synthetic-sender@example.org",
            "SENDER_AUTHORITY_REF": "synthetic-authority-1",
            "BOOKING_URL": "https://example.org/synthetic-booking",
            "BOOKING_AUTHORITY_REF": "synthetic-booking-authority-1",
        }.items()}

    def preview(self, **kwargs):
        return build_invitation_preview(workspace_id="synthetic-test", config=self.config, **kwargs)

    def test_exact_preview_and_digest_are_deterministic_without_side_effects(self):
        before = copy.deepcopy(self.config)
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
             patch("builtins.open", side_effect=AssertionError("persistence forbidden")), \
             patch("subprocess.Popen", side_effect=AssertionError("process forbidden")):
            result = self.preview()
            self.assertEqual(result, self.preview())
        self.assertEqual(before, self.config)
        email = result["email_preview"]
        self.assertEqual(email, result["approval_digest"]["email"])
        self.assertEqual(email["to"], "synthetic-prospect@example.net")
        self.assertEqual(email["from"], "synthetic-sender@example.org")
        self.assertIn("[SYNTHETIC TEST]", email["subject"])
        self.assertIn("10-minute", email["body"])
        self.assertIn("informed consent", email["body"])
        self.assertIn(self.config[PREFIX + "BOOKING_URL"], email["body"])
        self.assertEqual(email["cc"] + email["bcc"] + email["attachments"], [])
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertFalse(result["external_action_taken"])
        self.assertFalse(result["approval_granted"])
        self.assertEqual(result["provider_verification"], "not_performed")

    def test_configuration_resolves_at_call_time_and_ignores_credentials(self):
        with patch.dict("os.environ", self.config, clear=True):
            first = build_invitation_preview(workspace_id="synthetic-test")
            with patch.dict("os.environ", {PREFIX + "RECIPIENT": "other@example.net"}):
                second = build_invitation_preview(workspace_id="synthetic-test")
        self.assertNotEqual(first["approval_digest"]["checksum"], second["approval_digest"]["checksum"])
        self.config["UNRELATED_API_KEY"] = "synthetic-secret-do-not-copy"
        self.assertNotIn("synthetic-secret-do-not-copy", json.dumps(self.preview()))

    def test_each_required_input_fails_closed_without_private_value_echo(self):
        for key in self.config:
            config = dict(self.config)
            del config[key]
            with self.subTest(key=key):
                result = build_invitation_preview(workspace_id="synthetic-test", config=config)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["email_preview"])
                self.assertIsNone(result["approval_digest"])
                self.assertIn(key, " ".join(result["blockers"]))
        self.assertEqual(build_invitation_preview(workspace_id="synthetic-test", config={})["status"], "blocked")

    def test_invalid_or_cross_workspace_configuration_is_blocked(self):
        for key, value in (
            ("WORKSPACE_ID", "another-workspace"),
            ("RECIPIENT", "hello@narratiive.com"),
            ("RECIPIENT", "synthetic-sender@example.org"),
            ("RECIPIENT", "one@example.net,two@example.net"),
            ("GMAIL_SENDER", "sender@example.org\r\nBcc: other@example.net"),
            ("BOOKING_URL", "https://example.org/book?token=private"),
            ("BOOKING_URL", "https://user:password@example.org/book"),
            ("BOOKING_URL", "http://example.org/book"),
            ("BOOKING_URL", "https://[invalid"),
            ("SENDER_AUTHORITY_REF", "unsafe\nreference"),
        ):
            with self.subTest(key=key, value=value):
                config = {**self.config, PREFIX + key: value}
                result = build_invitation_preview(workspace_id="synthetic-test", config=config)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["email_preview"])

    def test_digest_changes_for_every_authority_or_email_input(self):
        original = self.preview()["approval_digest"]["checksum"]
        for key in ("RECIPIENT", "GMAIL_SENDER", "BOOKING_URL", "SENDER_AUTHORITY_REF", "BOOKING_AUTHORITY_REF"):
            config = dict(self.config)
            config[PREFIX + key] = config[PREFIX + key].replace("synthetic", "changed")
            result = build_invitation_preview(workspace_id="synthetic-test", config=config)
            self.assertNotEqual(original, result["approval_digest"]["checksum"])

    def test_preview_cannot_dispatch_or_grant_approval(self):
        gmail = Mock(side_effect=AssertionError("sending forbidden"))
        executor = TonyStructuredActionExecutor({"Gmail": gmail})
        preview = self.preview()
        for payload in (preview, {
            **preview, "action": "send synthetic invitation", "surface": "gmail", "kind": "write",
        }):
            with self.assertRaises(StructuredActionExecutionError):
                executor.execute(payload)
        gmail.assert_not_called()


if __name__ == "__main__":
    unittest.main()
