from __future__ import annotations

import re
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from runtime.agency_map import (
    ROSTER_SCOPE_NOTE,
    _ROSTER,
    AgencyMapEntry,
    CapabilityEvidence,
    Evidence,
    build_agency_map,
)
from runtime.models import StageRecord, StageStatus, WorkflowState, WorkflowStatus

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _state(
    workflow_id: str,
    run_id: str,
    stages: list[StageRecord],
    *,
    status: WorkflowStatus = WorkflowStatus.ACTIVE,
    client_id: str = "northstar-co",
    updated_at: str = "2026-10-30T09:00:00+00:00",
) -> WorkflowState:
    return WorkflowState(
        workflow_id,
        run_id,
        stages,
        status=status,
        current_stage_id=stages[-1].stage_id,
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

    def test_no_two_agents_claim_the_same_stage(self) -> None:
        seen: dict[tuple[str, str], str] = {}
        for spec in _ROSTER:
            for ref in spec.canonical_stage_refs:
                self.assertNotIn(
                    ref,
                    seen,
                    f"{ref} claimed by both {seen.get(ref)} and {spec.agent_id}",
                )
                seen[ref] = spec.agent_id

    def test_scope_note_disclaims_completeness_and_agent_invention(self) -> None:
        self.assertIn("not", ROSTER_SCOPE_NOTE.lower())
        self.assertIn("agents/*.md", ROSTER_SCOPE_NOTE)
        self.assertTrue(len(ROSTER_SCOPE_NOTE) > 50)


class AgencyMapImmutabilityTests(unittest.TestCase):
    """Priority: this is a read-only projection, not a second registry."""

    def test_entries_and_evidence_are_frozen(self) -> None:
        entry = build_agency_map()[0]
        with self.assertRaises(FrozenInstanceError):
            entry.agent_id = "tampered"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            entry.capability.defined = Evidence(False, "tampered")  # type: ignore[misc]

    def test_build_agency_map_returns_a_fresh_tuple_each_call(self) -> None:
        first = build_agency_map()
        second = build_agency_map()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)


class AgencyMapStaticEvidenceTests(unittest.TestCase):
    def test_every_agent_is_defined_implemented_tested_and_configured_against_real_repo_evidence(self) -> None:
        entries = build_agency_map()
        self.assertEqual(len(entries), 6)
        for entry in entries:
            self.assertTrue(entry.capability.defined.value, entry.capability.defined.evidence)
            self.assertTrue(entry.capability.implemented.value, entry.capability.implemented.evidence)
            self.assertTrue(entry.capability.tested.value, entry.capability.tested.evidence)
            self.assertTrue(entry.capability.configured.value, entry.capability.configured.evidence)

    def test_configured_evidence_explicitly_disclaims_runtime_proof(self) -> None:
        for entry in build_agency_map():
            self.assertIn(
                "static source match",
                entry.capability.configured.evidence,
                f"{entry.agent_id}: configured evidence must disclaim runtime proof",
            )

    def test_without_a_live_snapshot_runtime_connected_is_unverified_not_false(self) -> None:
        for entry in build_agency_map():
            self.assertIsNone(
                entry.capability.runtime_connected.value,
                f"{entry.agent_id}: runtime_connected must be None (unverified), not False, with no live snapshot",
            )

    def test_live_snapshot_containing_a_worker_id_marks_it_runtime_connected(self) -> None:
        entries = {
            e.agent_id: e
            for e in build_agency_map(live_worker_ids=frozenset({"narratiive-research-engine"}))
        }
        self.assertTrue(entries["research_analyst"].capability.runtime_connected.value)

    def test_live_snapshot_missing_a_worker_id_marks_it_not_runtime_connected(self) -> None:
        entries = {
            e.agent_id: e
            for e in build_agency_map(live_worker_ids=frozenset({"some-other-worker"}))
        }
        self.assertFalse(entries["research_analyst"].capability.runtime_connected.value)

    def test_quality_reviewer_structural_gates_have_no_worker_registry_runtime_check(self) -> None:
        # The deterministic quality-gate functions run in-process; they are not
        # dispatched through the capability worker registry, so a live
        # worker-id snapshot cannot verify them either way.
        entries = {
            e.agent_id: e
            for e in build_agency_map(live_worker_ids=frozenset({"narratiive-senior-strategist-reviewer"}))
        }
        # The senior-strategist review *is* worker-registry-dispatched, so this
        # should report connected -- but it must be via that specific worker_id,
        # not an inferred blanket claim for the whole agent.
        self.assertTrue(entries["quality_reviewer"].capability.runtime_connected.value)


