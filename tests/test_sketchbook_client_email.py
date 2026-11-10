from __future__ import annotations

import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from runtime.models import StageRecord, StageStatus, WorkflowState, WorkflowStatus
from runtime.sketchbook_client_email import (
    SketchbookClientEmailError,
    SketchbookClientEmailService,
)
from runtime.tony_workflow_runtime import build_tony_workflow_runtime


class SketchbookClientEmailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.gmail = Mock(
            return_value={
                "verified": True,
                "sent": False,
                "draft_id": "draft-safe-1",
                "message_id": "message-safe-1",
                "html_verified": True,
            }
        )
        self.runtime = build_tony_workflow_runtime(
            self.root,
            workspace_id="test-workspace",
            client_id="test-client",
            dispatchers={"Gmail": self.gmail},
            environ={},
        )
        self.bible_checksum = "b" * 64
        state = WorkflowState(
            workflow_id="campaign_world_to_creative_bible",
            run_id="test-sketchbook-email-run",
            stages=[
                StageRecord(
                    "prepare_creative_bible",
                    "specialist",
                    status=StageStatus.COMPLETED,
                ),
                StageRecord(
                    "triage_creative_bible",
                    "reviewer",
                    status=StageStatus.COMPLETED,
                ),
            ],
            status=WorkflowStatus.COMPLETE,
            approval_required=True,
            approval_status="approved",
            workspace_id="test-workspace",
            client_id="test-client",
            entity_id="test-campaign",
            correlation_id="test-correlation",
            input_payload={"company": "TEST / FICTIONAL — Northstar Foods"},
            approval_history=[
                {
                    "decision": "creative_bible_approval",
                    "approver": "telegram:matt",
                    "human_approval": True,
                    "creative_bible_checksum": self.bible_checksum,
                }
            ],
        )
        self.runtime.runs.repository.save(state)
        self.state = state

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _file(role: str, filename: str, data: bytes) -> dict[str, str]:
        return {
            "role": role,
            "filename": filename,
            "content_base64": base64.b64encode(data).decode("ascii"),
        }

    def inputs(self, *, release_status: str = "unknown") -> dict:
        pdf = b"%PDF-1.4\nTEST SKETCHBOOK"
        pptx = b"PK\x03\x04TEST EDITABLE SKETCHBOOK"
        return {
            "workspace_id": "test-workspace",
            "client_id": "test-client",
            "title": "TEST Northstar Sketchbook",
            "version": "v1",
            "real_client": False,
            "approved_creative_bible_checksum": self.bible_checksum,
            "client_summary": {
                "first_name": "Avery",
                "client_name": "TEST Northstar Foods",
                "recipient_email": "avery@example.test",
                "recipient_verified": True,
                "recipient_evidence_ref": "test-contact-record:1",
                "approved_creative_idea": "The Good Things Table",
                "approved_reason_for_audience": "It makes everyday choices feel generous, social and easy to recognise.",
                "approved_next_step": "We'll bring a clear recommendation for the route to develop.",
                "sender_name": "The Narratiive team",
                "sender_identity_evidence_ref": "test-sender:hello@narratiive.com",
            },
            "release_conditions": {
                "status": release_status,
                "evidence_ref": "test-contract:1" if release_status != "unknown" else "",
            },
            "booking_link": "https://calendar.google.com/calendar/appointments/schedules/test-safe",
            "booking_link_evidence": {"verified": True, "evidence_ref": "test-calendar-config:1"},
            "review_link": "https://drive.google.com/file/d/test-safe/view",
            "review_link_evidence": {
                "permission_verified": True,
                "file_sha256": hashlib.sha256(pdf).hexdigest(),
                "evidence_ref": "test-drive-permission:1",
            },
            "files": [
                self._file("review_pdf", "TEST-Northstar-Sketchbook-v1.pdf", pdf),
                self._file("editable_source", "TEST-Northstar-Sketchbook-v1.pptx", pptx),
            ],
            "quality_assurance": {
                "status": "passed",
                "visual_qa_passed": True,
                "overflow_checked": True,
                "legibility_checked": True,
                "page_count": 5,
                "review_pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                "editable_source_sha256": hashlib.sha256(pptx).hexdigest(),
                "evidence_lineage": ["test-fieldwork:approved", "test-creative-bible:approved"],
            },
        }

    def service(self) -> SketchbookClientEmailService:
        return SketchbookClientEmailService(self.runtime, {"Gmail": self.gmail})

    def test_exact_package_creates_accessible_html_and_plain_preview_without_draft(self) -> None:
        preview = self.service().register_preview(
            self.state,
            self.inputs(),
            principal="telegram:matt",
        )

        self.assertEqual(preview["approval_status"], "pending")
        self.assertIn("TEST Northstar Foods: your story is coming to life", preview["message"]["subject"])
        self.assertIn("The Good Things Table", preview["message"]["plain_text"])
        self.assertIn("The Good Things Table", preview["message"]["html"])
        self.assertIn("Choose a time to explore your Sketchbook", preview["message"]["html"])
        self.assertNotIn("View your Sketchbook", preview["message"]["html"])
        self.assertEqual(self.gmail.call_count, 0)
        self.assertFalse(preview["client_send_authorised"])

    def test_satisfied_release_allows_only_the_exact_review_link_into_preview(self) -> None:
        preview = self.service().register_preview(
            self.state,
            self.inputs(release_status="satisfied"),
            principal="telegram:matt",
        )
        self.assertIn("https://drive.google.com/file/d/test-safe/view", preview["message"]["html"])
        self.assertTrue(preview["release_conditions"]["satisfied"])

        stale = self.inputs(release_status="satisfied")
        stale["review_link_evidence"]["file_sha256"] = "0" * 64
        with self.assertRaisesRegex(SketchbookClientEmailError, "exact-version evidence"):
            self.service().register_preview(self.state, stale, principal="telegram:matt")

    def test_preview_escapes_client_content_and_rejects_unsafe_destinations(self) -> None:
        supplied = self.inputs()
        supplied["client_summary"]["approved_creative_idea"] = "<script>alert(1)</script>"
        preview = self.service().register_preview(self.state, supplied, principal="telegram:matt")
        self.assertNotIn("<script>", preview["message"]["html"])
        self.assertIn("&lt;script&gt;", preview["message"]["html"])

        unsafe = self.inputs()
        unsafe["booking_link"] = "http://localhost:3000/book"
        with self.assertRaisesRegex(SketchbookClientEmailError, "public HTTPS"):
            self.service().register_preview(self.state, unsafe, principal="telegram:matt")

    def test_editable_source_qa_and_verified_recipient_are_mandatory(self) -> None:
        missing_source = self.inputs()
        missing_source["files"] = missing_source["files"][:1]
        with self.assertRaisesRegex(SketchbookClientEmailError, "native editable PPTX"):
            self.service().register_preview(self.state, missing_source, principal="telegram:matt")

        unverified = self.inputs()
        unverified["client_summary"]["recipient_verified"] = False
        with self.assertRaisesRegex(SketchbookClientEmailError, "recipient evidence"):
            self.service().register_preview(self.state, unverified, principal="telegram:matt")

        failed_qa = self.inputs()
        failed_qa["quality_assurance"]["visual_qa_passed"] = False
        with self.assertRaisesRegex(SketchbookClientEmailError, "visual QA"):
            self.service().register_preview(self.state, failed_qa, principal="telegram:matt")

    def test_completed_run_is_not_reopened_and_exact_approval_creates_one_unsent_draft(self) -> None:
        preview = self.service().register_preview(self.state, self.inputs(), principal="telegram:matt")
        receipt = self.service().prepare_draft(
            self.state,
            candidate_id=preview["candidate_id"],
            action_digest=preview["action_digest"],
            approver="telegram:12345",
            rationale="Approve this exact fictional Sketchbook version for client-presentation draft review.",
        )
        replay = self.service().prepare_draft(
            self.state,
            candidate_id=preview["candidate_id"],
            action_digest=preview["action_digest"],
            approver="telegram:12345",
            rationale="Approve this exact fictional Sketchbook version for client-presentation draft review.",
        )

        self.assertFalse(receipt["sent"])
        self.assertFalse(receipt["send_authorised"])
        self.assertFalse(receipt["client_send_boundary_available"])
        self.assertTrue(replay["duplicate_suppressed"])
        self.assertEqual(self.gmail.call_count, 1)
        contract = self.gmail.call_args.args[0]
        self.assertEqual(contract["operation"], "create_draft")
        self.assertEqual(contract["payload"]["recipient_email"], "avery@example.test")
        self.assertIn("html_body", contract["payload"])
        persisted = self.runtime.runs.load_run(self.state.run_id)
        self.assertEqual(persisted.status, WorkflowStatus.COMPLETE)
        self.assertEqual(persisted.approval_status, "approved")
        self.assertEqual(persisted.approval_history[-1]["decision"], "sketchbook_presentation_approval")
        self.assertFalse(persisted.approval_history[-1]["client_send_authorised"])

    def test_corrected_candidate_receives_a_fresh_append_only_approval(self) -> None:
        first = self.service().register_preview(self.state, self.inputs(), principal="telegram:12345")
        self.service().prepare_draft(
            self.state,
            candidate_id=first["candidate_id"],
            action_digest=first["action_digest"],
            approver="telegram:12345",
            rationale="Approve the first exact fictional candidate.",
        )

        corrected_inputs = self.inputs()
        corrected_inputs["client_summary"]["recipient_email"] = "corrected@example.test"
        corrected_inputs["client_summary"]["recipient_evidence_ref"] = "test-contact-record:2"
        corrected = self.service().register_preview(
            self.state,
            corrected_inputs,
            principal="telegram:12345",
        )
        self.service().prepare_draft(
            self.state,
            candidate_id=corrected["candidate_id"],
            action_digest=corrected["action_digest"],
            approver="telegram:12345",
            rationale="Approve the corrected recipient and exact fictional candidate.",
        )

        persisted = self.runtime.runs.load_run(self.state.run_id)
        approvals = [
            item
            for item in persisted.approval_history
            if item.get("decision") == "sketchbook_presentation_approval"
        ]
        self.assertEqual(len(approvals), 2)
        self.assertNotEqual(approvals[0]["candidate_id"], approvals[1]["candidate_id"])
        self.assertEqual(approvals[1]["candidate_id"], corrected["candidate_id"])

    def test_changed_document_or_message_digest_invalidates_approval(self) -> None:
        preview = self.service().register_preview(self.state, self.inputs(), principal="telegram:matt")
        with self.assertRaisesRegex(SketchbookClientEmailError, "stale or incorrect"):
            self.service().prepare_draft(
                self.state,
                candidate_id=preview["candidate_id"],
                action_digest="0" * 64,
                approver="telegram:12345",
                rationale="Synthetic test only.",
            )
        self.assertEqual(self.gmail.call_count, 0)

    def test_failed_gmail_operation_never_produces_a_draft_or_sent_claim(self) -> None:
        preview = self.service().register_preview(self.state, self.inputs(), principal="telegram:matt")
        self.gmail.return_value = {"verified": False, "sent": False}
        with self.assertRaisesRegex(SketchbookClientEmailError, "not verified"):
            self.service().prepare_draft(
                self.state,
                candidate_id=preview["candidate_id"],
                action_digest=preview["action_digest"],
                approver="telegram:12345",
                rationale="Synthetic failure test only.",
            )
        persisted = self.runtime.runs.load_run(self.state.run_id)
        self.assertFalse(persisted.external_action_taken)
        self.assertEqual(persisted.external_action_receipts, [])


if __name__ == "__main__":
    unittest.main()
