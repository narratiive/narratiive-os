from __future__ import annotations

import unittest

from runtime.mission_control import ConnectionStatus, MissionControlSnapshot, WorkstreamStatus
from runtime.terminology_policy import TerminologyPolicy
from runtime.tony_executive_commands import TonyExecutiveCommandService


class StubCommandService:
    def __init__(self) -> None:
        self.mission_control_loader = self._snapshot
        self.github_configured = False

    @staticmethod
    def _snapshot() -> MissionControlSnapshot:
        return MissionControlSnapshot(
            generated_at="2026-08-16T14:00:00Z",
            status="healthy",
            progress={"status": "healthy"},
            workstreams=(
                WorkstreamStatus(
                    workstream_id="commercial",
                    title="Commercial",
                    state="functional",
                    owner="Tony",
                    next_action="Prepare the next commercial move",
                    evidence=("crm:commercial",),
                ),
            ),
            connections=(
                ConnectionStatus(name="telegram-bridge", state="connected", evidence="healthy"),
            ),
            approvals_required=(),
            blockers=(),
        )

    def execute(self, command, objects):
        raise AssertionError("executive command should not delegate")


class StubBrief:
    status = "healthy"

    def render_compact(self) -> str:
        return "Morning agency brief\nCommercial: Prepare an Opportunity Card for the strongest lead."

    def to_dict(self) -> dict[str, str]:
        return {"period": "morning", "status": "healthy"}


class StubAgencyBriefService:
    def build(self, state, period):
        return StubBrief()


class TonyExecutiveTerminologyRewriteTests(unittest.TestCase):
    def test_daily_brief_rewrites_retired_language_before_policy_gate(self) -> None:
        policy = TerminologyPolicy(
            {
                "version": "1.1.0",
                "version_note": "Rewrite retired terms instead of blocking useful Tony outputs.",
                "status": "active",
                "approved_terms": [],
                "unsettled_terms": [
                    {
                        "concept": "Personalised prospecting asset",
                        "rule": "Use descriptive language until a product name is approved.",
                    }
                ],
                "retired_terms": [
                    {
                        "term": "Opportunity Card",
                        "replacement": "personalised prospecting asset",
                        "rationale": "Retired terminology",
                    }
                ],
            }
        )
        service = TonyExecutiveCommandService(
            StubCommandService(),
            agency_brief_service=StubAgencyBriefService(),
            terminology_policy_loader=lambda: policy,
            inbound_lead_loader=lambda: (),
        )

        response = service.execute("/morning", ())

        self.assertEqual(response.status, "healthy")
        self.assertNotIn("Opportunity Card", response.message)
        self.assertIn("personalised prospecting asset", response.message)
        self.assertFalse(policy.scan(response.message))


if __name__ == "__main__":
    unittest.main()