class AgencyMapWithoutInjectedStateTests(unittest.TestCase):
    def test_live_verified_is_honestly_false_with_no_evidence(self) -> None:
        for entry in build_agency_map():
            self.assertFalse(entry.capability.live_verified.value)
            self.assertIn("no persisted WorkflowState", entry.capability.live_verified.evidence)
            self.assertEqual(entry.active_work, ())
            self.assertIsNone(entry.last_verified_activity)


class AgencyMapStageAttributionTests(unittest.TestCase):
    """Priority: attribute activity to an agent only when evidence supports it."""

    def test_generation_stage_completion_verifies_the_generating_specialist_only(self) -> None:
        stage = StageRecord("generate_campaign_world", "claude-anthropic", status=StageStatus.COMPLETED)
        state = _state("growth_blueprint_to_campaign_world", "run-1", [stage])
        entries = {e.agent_id: e for e in build_agency_map([state])}

        self.assertTrue(entries["campaign_world_generator"].capability.live_verified.value)
        self.assertFalse(
            entries["orchestrator"].capability.live_verified.value,
            "the generation stage completing must not verify the Orchestrator's separate triage stage",
        )

    def test_triage_stage_completion_verifies_the_orchestrator_only(self) -> None:
        stage = StageRecord("triage_campaign_world_candidates", "tony-campaign-world-triage", status=StageStatus.COMPLETED)
        state = _state("growth_blueprint_to_campaign_world", "run-1", [stage])
        entries = {e.agent_id: e for e in build_agency_map([state])}

        self.assertTrue(entries["orchestrator"].capability.live_verified.value)
        self.assertFalse(
            entries["campaign_world_generator"].capability.live_verified.value,
            "the triage stage completing must not verify Campaign World Generator's separate generation stage",
        )

    def test_not_started_stage_does_not_count_as_live_verified(self) -> None:
        stage = StageRecord("generate_campaign_world", "claude-anthropic", status=StageStatus.NOT_STARTED)
        state = _state("growth_blueprint_to_campaign_world", "run-1", [stage])
        entries = {e.agent_id: e for e in build_agency_map([state])}

        self.assertFalse(entries["campaign_world_generator"].capability.live_verified.value)

    def test_running_stage_is_live_verified_and_appears_in_active_work_not_completed_count(self) -> None:
        stage = StageRecord("prepare_creative_bible", "claude-anthropic", status=StageStatus.RUNNING)
        state = _state("campaign_world_to_creative_bible", "run-2", [stage])
        entries = {e.agent_id: e for e in build_agency_map([state])}
        creative_director = entries["creative_director"]

        self.assertTrue(creative_director.capability.live_verified.value)
        self.assertEqual(len(creative_director.active_work), 1)
        self.assertEqual(creative_director.active_work[0]["stage_id"], "prepare_creative_bible")
        self.assertEqual(creative_director.last_verified_activity, "2026-10-30T09:00:00+00:00")

    def test_creative_bible_to_asset_production_is_not_attributed_to_creative_director(self) -> None:
        # No agents/*.md contract claims asset-production execution; this must
        # stay unattributed rather than being folded into Creative Director.
        stage = StageRecord("execute_creative_asset_production", "configured-creative-production", status=StageStatus.COMPLETED)
        state = _state("creative_bible_to_asset_production", "run-3", [stage])
        entries = {e.agent_id: e for e in build_agency_map([state])}

        for entry in entries.values():
            self.assertFalse(
                entry.capability.live_verified.value,
                f"{entry.agent_id} must not claim creative_bible_to_asset_production activity",
            )

    def test_to_dict_contains_the_expected_shape(self) -> None:
        entry = build_agency_map()[0]
        payload = entry.to_dict()

        self.assertEqual(payload["agent_id"], entry.agent_id)
        self.assertIn("status", payload)
        for key in ("defined", "implemented", "tested", "configured", "runtime_connected", "live_verified"):
            self.assertIn("value", payload["status"][key])
            self.assertIn("evidence", payload["status"][key])
        self.assertIsInstance(payload["active_work"], list)
        self.assertIsInstance(payload["dependencies"], list)


if __name__ == "__main__":
    unittest.main()
