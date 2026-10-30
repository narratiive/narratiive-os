from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from runtime.models import StageRecord, WorkflowState
from runtime.repositories import FileWorkflowRunRepository
from runtime.synthetic_invitation_preview import DiscoveryEvidenceResolver, PREFIX, build_invitation_preview
from runtime.tony_structured_action_execution import (
    StructuredActionExecutionError, TonyStructuredActionExecutor,
)
from runtime.workflow_execution_coordinator import FileWorkflowArtifactStore


class SyntheticInvitationPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runs = FileWorkflowRunRepository(self.root / "runs", workspace_id="synthetic-test", client_id="synthetic-client")
        self.artifacts = FileWorkflowArtifactStore(self.root / "artifacts")
        self.evidence_resolver = DiscoveryEvidenceResolver(self.runs, self.artifacts.root)
        self.preparation = self.persist_discovery_preparation()
        self.config = {PREFIX + key: value for key, value in {
            "WORKSPACE_ID": "synthetic-test",
            "RECIPIENT": "synthetic-prospect@example.net",
            "GMAIL_SENDER": "synthetic-sender@example.org",
            "SENDER_AUTHORITY_REF": "synthetic-authority-1",
            "BOOKING_URL": "https://example.org/synthetic-booking",
            "BOOKING_AUTHORITY_REF": "synthetic-booking-authority-1",
            "COMPANY_NAME": "Synthetic Company",
            "ENTITY_ID": "synthetic-entity-1",
            "DISCOVERY_PREPARATION_REF": self.preparation,
            "MEETING_DURATION_MINUTES": "30",
            "INSIGHTS_JSON": json.dumps([
                {"observation": "Validated fixture ambition.", "question": "What would make it more useful?", "source_ref": "fixture:1"},
                {"observation": "Validated fixture audience.", "question": "Who matters most here?", "source_ref": "fixture:2"},
                {"observation": "Validated fixture distinction.", "question": "What should be unmissable?", "source_ref": "fixture:3"},
            ]),
            "FOUNDER_SIGNATURE": "Matt Franks\nFounder, Narratiive",
        }.items()}

    def tearDown(self):
        self.temporary.cleanup()

    def preview(self, **kwargs):
        resolver = kwargs.pop("discovery_evidence_resolver", self.evidence_resolver)
        config = kwargs.pop("config", self.config)
        return build_invitation_preview(
            workspace_id="synthetic-test",
            config=config,
            discovery_evidence_resolver=resolver,
            **kwargs,
        )

    def persist_discovery_preparation(self, *, entity_id="synthetic-entity-1", source_refs=None):
        state = WorkflowState(
            workflow_id="blueprint_lite_to_discovery_preparation",
            run_id=f"discovery-{entity_id}",
            stages=[StageRecord("prepare_discovery", "Claude")],
            workspace_id="synthetic-test",
            client_id="synthetic-client",
            entity_id=entity_id,
        )
        artifact = self.artifacts.persist(
            state,
            "prepare_discovery",
            {"evidence_lineage": [
                {"claim": "Synthetic source lineage", "source_refs": source_refs or ["fixture:1", "fixture:2", "fixture:3"]}
            ]},
        )
        state.stage("prepare_discovery").output_artifacts = [artifact]
        self.runs.save(state)
        return artifact.artifact_id

    def persist_discovery_attempt(self, *, entity_id):
        state = WorkflowState(
            workflow_id="blueprint_lite_to_discovery_preparation",
            run_id=f"attempt-{entity_id}",
            stages=[StageRecord("prepare_discovery", "Claude")],
            workspace_id="synthetic-test",
            client_id="synthetic-client",
            entity_id=entity_id,
        )
        artifact = self.artifacts.persist_attempt(
            state, "prepare_discovery", {"evidence_lineage": [
                {"claim": "Unaccepted attempt", "source_refs": ["fixture:1"]}
            ]}, attempt_number=1,
        )
        state.stage("prepare_discovery").output_artifacts = [artifact]
        self.runs.save(state)
        return artifact.artifact_id

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
            first = build_invitation_preview(
                workspace_id="synthetic-test", discovery_evidence_resolver=self.evidence_resolver
            )
            with patch.dict("os.environ", {PREFIX + "RECIPIENT": "other@example.net"}):
                second = build_invitation_preview(
                    workspace_id="synthetic-test", discovery_evidence_resolver=self.evidence_resolver
                )
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
                    result = self.preview(config=config)
                    self.assertEqual(result["status"], "blocked")
                    self.assertIsNone(result["email_preview"])
                    self.assertIsNone(result["approval_digest"])
                    self.assertIn(key, " ".join(result["blockers"]))

    def test_each_required_input_fails_closed_without_private_value_echo(self):
        for key in self.config:
            config = dict(self.config)
            del config[key]
            with self.subTest(key=key):
                result = self.preview(config=config)
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["email_preview"])
                self.assertIsNone(result["approval_digest"])
                self.assertIn(key, " ".join(result["blockers"]))
        self.assertEqual(self.preview(config={})["status"], "blocked")

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
                result = self.preview(config=config)
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
            result = self.preview(config=config)
            if key in {"ENTITY_ID", "DISCOVERY_PREPARATION_REF"}:
                self.assertEqual(result["status"], "blocked")
            else:
                self.assertNotEqual(original, result["approval_digest"]["checksum"])

        invalid_duration = {**self.config, PREFIX + "MEETING_DURATION_MINUTES": "10"}
        result = self.preview(config=invalid_duration)
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
        self.assertEqual(self.preview(config=missing)["status"], "blocked")
        one_insight = {**self.config, PREFIX + "INSIGHTS_JSON": json.dumps([
            {"observation": "One.", "question": "Why?", "source_ref": "fixture:1"},
        ])}
        one_preview = self.preview(config=one_insight)
        self.assertEqual(one_preview["status"], "awaiting_approval")
        self.assertEqual(len(one_preview["approval_digest"]["validated_insights"]), 1)
        self.assertNotIn("three things", one_preview["email_preview"]["subject"].casefold())
        self.assertNotIn("three things", one_preview["email_preview"]["html"].casefold())
        for count in (2, 3):
            preview = self.preview(config={
                **self.config,
                PREFIX + "INSIGHTS_JSON": json.dumps([
                    {"observation": f"Observation {index}.", "question": f"Question {index}?", "source_ref": f"fixture:{index}"}
                    for index in range(1, count + 1)
                ]),
            })
            self.assertEqual(preview["status"], "awaiting_approval")
            self.assertNotIn("three things", preview["email_preview"]["html"].casefold())
        incomplete = {**self.config, PREFIX + "INSIGHTS_JSON": json.dumps([
            {"observation": "One.", "question": "Why?", "source_ref": "fixture:1"},
            {"observation": "Two.", "question": "Why?", "source_ref": "fixture:2"},
            {"observation": "Three.", "question": "Why?", "source_ref": "fixture:3"},
            {"observation": "Four.", "question": "Why?", "source_ref": "fixture:3"},
        ])}
        self.assertEqual(self.preview(config=incomplete)["status"], "blocked")
        forged = {**self.config, PREFIX + "INSIGHTS_JSON": json.dumps([
            {"observation": "One.", "question": "Why?", "source_ref": "forged:source"},
        ])}
        self.assertEqual(self.preview(config=forged)["status"], "blocked")
        unsafe = {**self.config, PREFIX + "INSIGHTS_JSON": json.dumps([
            {"observation": "<script>", "question": "Why?", "source_ref": "fixture:1"},
            {"observation": "Two.", "question": "Why?", "source_ref": "fixture:2"},
            {"observation": "Three.", "question": "Why?", "source_ref": "fixture:3"},
        ])}
        result = self.preview(config=unsafe)
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertNotIn("<script>", result["email_preview"]["html"])

    def test_authoritative_evidence_must_match_scope_preparation_and_integrity(self):
        self.assertEqual(
            build_invitation_preview(workspace_id="synthetic-test", config=self.config)["status"],
            "blocked",
        )
        forged_record = {
            "workspace_id": "synthetic-test", "entity_id": "synthetic-entity-1",
            "discovery_preparation_ref": self.preparation, "source_refs": ["fixture:1"],
        }
        self.assertEqual(
            self.preview(discovery_evidence_resolver=lambda **_kwargs: forged_record)["status"],
            "blocked",
        )
        artifact = self.runs.load("discovery-synthetic-entity-1").stage("prepare_discovery").output_artifacts[0]
        Path(artifact.location).write_text('{"evidence_lineage":[]}', encoding="utf-8")
        self.assertEqual(self.preview()["status"], "blocked")
        attempt_entity = "attempt-only"
        attempt_ref = self.persist_discovery_attempt(entity_id=attempt_entity)
        self.assertEqual(self.preview(config={
            **self.config,
            PREFIX + "ENTITY_ID": attempt_entity,
            PREFIX + "DISCOVERY_PREPARATION_REF": attempt_ref,
        })["status"], "blocked")

    def test_founder_approved_loom_loft_copy_is_exact_and_isolated(self):
        config = {
            **self.config,
            PREFIX + "COMPANY_NAME": "Loom Loft",
            PREFIX + "ENTITY_ID": "inbound-d1b96a67",
        }
        loom_preparation = self.persist_discovery_preparation(entity_id="inbound-d1b96a67")
        email = self.preview(
            config={**config, PREFIX + "DISCOVERY_PREPARATION_REF": loom_preparation}
        )["email_preview"]
        expected = (
            "Hi [First Name],\n\n"
            "Thanks for getting in touch. We've been having a look around Loom Loft, and we're intrigued.\n\n"
            "Furniture is an interesting business. People might come looking for a sofa, but what they're really imagining is a different version of home. And that creates some exciting possibilities for a brand with ambition.\n\n"
            "We've got a few thoughts. But we'd much rather explore them with you than jump to conclusions.\n\n"
            "THREE THINGS WE'D LOVE TO EXPLORE\n\n"
            "01 / HOW BIG COULD THIS GET?\n"
            "Forget next quarter's targets for a moment. Where do you really want to take Loom Loft? And what's stopping you getting there faster?\n\n"
            "02 / WHO COULD FALL IN LOVE WITH IT?\n"
            "There's a difference between reaching more people and becoming the brand that the right people actively seek out. Who are those people for Loom Loft?\n\n"
            "03 / WHAT COULD MAKE YOU FAMOUS?\n"
            "Not just another furniture retailer. A brand people recognise, remember and recommend. What could Loom Loft become known for?\n\n"
            "LET'S FIND OUT TOGETHER.\n\n"
            "I'd love to spend 30 minutes exploring what's possible. We'll bring an outside perspective, you bring the inside story, and we'll see where the interesting opportunities emerge.\n\n"
            "No pitch deck. No obligation. Just a good conversation.\n\n"
            "→ Book a 30-minute conversation\nhttps://example.org/synthetic-booking\n\n"
            "Looking forward to meeting you.\n\n"
            "Matt Franks\nFounder, Narratiive"
        )
        self.assertEqual(email["body"], expected)
        self.assertEqual(email["subject"], "Loom Loft — what could we build together?")
        self.assertIn("Loom Loft —<br>what could we<br>build together?", email["html"])
        self.assertIn("THREE THINGS WE'D LOVE TO EXPLORE", email["html"])
        self.assertIn("Book a 30-minute conversation&nbsp; →", email["html"])
        self.assertNotIn("The submitted diagnostic", email["html"])

        other_preparation = self.persist_discovery_preparation(entity_id="another-entity")
        non_synthetic = self.preview(
            config={
                **config,
                PREFIX + "ENTITY_ID": "another-entity",
                PREFIX + "DISCOVERY_PREPARATION_REF": other_preparation,
            },
        )["email_preview"]
        self.assertNotEqual(non_synthetic["body"], expected)


if __name__ == "__main__":
    unittest.main()
