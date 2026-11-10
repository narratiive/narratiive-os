from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.discovery_proposal_mission_control import REQUIRED_STATES, project_discovery_proposal_journey


class DiscoveryProposalMissionControlTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.discovery_path = self.root / "discovery-outcome-tracking.json"
        self.post_discovery_path = self.root / "post-discovery-commercial.json"
        self.handback_path = self.root / "proposal-handback.json"

    def _write(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _project(self, now: datetime):
        return project_discovery_proposal_journey(
            "calendar:pimentae-event-1",
            discovery_tracking_path=self.discovery_path,
            post_discovery_path=self.post_discovery_path,
            proposal_handback_path=self.handback_path,
            now=now,
        )

    def test_no_files_yet_reports_all_states_false_without_erroring(self):
        result = self._project(datetime(2026, 11, 10, tzinfo=timezone.utc))
        self.assertEqual(set(result["states"]), set(REQUIRED_STATES))
        self.assertFalse(any(result["states"].values()))
        self.assertEqual(result["current_stage"], "no_active_discovery_or_proposal_work")
        self.assertFalse(result["states"]["verified_sent"])

    def test_meeting_booked_before_slot_end_then_awaiting_transcript_after(self):
        self._write(self.discovery_path, {
            "active": {"calendar_event_id": "pimentae-event-1", "lead_id": "calendar:pimentae-event-1", "slot": {"start": "2026-11-12T09:00:00+00:00", "end": "2026-11-12T09:30:00+00:00"}},
            "last_completed": None,
        })

        before = self._project(datetime(2026, 11, 11, tzinfo=timezone.utc))
        self.assertTrue(before["states"]["meeting_booked"])
        self.assertFalse(before["states"]["awaiting_transcript"])

        after = self._project(datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc))
        self.assertFalse(after["states"]["meeting_booked"])
        self.assertTrue(after["states"]["awaiting_transcript"])

    def test_transcript_verified_once_last_completed_matches_lead(self):
        self._write(self.discovery_path, {
            "active": None,
            "last_completed": {"calendar_event_id": "pimentae-event-1", "lead_id": "calendar:pimentae-event-1", "evidence_source": "gemini_drive", "reviewed_at": "2026-11-12T11:00:00+00:00"},
        })

        result = self._project(datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc))

        self.assertTrue(result["states"]["transcript_verified"])
        self.assertEqual(result["evidence"]["transcript_verified"]["evidence_source"], "gemini_drive")

    def test_proposal_brief_ready_then_awaiting_external_proposal(self):
        self._write(self.post_discovery_path, {
            "pending": None,
            "last_prepared": {"lead_id": "calendar:pimentae-event-1", "commission_brief": {"brief_id": "brief-abc", "prepared_at": "2026-11-12T12:00:00+00:00"}},
        })

        result = self._project(datetime(2026, 11, 12, 13, 0, tzinfo=timezone.utc))

        self.assertTrue(result["states"]["proposal_brief_ready"])
        self.assertTrue(result["states"]["awaiting_external_proposal"])
        self.assertFalse(result["states"]["proposal_registered"])

    def test_full_journey_through_approved_but_not_sent(self):
        self._write(self.post_discovery_path, {
            "pending": None,
            "last_prepared": {"lead_id": "calendar:pimentae-event-1", "commission_brief": {"brief_id": "brief-abc", "prepared_at": "2026-11-12T12:00:00+00:00"}},
        })
        self._write(self.handback_path, {
            "documents": {"proposal-handback-xyz": {"recovery_id": "proposal-handback-xyz", "brief_id": "brief-abc", "checksum": "chk-1", "producer": "Claude", "version": "v1", "registered_at": "2026-11-12T14:00:00+00:00"}},
            "document_approvals": [{"recovery_id": "proposal-handback-xyz", "checksum": "chk-1", "approver": "Matt", "approved_at": "2026-11-12T14:30:00+00:00"}],
            "drafts": {"proposal-handback-xyz": {"recovery_id": "proposal-handback-xyz", "recipient": "hello@narratiive.com", "subject": "Proposal", "action_digest": "digest-1"}},
            "email_approvals": [{"recovery_id": "proposal-handback-xyz", "action_digest": "digest-1", "approver": "Matt", "approved_at": "2026-11-12T15:00:00+00:00"}],
        })

        result = self._project(datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc))

        self.assertTrue(result["states"]["proposal_registered"])
        self.assertFalse(result["states"]["proposal_awaiting_approval"])
        self.assertFalse(result["states"]["email_draft_awaiting_approval"])
        self.assertTrue(result["states"]["approved_but_not_sent"])
        self.assertFalse(result["states"]["verified_sent"])
        self.assertEqual(result["current_stage"], "approved_but_not_sent")

    def test_email_draft_awaiting_approval_when_draft_changed_after_prior_approval(self):
        self._write(self.post_discovery_path, {
            "pending": None,
            "last_prepared": {"lead_id": "calendar:pimentae-event-1", "commission_brief": {"brief_id": "brief-abc"}},
        })
        self._write(self.handback_path, {
            "documents": {"proposal-handback-xyz": {"recovery_id": "proposal-handback-xyz", "brief_id": "brief-abc", "checksum": "chk-1"}},
            "document_approvals": [{"recovery_id": "proposal-handback-xyz", "checksum": "chk-1"}],
            "drafts": {"proposal-handback-xyz": {"recovery_id": "proposal-handback-xyz", "recipient": "someone-else@safe-test.invalid", "action_digest": "digest-2"}},
            "email_approvals": [{"recovery_id": "proposal-handback-xyz", "action_digest": "digest-1"}],
        })

        result = self._project(datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc))

        self.assertTrue(result["states"]["email_draft_awaiting_approval"])
        self.assertFalse(result["states"]["approved_but_not_sent"])

    def test_proposal_awaiting_approval_before_document_approved(self):
        self._write(self.post_discovery_path, {
            "pending": None,
            "last_prepared": {"lead_id": "calendar:pimentae-event-1", "commission_brief": {"brief_id": "brief-abc"}},
        })
        self._write(self.handback_path, {
            "documents": {"proposal-handback-xyz": {"recovery_id": "proposal-handback-xyz", "brief_id": "brief-abc", "checksum": "chk-1"}},
            "document_approvals": [],
            "drafts": {},
            "email_approvals": [],
        })

        result = self._project(datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc))

        self.assertTrue(result["states"]["proposal_registered"])
        self.assertTrue(result["states"]["proposal_awaiting_approval"])
        self.assertFalse(result["states"]["email_draft_awaiting_approval"])

    def test_mismatched_lead_id_does_not_leak_another_leads_state(self):
        self._write(self.discovery_path, {"active": {"calendar_event_id": "other-event", "lead_id": "calendar:other-event", "slot": {"end": "2026-11-12T09:30:00+00:00"}}, "last_completed": None})

        result = self._project(datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc))

        self.assertFalse(result["states"]["meeting_booked"])
        self.assertFalse(result["states"]["awaiting_transcript"])


if __name__ == "__main__":
    unittest.main()
