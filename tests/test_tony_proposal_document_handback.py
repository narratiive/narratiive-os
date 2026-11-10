from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from runtime.tony_proposal_document_handback import TonyProposalHandbackCommandService

FIXTURE_PDF = b"%PDF-1.7\nSAFE TEST ONLY fixture proposal\n%%EOF"


class TonyProposalDocumentHandbackTests(unittest.TestCase):
    def _service(self, dispatchers=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return TonyProposalHandbackCommandService(
            dispatchers or {},
            store_path=Path(tmp.name) / "state.json",
            documents_root=Path(tmp.name) / "documents",
        )

    def _register(self, service, **overrides):
        payload = {
            "brief_id": "brief-abc123",
            "lead_id": "lead-1",
            "company": "SAFE TEST Co",
            "contact": "founder@safe-test.invalid",
            "producer": "Claude",
            "version": "v1",
            "title": "SAFE TEST proposal",
            "filename": "proposal.pdf",
            "content_base64": base64.b64encode(FIXTURE_PDF).decode(),
            "registered_by": "Matt",
        }
        payload.update(overrides)
        return service.register(**payload)

    def test_registration_does_not_imply_approval_and_replay_does_not_duplicate(self):
        service = self._service()
        first = self._register(service)
        self.assertEqual(first.data["execution_status"], "proposal_document_registered")
        self.assertEqual(first.data["proposal_handback"]["approval_status"], "not_accepted_on_registration")

        replay = self._register(service)
        self.assertEqual(replay.data["execution_status"], "proposal_document_already_registered")
        self.assertEqual(len(service.state["documents"]), 1)

    def test_rejects_non_pdf_content(self):
        service = self._service()
        response = self._register(service, content_base64=base64.b64encode(b"not a pdf").decode())
        self.assertEqual(response.data["execution_status"], "proposal_handback_not_a_pdf")
        self.assertEqual(service.state["documents"], {})

    def test_draft_requires_exact_document_approval_first(self):
        service = self._service({"Gmail": Mock()})
        recovery_id = self._register(service).data["proposal_handback"]["recovery_id"]

        response = service.prepare_email_draft(recovery_id, recipient="hello@narratiive.com", subject="SAFE TEST proposal", body="See attached.")

        self.assertEqual(response.data["execution_status"], "proposal_document_approval_required")

    def test_document_approval_then_draft_then_email_approval_separate_gates(self):
        receipt = {"verified": True, "sent": False, "draft_id": "draft-1"}
        gmail = Mock(return_value=receipt)
        service = self._service({"Gmail": gmail})
        recovery_id = self._register(service).data["proposal_handback"]["recovery_id"]

        approved = service.approve_document(recovery_id, approver="Matt", rationale="Reviewed and correct.")
        self.assertEqual(approved.data["execution_status"], "proposal_document_approved")
        replay_approval = service.approve_document(recovery_id, approver="Matt", rationale="Reviewed and correct.")
        self.assertEqual(replay_approval.data["execution_status"], "proposal_document_already_approved")

        drafted = service.prepare_email_draft(recovery_id, recipient="hello@narratiive.com", subject="SAFE TEST proposal", body="See attached.")
        self.assertEqual(drafted.data["execution_status"], "proposal_email_draft_ready")
        self.assertFalse(drafted.data["proposal_email_draft"]["send_authorised"])
        self.assertEqual(gmail.call_args.args[0]["operation"], "create_draft")
        self.assertEqual(service.email_approval_status(recovery_id), "awaiting_approval")

        email_approved = service.approve_email(recovery_id, approver="Matt", rationale="Exact email reviewed.")
        self.assertEqual(email_approved.data["execution_status"], "proposal_email_approved")
        self.assertFalse(email_approved.data["send_enabled"])
        self.assertEqual(service.email_approval_status(recovery_id), "approved")

    def test_changed_recipient_invalidates_prior_email_approval(self):
        receipt = {"verified": True, "sent": False, "draft_id": "draft-1"}
        gmail = Mock(return_value=receipt)
        service = self._service({"Gmail": gmail})
        recovery_id = self._register(service).data["proposal_handback"]["recovery_id"]
        service.approve_document(recovery_id, approver="Matt", rationale="Reviewed.")
        service.prepare_email_draft(recovery_id, recipient="hello@narratiive.com", subject="SAFE TEST proposal", body="See attached.")
        service.approve_email(recovery_id, approver="Matt", rationale="Approved as drafted.")
        self.assertEqual(service.email_approval_status(recovery_id), "approved")

        service.prepare_email_draft(recovery_id, recipient="different@safe-test.invalid", subject="SAFE TEST proposal", body="See attached.")

        self.assertEqual(service.email_approval_status(recovery_id), "invalidated_by_change")

    def test_real_looking_client_recipient_is_not_authorised(self):
        service = self._service({"Gmail": Mock(return_value={"verified": True, "sent": False, "draft_id": "d"})})
        recovery_id = self._register(service).data["proposal_handback"]["recovery_id"]
        service.approve_document(recovery_id, approver="Matt", rationale="Reviewed.")

        response = service.prepare_email_draft(recovery_id, recipient="founder@pimentae.com", subject="Proposal", body="See attached.")

        self.assertEqual(response.data["execution_status"], "proposal_email_recipient_not_authorised")

    def test_document_bytes_changed_on_disk_blocks_draft(self):
        service = self._service({"Gmail": Mock(return_value={"verified": True, "sent": False, "draft_id": "d"})})
        result = self._register(service)
        recovery_id = result.data["proposal_handback"]["recovery_id"]
        service.approve_document(recovery_id, approver="Matt", rationale="Reviewed.")
        Path(result.data["proposal_handback"]["path"]).write_bytes(b"%PDF-1.7\ntampered\n%%EOF")

        response = service.prepare_email_draft(recovery_id, recipient="hello@narratiive.com", subject="Subject", body="Body")

        self.assertEqual(response.data["execution_status"], "proposal_document_changed")


if __name__ == "__main__":
    unittest.main()
