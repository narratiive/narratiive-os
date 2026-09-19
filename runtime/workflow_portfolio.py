from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from runtime.models import WorkflowState
from runtime.workflow_mission_control import workflow_state_name, workflow_state_summary
from runtime.workflow_registry import NARRATIIVE_PRODUCTION_WORKFLOWS


_WORKFLOW_ORDER = tuple(item.workflow_id for item in NARRATIIVE_PRODUCTION_WORKFLOWS)
_WORKFLOW_INDEX = {workflow_id: index for index, workflow_id in enumerate(_WORKFLOW_ORDER)}
_WORKFLOW_LABELS = {
    "growth_diagnostic_to_blueprint_lite": "Blueprint Lite",
    "blueprint_lite_to_discovery_preparation": "Discovery preparation",
    "discovery_evidence_to_growth_sprint_proposal": "Growth Sprint proposal",
    "growth_sprint_to_research_engine": "Research",
    "research_to_growth_blueprint": "Growth Blueprint",
    "growth_blueprint_deliverable_production": "Growth Blueprint deliverable",
    "growth_blueprint_to_campaign_world": "Creative World",
    "campaign_world_to_creative_bible": "Creative Bible",
    "creative_bible_to_asset_production": "Asset production",
    "asset_review_to_delivery_preparation": "Client delivery",
    "delivery_to_follow_up_next_action": "Performance follow-up",
}


def project_client_portfolio(states: Iterable[WorkflowState]) -> tuple[dict[str, Any], ...]:
    """Collapse canonical runs into one read-only operational row per client.

    The run snapshots remain authoritative. This projection deliberately performs
    no recovery, handoff, approval or external action.
    """

    grouped: dict[tuple[str, str], list[WorkflowState]] = defaultdict(list)
    for state in states:
        if state.workflow_id not in _WORKFLOW_INDEX:
            continue
        grouped[(state.workspace_id, state.client_id)].append(state)

    rows = [_project_client(client_states) for client_states in grouped.values()]
    rows.sort(key=lambda item: (item["attention_priority"], item["updated_at"]), reverse=True)
    return tuple(rows)


def _project_client(states: list[WorkflowState]) -> dict[str, Any]:
    states.sort(key=lambda state: (_WORKFLOW_INDEX[state.workflow_id], state.updated_at, state.run_id))
    furthest_index = max(_WORKFLOW_INDEX[state.workflow_id] for state in states)
    furthest = [state for state in states if _WORKFLOW_INDEX[state.workflow_id] == furthest_index]
    current = max(furthest, key=lambda state: (state.updated_at, state.run_id))
    definition = NARRATIIVE_PRODUCTION_WORKFLOWS[furthest_index]
    completed = sorted(
        {state.workflow_id for state in states if state.status.value == "complete"},
        key=_WORKFLOW_INDEX.__getitem__,
    )
    # Historical blocked/rejected attempts remain in the audit trail but must
    # not keep a client red after a later canonical run has progressed.
    blockers = (
        [{
            "run_id": current.run_id,
            "workflow_id": current.workflow_id,
            "reason": current.blocker or "workflow_failed",
        }]
        if current.status.value in {"blocked", "failed"}
        else []
    )
    pending_approvals = (
        [workflow_state_summary(current)]
        if current.approval_status == "pending"
        else []
    )
    next_workflow_id = definition.next_workflow_id
    journey_status, next_action = _journey_status(current, next_workflow_id)
    priority = 3 if blockers else 2 if pending_approvals else 1 if journey_status != "fulfilled" else 0
    campaign_identity = current.input_payload.get("campaign_identity")
    if not isinstance(campaign_identity, dict):
        campaign_identity = {}

    return {
        "workspace_id": current.workspace_id,
        "client_id": current.client_id,
        "company": workflow_state_name(current),
        "campaign_id": str(campaign_identity.get("campaign_id") or ""),
        "journey_status": journey_status,
        "current_gate": furthest_index + 1,
        "total_gates": len(_WORKFLOW_ORDER),
        "current_phase": _WORKFLOW_LABELS[current.workflow_id],
        "current_workflow_id": current.workflow_id,
        "current_run_id": current.run_id,
        "current_state": current.status.value,
        "current_worker": (
            current.stage(current.current_stage_id).agent_ref
            if current.current_stage_id
            else None
        ),
        "completed_gate_count": len(completed),
        "completed_workflow_ids": completed,
        "pending_approvals": pending_approvals,
        "blockers": blockers,
        "next_action": next_action,
        "next_workflow_id": next_workflow_id,
        "human_approval_required": bool(pending_approvals),
        "attention_priority": priority,
        "external_action_taken": any(state.external_action_taken for state in states),
        "updated_at": max(state.updated_at for state in states),
        "run_count": len(states),
    }


def _journey_status(current: WorkflowState, next_workflow_id: str) -> tuple[str, str]:
    if current.status.value in {"blocked", "failed"}:
        return "blocked", current.current_proposed_next_action() or f"Resolve {current.blocker or 'the recorded workflow failure'}."
    if current.approval_status == "pending":
        return "awaiting_human_approval", current.current_proposed_next_action() or "Matt reviews the exact persisted artefact."
    if current.status.value == "complete" and next_workflow_id:
        return "handoff_ready", f"Continue {current.run_id} into {_WORKFLOW_LABELS[next_workflow_id]}."
    if current.status.value == "complete":
        return "fulfilled", "Monitor the agreed measurement window and prepare evidence-backed campaign learning."
    return "in_progress", current.current_proposed_next_action() or "Continue the current authorised internal step."
