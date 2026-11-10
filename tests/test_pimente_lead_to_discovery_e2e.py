from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from runtime.discovery_monitor import TonyDiscoveryMonitor
from runtime.discovery_proposal_mission_control import project_discovery_proposal_journey
from runtime.inbound_leads import InboundLead
from runtime.tony_command_service import CommandResponse
from runtime.tony_discovery_outcome_tracking import TonyDiscoveryOutcomeTrackingCommandService
from runtime.tony_post_discovery_commercial import TonyPostDiscoveryCommercialCommandService


class NoOpUpstream:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("noop", "healthy", "No upstream change.", {"execution_status": "noop"})


class GroundworkStore:
    def __init__(self, record):
        self.record = record

    def get(self, lead_id):
        return self.record if lead_id == "pimente-fictional" else None

    def put(self, lead_id, record):
        self.record = record


class FictionalPimenteLeadToDiscoveryE2ETests(unittest.TestCase):
    def test_fictional_pimente_reaches_internal_proposal_brief_without_any_client_send(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc)
            external_calls = []

            def calendar(contract):
                external_calls.append(("calendar_read", contract["execution_mode"]))
                return {
                    "verified": True,
                    "read_only": True,
                    "mutation_count": 0,
                    "source_id": "calendar:pimente-fictional",
                    "events": [
                        {
                            "event_id": "pimente-fictional-event",
                            "summary": "Pimente Fictional Discovery",
                            "status": "confirmed",
                            "start": "2026-11-10T15:00:00Z",
                            "end": "2026-11-10T15:30:00Z",
                            "attendees": ["hello@narratiive.com", "founder@pimente.invalid"],
                        }
                    ],
                }

            def drive(contract):
                external_calls.append((f"drive_{contract['operation']}", contract["execution_mode"]))
                if contract["operation"] == "search":
                    return {
                        "verified": True,
                        "read_only": True,
                        "mutation_count": 0,
                        "source_id": "drive:search:pimente-fictional",
                        "files": [
                            {
                                "id": "pimente-gemini-notes",
                                "name": "Pimente Fictional Discovery — Notes by Gemini",
                                "modifiedTime": "2026-11-10T15:35:00Z",
                                "webViewLink": "https://docs.google.invalid/pimente-gemini-notes",
                            }
                        ],
                    }
                return {
                    "verified": True,
                    "read_only": True,
                    "mutation_count": 0,
                    "source_id": "drive:file:pimente-gemini-notes",
                    "content": "The fictional Pimente team asked for a paid-visibility and saliency proposal.",
                }

            def claude(contract):
                external_calls.append(("claude_prepare", contract["execution_mode"]))
                return {
                    "summary": "Pimente Fictional wants a deliberate paid-visibility system to turn distribution into recognition and trial.",
                    "recommendation": "Prepare a Fieldwork proposal commission brief for Matt review.",
                    "buying_signals": ["The fictional prospect explicitly requested a proposal."],
                    "agreed_actions": ["Matt will prepare a proposal for review."],
                    "work_product": "evidence-grounded review",
                }

            tracking_path = root / "discovery.json"
            post_path = root / "post-discovery.json"
            handback_path = root / "proposal-handback.json"
            discovery = TonyDiscoveryOutcomeTrackingCommandService(
                NoOpUpstream(),
                dispatchers={"Google Calendar": calendar, "Google Drive": drive, "Claude": claude},
                store_path=tracking_path,
                clock=lambda: now,
                evidence_source="gemini_drive",
            )
            groundwork = GroundworkStore(
                {
                    "canonical_run_id": "pimente-groundwork-run",
                    "state": "awaiting_review",
                    "versions": [
                        {
                            "version": 1,
                            "evidence": {
                                "growth_tension": "Distribution is expanding faster than consumer saliency.",
                                "provisional_opportunity": "Build measurable recognition, trial and repeat purchase.",
                                "sources": ["https://pimente.invalid/public-fictional-evidence"],
                            },
                        }
                    ],
                }
            )
            post_discovery = TonyPostDiscoveryCommercialCommandService(
                discovery,
                dispatchers={},
                store_path=post_path,
                groundwork_store=groundwork,
            )
            lead = InboundLead(
                lead_id="pimente-fictional",
                contact="Synthetic Founder",
                company="Pimente Fictional",
                email="founder@pimente.invalid",
                source="Website",
                disposition="test",
                selected_service="FIELDWORK",
            )
            notifications = []
            monitor = TonyDiscoveryMonitor(
                discovery_service=discovery,
                post_discovery_service=post_discovery,
                leads_loader=lambda: (lead,),
                notify=notifications.append,
                state_path=root / "monitor.json",
                events_path=root / "monitor.jsonl",
                clock=lambda: now,
            )

            result = monitor.run()
            prepared = post_discovery.execute("do that", ())
            mission_control = project_discovery_proposal_journey(
                "pimente-fictional",
                discovery_tracking_path=tracking_path,
                post_discovery_path=post_path,
                proposal_handback_path=handback_path,
            )

            self.assertEqual(result["status"], "post_discovery_proposal_approval_required")
            self.assertEqual(prepared.data["execution_status"], "proposal_brief_ready")
            self.assertIn("Pimente Fictional", prepared.data["proposal_commission_brief"]["copyable_commission"])
            self.assertTrue(mission_control["states"]["transcript_verified"])
            self.assertTrue(mission_control["states"]["proposal_brief_ready"])
            self.assertFalse(mission_control["states"]["verified_sent"])
            self.assertEqual(len(notifications), 2)
            self.assertTrue(all(mode in {"autonomous_read", "autonomous_prepare"} for _, mode in external_calls))
            self.assertFalse(any(name in {"gmail_send", "client_send"} for name, _ in external_calls))


if __name__ == "__main__":
    unittest.main()
