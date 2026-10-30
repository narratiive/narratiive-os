from __future__ import annotations

import re
import unittest
from pathlib import Path

from runtime.agency_map import _ROSTER, build_agency_map
from runtime.models import StageRecord, StageStatus, WorkflowState, WorkflowStatus

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _state(
    workflow_id: str,
    run_id: str,
    *,
    status: WorkflowStatus = WorkflowStatus.ACTIVE,
    client_id: str = "northstar-co",
    updated_at: str = "2026-10-30T09:00:00+00:00",
) -> WorkflowState:
    stage = StageRecord("stage-1", "agent-ref", status=StageStatus.RUNNING)
    return WorkflowState(
        workflow_id,
        run_id,
        [stage],
        status=status,
        current_stage_id=stage.stage_id,
        workspace_id="narratiive",
        client_id=client_id,
        entity_id=client_id,
        updated_at=updated_at,
    )


class AgencyMapRosterTests(unittest.TestCase):
    """Guard against roster drift: every declared path/marker must stay real."""

    def test_agent_ids_match_the_canonical_contract_files(self) -> None:
        for spec in _ROSTER:
            contract_text = (_REPO_ROOT / spec.defined_in).read_text(encoding="utf-8")
            match = re.search(r"AI_AGENT_ID:\s*(\S+)", contract_text)
            self.assertIsNotNone(match, f"{spec.defined_in} has no AI_AGENT_ID marker")
            self.assertEqual(spec.agent_id, match.group(1))

    def test_roster_covers_every_specialist_and_the_orchestrator(self) -> None:
        agent_ids = {spec.agent_id for spec in _ROSTER}
        self.assertEqual(
            agent_ids,
            {
                "orchestrator",
                "research_analyst",
                "strategy_director",
                "campaign_world_generator",
                "creative_director",
                "quality_reviewer",
            },
        )


class AgencyMapBuildTests(unittest.TestCase):
    def test_every_agent_is_defined_implemented_tested_and_connected_against_real_repo_evidence(self) -> None:
        entries = build_agency_map()
        self.assertEqual(len(entries), 6)
        for entry in entries:
            self.assertTrue(entry.capability.defined, f"{entry.agent_id}: {entry.capability.defined_evidence}")
            self.assertTrue(entry.capability.implemented, f"{entry.agent_id}: {entry.capability.implemented_evidence}")
            self.assertTrue(entry.capability.tested, f"{entry.agent_id}: {entry.capability.tested_evidence}")
            self.assertTrue(entry.capability.connected, f"{entry.agent_id}: {entry.capability.connected_evidence}")

    def test_without_injected_state_live_verified_is_honestly_false(self) -> None:
        entries = build_agency_map()
        for entry in entries:
            self.assertFalse(entry.capability.live_verified)
            self.assertTrue(
                "no" in entry.capability.live_verified_evidence.lower()
                or "no single canonical" in entry.capability.live_verified_evidence,
                entry.capability.live_verified_evidence,
            )
            self.assertEqual(entry.active_work, ())
            self.assertIsNone(entry.last_verified_activity)

    def test_creative_director_is_connected_for_triage_but_blocked_on_production_execution(self) -> None:
        entries = {entry.agent_id: entry for entry in build_agency_map()}
        creative_director = entries["creative_director"]
        self.assertTrue(creative_director.capability.connected)
        self.assertTrue(creative_director.capability.blocked)
        self.assertIn("Creative Production", creative_director.capability.blocker)

    def test_non_blocked_agents_report_no_blocker(self) -> None:
        entries = {entry.agent_id: entry for entry in build_agency_map()}
        self.assertFalse(entries["research_analyst"].capability.blocked)
        self.assertEqual(entries["research_analyst"].capability.blocker, "")

    def test_injected_in_progress_state_marks_live_verified_and_appears_in_active_work(self) -> None:
        state = _state("growth_blueprint_to_campaign_world", "run-1", status=WorkflowStatus.ACTIVE)
        entries = {entry.agent_id: entry for entry in build_agency_map([state])}
        campaign_world = entries["campaign_world_generator"]

        self.assertTrue(campaign_world.capability.live_verified)
        self.assertEqual(len(campaign_world.active_work), 1)
        self.assertEqual(campaign_world.active_work[0]["run_id"], "run-1")
        self.assertEqual(campaign_world.last_verified_activity, "2026-10-30T09:00:00+00:00")

    def test_completed_state_counts_as_live_verified_but_not_active_work(self) -> None:
        state = _state("growth_blueprint_to_campaign_world", "run-done", status=WorkflowStatus.COMPLETE)
        entries = {entry.agent_id: entry for entry in build_agency_map([state])}
        campaign_world = entries["campaign_world_generator"]

        self.assertTrue(campaign_world.capability.live_verified)
        self.assertEqual(campaign_world.active_work, ())

    def test_state_for_a_different_workflow_does_not_leak_into_an_unrelated_agent(self) -> None:
        state = _state("growth_blueprint_to_campaign_world", "run-1")
        entries = {entry.agent_id: entry for entry in build_agency_map([state])}

        self.assertFalse(entries["creative_director"].capability.live_verified)
        self.assertFalse(entries["research_analyst"].capability.live_verified)

    def test_to_dict_contains_the_expected_shape(self) -> None:
        entry = build_agency_map()[0]
        payload = entry.to_dict()

        self.assertEqual(payload["agent_id"], entry.agent_id)
        self.assertIn("status", payload)
        self.assertIn("defined", payload["status"])
        self.assertIn("live_verified_evidence", payload["status"])
        self.assertIsInstance(payload["active_work"], list)
        self.assertIsInstance(payload["dependencies"], list)


if __name__ == "__main__":
    unittest.main()
