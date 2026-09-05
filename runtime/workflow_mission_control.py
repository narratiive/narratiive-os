from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from runtime.mission_control import WorkstreamStatus
from runtime.models import WorkflowState


@dataclass(frozen=True, slots=True)
class WorkflowMissionControlView:
    """Read-only projection of durable workflow runs for Mission Control."""

    runs: tuple[dict[str, Any], ...]
    workstreams: tuple[WorkstreamStatus, ...]
    approvals_required: tuple[str, ...]
    domain_values: Mapping[str, Mapping[str, Any]]


def workflow_state_name(state: WorkflowState) -> str:
    payload = state.input_payload
    candidates = (
        payload.get("company"),
        payload.get("company_name"),
        payload.get("company_context", {}).get("name")
        if isinstance(payload.get("company_context"), Mapping)
        else None,
        payload.get("client_context", {}).get("name")
        if isinstance(payload.get("client_context"), Mapping)
        else None,
    )
    return next(
        (str(value).strip() for value in candidates if str(value or "").strip()),
        state.entity_id or state.client_id,
    )


def workflow_state_summary(state: WorkflowState) -> dict[str, Any]:
    """Return the shared executive-safe shape for one persisted workflow run."""

    current = state.stage(state.current_stage_id) if state.current_stage_id else None
    latest_stage = next(
        (stage for stage in reversed(state.stages) if stage.output_artifacts),
        None,
    )
    latest_artifact = latest_stage.output_artifacts[-1] if latest_stage else None
    quality_result = (
        current.quality_result
        if current and current.quality_result
        else latest_stage.quality_result
        if latest_stage and latest_stage.quality_result
        else None
    )
    return {
        "run_id": state.run_id,
        "workflow_id": state.workflow_id,
        "entity_id": state.entity_id,
        "client_id": state.client_id,
        "company": workflow_state_name(state),
        "status": state.status.value,
        "current_step": state.current_stage_id,
        "current_worker": current.agent_ref if current else None,
        "attempt_count": len(current.attempts) if current else 0,
        "quality_passed": quality_result.get("passed") if quality_result else None,
        "approval_status": state.approval_status,
        "approval_required": state.approval_status == "pending",
        "blocker": state.blocker,
        "proposed_next_action": state.current_proposed_next_action(),
        "latest_artefact_id": latest_artifact.artifact_id if latest_artifact else None,
        "latest_artefact": (
            {
                "artifact_id": latest_artifact.artifact_id,
                "artifact_type": latest_artifact.artifact_type,
                "checksum": latest_artifact.checksum,
            }
            if latest_artifact
            else None
        ),
        "external_action_taken": state.external_action_taken,
        "updated_at": state.updated_at,
    }


class WorkflowMissionControlProjector:
    """Project canonical workflow snapshots without mutating or replaying them."""

    def __init__(self, *, workspace_id: str) -> None:
        self.workspace_id = workspace_id.strip()
        if not self.workspace_id:
            raise ValueError("workspace_id must not be empty")

    def project(self, states: Iterable[WorkflowState]) -> WorkflowMissionControlView:
        scoped = []
        for state in states:
            if state.workspace_id != self.workspace_id:
                raise ValueError("workflow state workspace mismatch")
            scoped.append(state)
        scoped.sort(key=lambda state: (state.updated_at, state.run_id), reverse=True)

        summaries = tuple(workflow_state_summary(state) for state in scoped)
        workstreams = tuple(self._workstream(state) for state in scoped)
        approvals = tuple(
            sorted(
                f"workflow:{state.run_id}:{state.current_proposed_next_action() or 'Review the persisted artefact'}"
                for state in scoped
                if state.approval_status == "pending"
            )
        )
        active = sum(
            state.status.value not in {"complete", "failed"} for state in scoped
        )
        blocked = sum(state.status.value == "blocked" for state in scoped)
        completed = sum(state.status.value == "complete" for state in scoped)
        evidence = {
            "health": {
                "state": "connected",
                "evidence": [f"workflow_runtime:runs:{len(scoped)}"],
            },
            "active_work": {
                "state": "connected",
                "evidence": [f"workflow_runtime:active:{active}"],
            },
            "approvals": {
                "state": "connected",
                "evidence": [f"workflow_runtime:approvals:{len(approvals)}"],
            },
            "risks": {
                "state": "connected",
                "evidence": [f"workflow_runtime:blockers:{blocked}"],
            },
            "recommended_focus": {
                "state": "connected",
                "evidence": ["workflow_runtime:proposed_next_actions"],
            },
            "recent_wins": {
                "state": "connected",
                "evidence": [f"workflow_runtime:complete:{completed}"],
            },
        }
        return WorkflowMissionControlView(
            runs=summaries,
            workstreams=workstreams,
            approvals_required=approvals,
            domain_values=evidence,
        )

    @staticmethod
    def _workstream(state: WorkflowState) -> WorkstreamStatus:
        current = state.stage(state.current_stage_id) if state.current_stage_id else None
        status = state.status.value
        workstream_state = {
            "active": "known",
            "awaiting_approval": "tested",
            "complete": "used",
            "blocked": "blocked",
            "failed": "blocked",
        }.get(status, "unknown")
        blocker = state.blocker
        if workstream_state == "blocked" and not blocker:
            blocker = "workflow_failed"
        next_action = state.current_proposed_next_action()
        if not next_action:
            if status == "complete":
                next_action = "No pending action; this workflow run is complete."
            elif blocker:
                next_action = f"Resolve {blocker}."
            else:
                next_action = "Continue the current authorised internal workflow step."
        evidence = [f"workflow_run:{state.run_id}", f"workflow_status:{status}"]
        for stage in reversed(state.stages):
            if stage.output_artifacts:
                evidence.append(f"artefact:{stage.output_artifacts[-1].artifact_id}")
                break
        return WorkstreamStatus(
            workstream_id=f"workflow:{state.run_id}",
            title=f"{workflow_state_name(state)} — {state.workflow_id}",
            state=workstream_state,
            owner=current.agent_ref if current else "Tony",
            next_action=next_action,
            evidence=tuple(evidence),
            blocker=blocker,
            last_updated_at=state.updated_at,
        )
