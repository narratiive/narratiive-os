from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.tony_command_service import CommandResponse
from runtime.tony_discovery_outcome_tracking import TonyDiscoveryOutcomeTrackingCommandService


class BookingSyncStub:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse(
            "post_booking_notion_sync",
            "healthy",
            "Notion is now Discovery booked.",
            {
                "execution_status": "discovery_commercial_state_sync_verified",
                "calendar_event_id": "event-123",
                "notion_receipt": "notion-456",
                "discovery_tracking": {
                    "calendar_event_id": "event-123",
                    "lead_id": "lead-1",
                    "contact": "Alex Example",
                    "company": "Example Co",
                    "slot": {
                        "start": "2026-08-18T10:00:00+01:00",
                        "end": "2026-08-18T10:30:00+01:00",
                    },
                },
                "external_action_taken": True,
            },
        )


class NoOpCommandService:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("noop", "healthy", "No upstream state change.", {"execution_status": "noop", "external_action_taken": False})


class TonyDiscoveryOutcomeTrackingTests(unittest.TestCase):
    def _service(self, dispatchers, now, *, evidence_source="fireflies", upstream=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return TonyDiscoveryOutcomeTrackingCommandService(
            upstream if upstream is not None else BookingSyncStub(),
            dispatchers=dispatchers,
            store_path=Path(tmp.name) / "discovery.json",
            clock=lambda: now[0],
            evidence_source=evidence_source,
        )

    def test_verified_booking_sync_starts_tracking_without_reading_meeting_tools(self):
        calls = []
        now = [datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)]
        service = self._service({"Fireflies": lambda contract: calls.append(contract) or {}}, now)

        response = service.execute("do that", ())

        self.assertEqual(response.data["execution_status"], "discovery_outcome_tracking_active")
        self.assertEqual(response.data["discovery_outcome_tracking"]["calendar_event_id"], "event-123")
        self.assertFalse(response.data["discovery_outcome_tracking"]["write_actions_allowed"])
        self.assertEqual(calls, [])
        self.assertIn("tracking the discovery outcome", response.message)

    def test_after_meeting_verified_fireflies_evidence_is_reviewed_by_claude_without_writes(self):
        now = [datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)]
        calls = []

        def fireflies(contract):
            calls.append(("fireflies", contract))
            self.assertEqual(contract["execution_mode"], "autonomous_read")
            self.assertIn("Read only", contract["instruction"])
            return {
                "read_only": True,
                "event_id": "event-123",
                "transcript_id": "transcript-789",
                "transcript": "Alex confirmed a positioning problem, wants a sharper growth story and asked for a concrete proposal next week.",
                "summary": "Discovery attended with a clear request for a concrete proposal.",
            }

        def claude(contract):
            calls.append(("claude", contract))
            self.assertEqual(contract["execution_mode"], "autonomous_prepare")
            self.assertIn("Distinguish meeting attendance from commercial success", contract["instruction"])
            self.assertIn("Do not send anything or update Notion", contract["instruction"])
            return {
                "summary": "The discovery produced a specific positioning need and a clear request for a proposal; this is a positive buying signal, not yet a win.",
                "recommendation": "Prepare a concise proposal grounded in the agreed positioning problem for Matt review.",
                "evidence_gaps": ["Budget and decision timing remain unverified."],
            }

        service = self._service({"Fireflies": fireflies, "Claude": claude}, now)
        service.execute("do that", ())
        now[0] = datetime(2026, 8, 18, 10, 45, tzinfo=timezone.utc)

        response = service.execute("what happened in discovery", ())

        self.assertEqual([name for name, _ in calls], ["fireflies", "claude"])
        self.assertEqual(response.data["execution_status"], "discovery_outcome_review_ready")
        outcome = response.data["discovery_outcome"]
        self.assertEqual(outcome["calendar_event_id"], "event-123")
        self.assertTrue(outcome["approval_required_for_next_write"])
        self.assertIn("Prepare a concise proposal", outcome["recommended_next_action"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("not yet a win", response.message)
        self.assertIn("approval-gated", response.message)

    def test_missing_fireflies_dispatcher_never_infers_meeting_outcome(self):
        now = [datetime(2026, 8, 18, 10, 45, tzinfo=timezone.utc)]
        service = self._service({}, now)
        service.execute("do that", ())

        response = service.execute("check discovery", ())

        self.assertEqual(response.data["execution_status"], "discovery_evidence_dispatcher_unavailable")
        self.assertFalse(response.data["external_action_taken"])
        self.assertIn("cannot verify attendance or meeting content", response.message)
        self.assertIn("No commercial outcome", response.message)

    @staticmethod
    def _pimentae_calendar_event():
        return {
            "event_id": "pimentae-event-1",
            "summary": "Narratiive / Pimentae Discovery",
            "status": "confirmed",
            "start": "2026-11-12T09:00:00+00:00",
            "end": "2026-11-12T09:30:00+00:00",
            "attendees": ["hello@narratiive.com", "founder@pimentae.example"],
            "html_link": "https://calendar.google.invalid/pimentae-event-1",
        }

    def _calendar_search_stub(self, events, calls=None):
        def calendar(contract):
            if calls is not None:
                calls.append(contract)
            self.assertEqual(contract["execution_mode"], "autonomous_read")
            self.assertEqual(contract["operation"], "search")
            return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": "calendar:events", "events": list(events)}
        return calendar

    def test_booking_discovered_from_calendar_without_tony_creating_it(self):
        now = [datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)]
        calls = []
        service = self._service(
            {"Google Calendar": self._calendar_search_stub([self._pimentae_calendar_event()], calls)},
            now,
            upstream=NoOpCommandService(),
        )

        response = service.execute("sync calendar booking Pimentae", ())

        self.assertEqual(response.data["execution_status"], "discovery_outcome_tracking_active")
        tracking = response.data["discovery_outcome_tracking"]
        self.assertEqual(tracking["calendar_event_id"], "pimentae-event-1")
        self.assertEqual(tracking["contact"], "founder@pimentae.example")
        self.assertEqual(tracking["slot"]["start"], "2026-11-12T09:00:00+00:00")
        self.assertFalse(tracking["write_actions_allowed"])
        self.assertFalse(response.data["external_action_taken"])
        self.assertEqual(len(calls), 1)

    def test_replay_does_not_duplicate_tracking(self):
        now = [datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)]
        calls = []
        service = self._service(
            {"Google Calendar": self._calendar_search_stub([self._pimentae_calendar_event()], calls)},
            now,
            upstream=NoOpCommandService(),
        )

        first = service.execute("sync calendar booking Pimentae", ())
        second = service.execute("sync calendar booking Pimentae", ())

        self.assertEqual(first.data["execution_status"], "discovery_outcome_tracking_active")
        self.assertEqual(second.data["execution_status"], "discovery_outcome_tracking_active")
        self.assertIn("did not create a duplicate record", second.message)
        reloaded = TonyDiscoveryOutcomeTrackingCommandService(
            NoOpCommandService(), {}, store_path=service.store_path,
        )
        self.assertEqual(reloaded.state["active"]["calendar_event_id"], "pimentae-event-1")

    def test_ambiguous_calendar_match_is_not_adopted(self):
        now = [datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)]
        events = [self._pimentae_calendar_event(), {**self._pimentae_calendar_event(), "event_id": "pimentae-event-2"}]
        service = self._service({"Google Calendar": self._calendar_search_stub(events)}, now, upstream=NoOpCommandService())

        response = service.execute("sync calendar booking Pimentae", ())

        self.assertEqual(response.data["execution_status"], "discovery_booking_ambiguous")
        self.assertIsNone(service.state["active"])

    def test_conflicting_calendar_adoption_is_refused_not_overwritten(self):
        now = [datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)]
        other_event = {**self._pimentae_calendar_event(), "event_id": "other-event", "summary": "Narratiive / Other Co Discovery"}
        service = self._service(
            {"Google Calendar": self._calendar_search_stub([self._pimentae_calendar_event()])},
            now,
            upstream=NoOpCommandService(),
        )
        service.execute("sync calendar booking Pimentae", ())
        service.dispatchers["Google Calendar"] = self._calendar_search_stub([other_event])

        response = service.execute("sync calendar booking Other Co", ())

        self.assertEqual(response.data["execution_status"], "discovery_booking_tracking_conflict")
        self.assertEqual(service.state["active"]["calendar_event_id"], "pimentae-event-1")

    def _active_from_calendar(self, dispatchers, now):
        service = self._service(dispatchers, now, upstream=NoOpCommandService())
        service.execute("sync calendar booking Pimentae", ())
        return service

    def test_gemini_drive_evidence_is_accepted_when_explicitly_configured(self):
        now = [datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)]
        calendar = self._calendar_search_stub([self._pimentae_calendar_event()])

        def drive(contract):
            if contract["operation"] == "search":
                return {
                    "verified": True, "read_only": True, "mutation_count": 0, "source_id": "drive:search",
                    "files": [{"id": "doc-1", "name": "Pimentae Discovery — Notes by Gemini", "modifiedTime": "2026-11-12T09:35:00Z"}],
                }
            self.assertEqual(contract["target"]["file_id"], "doc-1")
            return {
                "verified": True, "read_only": True, "mutation_count": 0, "source_id": "drive:file:doc-1",
                "content": "Pimentae's founder confirmed a positioning problem and asked for a concrete proposal.",
            }

        claude_calls = []
        def claude(contract):
            claude_calls.append(contract)
            return {"summary": "Clear buying signal; proposal requested.", "recommendation": "Prepare a concise proposal for Matt review.", "work_product": "evidence-grounded review"}

        service = self._service({"Google Calendar": calendar, "Google Drive": drive, "Claude": claude}, now, evidence_source="gemini_drive", upstream=NoOpCommandService())
        service.execute("sync calendar booking Pimentae", ())

        response = service.execute("check discovery", ())

        self.assertEqual(response.data["execution_status"], "discovery_outcome_review_ready")
        outcome = response.data["discovery_outcome"]
        self.assertEqual(outcome["evidence_source"], "gemini_drive")
        self.assertEqual(outcome["meeting_evidence"]["drive_file_id"], "doc-1")
        self.assertEqual(len(claude_calls), 1)

    def test_gemini_drive_similarly_named_document_outside_bounds_is_not_accepted(self):
        now = [datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)]
        calendar = self._calendar_search_stub([self._pimentae_calendar_event()])

        def drive(contract):
            # A similarly named document from an unrelated, much earlier meeting
            # must not be accepted merely because the name matches.
            return {
                "verified": True, "read_only": True, "mutation_count": 0, "source_id": "drive:search",
                "files": [{"id": "stale-doc", "name": "Pimentae Discovery — Notes by Gemini", "modifiedTime": "2026-01-02T09:35:00Z"}],
            }

        service = self._service({"Google Calendar": calendar, "Google Drive": drive}, now, evidence_source="gemini_drive", upstream=NoOpCommandService())
        service.execute("sync calendar booking Pimentae", ())

        response = service.execute("check discovery", ())

        self.assertEqual(response.data["execution_status"], "discovery_evidence_pending")

    def test_gemini_drive_pending_when_no_document_yet(self):
        now = [datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)]
        calendar = self._calendar_search_stub([self._pimentae_calendar_event()])
        drive = lambda contract: {"verified": True, "read_only": True, "mutation_count": 0, "source_id": "drive:search", "files": []}

        service = self._service({"Google Calendar": calendar, "Google Drive": drive}, now, evidence_source="gemini_drive", upstream=NoOpCommandService())
        service.execute("sync calendar booking Pimentae", ())

        response = service.execute("check discovery", ())

        self.assertEqual(response.data["execution_status"], "discovery_evidence_pending")

    def test_fireflies_configured_as_explicit_alternative_is_not_substituted_by_drive(self):
        now = [datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)]
        calendar = self._calendar_search_stub([self._pimentae_calendar_event()])
        drive_calls = []
        drive = lambda contract: drive_calls.append(contract) or {"verified": True, "read_only": True, "mutation_count": 0, "files": []}

        service = self._service({"Google Calendar": calendar, "Google Drive": drive}, now, evidence_source="fireflies", upstream=NoOpCommandService())
        service.execute("sync calendar booking Pimentae", ())

        response = service.execute("check discovery", ())

        self.assertEqual(response.data["execution_status"], "discovery_evidence_dispatcher_unavailable")
        self.assertIn("Fireflies", response.message)
        self.assertEqual(drive_calls, [])


if __name__ == "__main__":
    unittest.main()
