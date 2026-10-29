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
            "COMPANY_NAME": "Synthetic Company",
            "ENTITY_ID": "synthetic-entity-1",
            "DISCOVERY_PREPARATION_REF": "artifact-synthetic-discovery-v1",
            "MEETING_DURATION_MINUTES": "30",
            "INSIGHTS_JSON": json.dumps([
                {"observation": "Validated fixture ambition.", "question": "What would make it more useful?", "source_ref": "fixture:1"},
                {"observation": "Validated fixture audience.", "question": "Who matters most here?", "source_ref": "fixture:2"},
                {"observation": "Validated fixture distinction.", "question": "What should be unmissable?", "source_ref": "fixture:3"},
            ]),
            "FOUNDER_SIGNATURE": "Matt Franks\nFounder, Narratiive",
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
        self.assertIn("30-minute", email["body"])
        self.assertIn("Google Meet", email["body"])
        self.assertIn("Gemini notes", email["body"])
        self.assertIn("optional fallback", email["body"])
        self.assertIn("Synthetic Company", email["body"])
        self.assertIn(self.config[PREFIX + "BOOKING_URL"], email["body"])
        self.assertEqual(result["approval_digest"]["entity_id"], "synthetic-entity-1")
        self.assertEqual(result["approval_digest"]["meeting_duration_minutes"], 30)
        self.assertIn("Thanks for reaching out. We've had an interesting look around", email["body"])
        for section in ("THE BIGGER AMBITION", "THE PEOPLE WHO MATTER", "WHAT MAKES YOU UNMISSABLE"):
            self.assertIn(section, email["body"])
            self.assertIn(section, email["html"])
        self.assertIn("Book a 30-minute conversation", email["html"])
        self.assertNotIn("fixture:1", email["html"])
        self.assertNotIn("fixture:1", email["body"])
        self.assertEqual(len(result["approval_digest"]["validated_insights"]), 3)
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

    def test_editing_preview_does_not_change_approval_snapshot(self):
        result = self.preview()
        digest = copy.deepcopy(result["approval_digest"])
        result["email_preview"]["body"] = "Changed invitation"
        result["email_preview"]["cc"].append("other@example.net")
        self.assertEqual(result["approval_digest"], digest)
        self.assertEqual(self.preview()["approval_digest"], digest)

    def test_control_characters_are_rejected_before_trimming(self):
        for key, value in self.config.items():
            for control in ("\r", "\n", "\t", "\x00", "\x7f"):
                if key == PREFIX + "FOUNDER_SIGNATURE" and control == "\n":
                    continue
                with self.subTest(key=key, control=repr(control)):
                    config = {**self.config, key: control + value + control}
                    result = build_invitation_preview(workspace_id="synthetic-test", config=config)
                    self.assertEqual(result["status"], "blocked")
                    self.assertIsNone(result["email_preview"])
                    self.assertIsNone(result["approval_digest"])
                    self.assertIn(key, " ".join(result["blockers"]))

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
            ("ENTITY_ID", "unsafe entity"),
            ("MEETING_DURATION_MINUTES", "10"),
        ):
            with self.subTest(key=key, value=value):
                config = {**self.config, PREFIX + key: value}
                result = build_invitation_preview(workspace_id="synthetic-test", config=config)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["email_preview"])

    def test_digest_changes_for_every_authority_or_email_input(self):
        original = self.preview()["approval_digest"]["checksum"]
        changed_values = {
            "RECIPIENT": "changed-prospect@example.net",
            "GMAIL_SENDER": "changed-sender@example.org",
            "BOOKING_URL": "https://example.org/changed-booking",
            "SENDER_AUTHORITY_REF": "changed-authority",
            "BOOKING_AUTHORITY_REF": "changed-booking-authority",
            "COMPANY_NAME": "Changed Company",
            "ENTITY_ID": "changed-entity",
            "DISCOVERY_PREPARATION_REF": "artifact-changed-discovery-v1",
        }
        for key, changed_value in changed_values.items():
            config = dict(self.config)
            config[PREFIX + key] = changed_value
            result = build_invitation_preview(workspace_id="synthetic-test", config=config)
            self.assertNotEqual(original, result["approval_digest"]["checksum"])

        invalid_duration = {**self.config, PREFIX + "MEETING_DURATION_MINUTES": "10"}
        result = build_invitation_preview(workspace_id="synthetic-test", config=invalid_duration)
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["approval_digest"])

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

    def test_missing_or_unsafe_insights_block_personalised_preview(self):
        missing = {**self.config, PREFIX + "INSIGHTS_JSON": "[]"}
        self.assertEqual(build_invitation_preview(workspace_id="synthetic-test", config=missing)["status"], "blocked")
        incomplete = {**self.config, PREFIX + "INSIGHTS_JSON": json.dumps([
            {"observation": "One.", "question": "Why?", "source_ref": "fixture:1"},
            {"observation": "Two.", "question": "Why?", "source_ref": "fixture:2"},
        ])}
        self.assertEqual(build_invitation_preview(workspace_id="synthetic-test", config=incomplete)["status"], "blocked")
        unsafe = {**self.config, PREFIX + "INSIGHTS_JSON": json.dumps([
            {"observation": "<script>", "question": "Why?", "source_ref": "fixture:1"},
            {"observation": "Two.", "question": "Why?", "source_ref": "fixture:2"},
            {"observation": "Three.", "question": "Why?", "source_ref": "fixture:3"},
        ])}
        result = build_invitation_preview(workspace_id="synthetic-test", config=unsafe)
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertNotIn("<script>", result["email_preview"]["html"])


if __name__ == "__main__":
    unittest.main()
