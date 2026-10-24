from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.inbound_leads import InboundLead
from runtime.executive_visibility import ExecutiveVisibilityPolicy
from runtime.mission_control import VALID_CONNECTION_STATES
from runtime.models import ArtifactRef, StageRecord, WorkflowState
from runtime.repositories import WorkflowEvent
from runtime.workflow_mission_control import workflow_state_name


LIFECYCLE = ("lead", "blueprint_lite", "discovery", "proposal", "delivery", "commercial", "complete")
WORKFLOW_STAGE = {
    "growth_diagnostic_to_blueprint_lite": "blueprint_lite",
    "blueprint_lite_to_discovery_preparation": "discovery",
    "discovery_evidence_to_growth_sprint_proposal": "proposal",
}
DELIVERY_STEPS = {
    "growth_sprint_to_research_engine": "Research",
    "research_to_strategic_synthesis": "Strategic Synthesis",
    "strategic_synthesis_to_strategy_thesis": "Strategy Thesis",
    "research_to_growth_blueprint": "Growth Blueprint",
    "strategy_thesis_to_growth_blueprint": "Growth Blueprint",
    "growth_blueprint_to_campaign_world": "Campaign World",
    "campaign_world_to_creative_bible": "Creative Director's Bible",
}
LEAD_STAGE = {
    "blueprint lite": "blueprint_lite", "discovery": "discovery", "meeting": "discovery",
    "proposal": "proposal", "delivery": "delivery", "invoice": "commercial",
    "commercial": "commercial", "complete": "complete", "completed": "complete",
}
ARTEFACT_NAMES = {
    "growth_diagnostic_to_blueprint_lite": "Blueprint Lite",
    "blueprint_lite_to_discovery_preparation": "Discovery Preparation",
    "discovery_evidence_to_growth_sprint_proposal": "Growth Sprint Proposal",
    "growth_sprint_to_research_engine": "Research Dossier",
    "research_to_strategic_synthesis": "Strategic Synthesis",
    "strategic_synthesis_to_strategy_thesis": "Strategy Thesis",
    "research_to_growth_blueprint": "Growth Blueprint",
    "strategy_thesis_to_growth_blueprint": "Growth Blueprint",
    "growth_blueprint_to_campaign_world": "Campaign World",
    "campaign_world_to_creative_bible": "Creative Director's Bible",
}


class FileWorkflowEvidenceReader:
    """Read append-only evidence adjacent to canonical workflow snapshots."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def events(self, state: WorkflowState) -> tuple[WorkflowEvent, ...]:
        scope = hashlib.sha256(f"{state.workspace_id}:{state.client_id}".encode()).hexdigest()[:24]
        path = self.root / scope / "events" / f"{state.run_id}.jsonl"
        if Path(state.run_id).name != state.run_id or not path.is_file():
            return ()
        path.resolve().relative_to((self.root / scope / "events").resolve())
        result: list[WorkflowEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event = WorkflowEvent.from_dict(json.loads(line))
                if event.workspace_id == state.workspace_id and event.run_id == state.run_id:
                    result.append(event)
        return tuple(result)


class OperatorMissionControlProjector:
    """Executive-safe projection of canonical lead and workflow truth."""

    def __init__(
        self,
        *,
        workflow_root: str | Path,
        workflow_workspace_id: str,
        worker_timeout_seconds: Mapping[str, int] | None = None,
    ) -> None:
        self.workflow_root = Path(workflow_root).resolve()
        self.workflow_workspace_id = workflow_workspace_id
        self.evidence = FileWorkflowEvidenceReader(self.workflow_root)
        self.visibility = ExecutiveVisibilityPolicy()
        self.worker_timeout_seconds = {
            str(capability): int(seconds)
            for capability, seconds in (worker_timeout_seconds or {}).items()
            if int(seconds) > 0
        }

    def project(
        self,
        *,
        states: Iterable[WorkflowState],
        leads: Iterable[InboundLead],
        system_snapshot: Mapping[str, Any] | None = None,
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        now = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        all_states = tuple(states)
        all_leads = tuple(leads)
        if any(state.workspace_id != self.workflow_workspace_id for state in all_states):
            raise ValueError("workflow state workspace mismatch")
        visible_leads = self.visibility.visible_leads(all_leads)
        policy_states = self.visibility.visible_workflows(all_states, all_leads)
        scoped = tuple(state for state in policy_states if not self._explicit_synthetic(state))
        visible_keys = {
            *(lead.lead_id for lead in visible_leads),
            *(state.client_id or state.entity_id for state in scoped),
        }
        all_keys = {
            *(lead.lead_id for lead in all_leads),
            *(state.client_id or state.entity_id for state in all_states),
        }
        lead_by_id = {lead.lead_id: lead for lead in visible_leads}
        grouped: dict[str, list[WorkflowState]] = defaultdict(list)
        for state in scoped:
            grouped[state.client_id or state.entity_id].append(state)
        for lead in visible_leads:
            grouped.setdefault(lead.lead_id, [])

        opportunities = [self._opportunity(key, runs, lead_by_id.get(key), now) for key, runs in grouped.items()]
        opportunities.sort(key=lambda item: (item["updated_at"], item["company"]), reverse=True)
        live = [item for item in opportunities if not item["synthetic"]]
        active = [item for item in live if item["lifecycle_stage"] != "complete"]
        needs_you = [self._queue_item(item) for item in live if item["requires_matt"]]
        attention = [item for item in live if item["attention_state"] in {"blocked", "waiting_externally", "failed", "stale", "stalled", "unverified"}]
        activity = sorted(
            (event for item in opportunities for event in item["activity"]),
            key=lambda item: item["occurred_at"], reverse=True,
        )[:30]
        running = sum(item["attention_state"] == "running" for item in active)
        connections = self._connections(system_snapshot or {})
        return {
            "schema_version": 1,
            "generated_at": now,
            "stale_after_seconds": 45,
            "summary": {
                "active_opportunities": len(active),
                "waiting_for_matt": len(needs_you),
                "blocked": sum(item["attention_state"] == "blocked" for item in active),
                "running_autonomously": running,
                "synthetic_hidden": len(all_keys - visible_keys),
            },
            "system": {
                "status": str((system_snapshot or {}).get("status") or "unknown"),
                "connections": connections,
            },
            "lifecycle": list(LIFECYCLE),
            "opportunities": opportunities,
            "needs_you": needs_you,
            "attention": attention,
            "activity": activity,
            "operations": {
                "runs": [{**run, "company": item["company"], "opportunity_id": item["id"]} for item in opportunities for run in item["runs"]],
                "blockers": [
                    {"company": item["company"], "opportunity_id": item["id"],
                     "owner": run["owner"], "reason": reason, "run_id": run["run_id"],
                     "next_action": run["next_action"], "status": "open"}
                    for item in opportunities for run in item["runs"]
                    for reason in run["issues"]
                ],
                "tony": {"state": "unknown", "evidence": "Workflow activity is not a live Tony heartbeat."},
            },
            "capabilities": {"read_only": True, "approvals": False, "external_actions": False},
        }

    def _opportunity(
        self,
        key: str,
        runs: list[WorkflowState],
        lead: InboundLead | None,
        generated_at: str,
    ) -> dict[str, Any]:
        runs.sort(key=lambda state: (state.updated_at, state.run_id))
        latest = runs[-1] if runs else None
        name = (lead.company or lead.contact).strip() if lead else ""
        if not name:
            name = next((workflow_state_name(state) for state in runs if workflow_state_name(state) not in {state.client_id, state.entity_id}), key)
        synthetic = bool(lead and self._lead_is_synthetic(lead)) or any(
            self._explicit_synthetic(state) for state in runs
        )
        lifecycle = self._lifecycle(runs, lead)
        blocker = next(
            (
                state.blocker
                or (
                    state.stage(state.current_stage_id).blocker
                    if state.current_stage_id
                    else None
                )
                for state in reversed(runs)
                if state.blocker
                or (
                    state.current_stage_id
                    and state.stage(state.current_stage_id).blocker
                )
            ),
            None,
        )
        failed = any(state.status.value == "failed" for state in runs)
        waiting = bool(latest and latest.status.value == "awaiting_approval")
        requires_matt = waiting or bool(latest and (latest.revision_owner or "").casefold() == "matt")
        waiting_externally = bool(blocker and str(blocker).casefold().startswith("waiting_external"))
        stage = latest.stage(latest.current_stage_id) if latest and latest.current_stage_id else None
        stalled = bool(latest and stage and self._stage_is_stalled(latest, stage, generated_at))
        retrying = bool(
            latest
            and stage
            and latest.status.value == "active"
            and stage.status.value == "ready"
            and stage.retry_count
        )
        queued = bool(
            latest
            and stage
            and latest.status.value == "active"
            and stage.status.value == "ready"
            and not stage.retry_count
        )
        attention = "failed" if failed else "waiting_externally" if waiting_externally else "blocked" if blocker else "matt_required" if requires_matt else "stalled" if stalled else "retrying" if retrying else "queued" if queued else "running" if latest and latest.status.value == "active" else "complete" if lifecycle == "complete" else "ready"
        owner = "Matt" if requires_matt else self._owner(latest)
        evidence_errors = []
        run_events = {}
        for state in runs:
            try:
                run_events[state.run_id] = self.evidence.events(state)
            except (OSError, ValueError, KeyError, TypeError):
                run_events[state.run_id] = ()
                evidence_errors.append(f"Event history unreadable for {state.run_id}; inspect the canonical journal.")
        artefacts = self._artefacts(runs, run_events)
        events = [self._event_item(state, event, name) for state in runs for event in run_events[state.run_id]]
        events = [event for event in events if event is not None]
        events.sort(key=lambda item: item["occurred_at"], reverse=True)
        next_action = latest.current_proposed_next_action() if latest else (lead.recommended_next_action if lead else None)
        current_activity = self._activity(latest, attention) if latest else "Opportunity recorded"
        run_details = [self._run_detail(state, run_events[state.run_id]) for state in runs]
        issues = evidence_errors + [issue for run in run_details for issue in run["issues"]]
        if latest and latest.status.value == "complete" and not run_details[-1]["completion_verified"]:
            attention = "unverified"
            current_activity = "Completion recorded; evidence incomplete"
        successful_events = [event for event in events if event["event_type"] in {"stage.completed", "workflow.outputs_promoted", "workflow.approved", "approval.granted"}]
        return {
            "id": key,
            "company": name,
            "kind": "TEST" if synthetic else "LIVE",
            "synthetic": synthetic,
            "lifecycle_stage": lifecycle,
            "operational_substate": attention if latest and latest.status.value == "active" else latest.status.value if latest else (lead.status if lead else "unknown"),
            "current_owner": owner,
            "current_activity": current_activity,
            "started_at": self._started(latest),
            "next_action": next_action or "No authoritative next action recorded.",
            "blocked": bool(blocker),
            "blocker": blocker,
            "requires_matt": requires_matt,
            "attention_state": attention,
            "updated_at": latest.updated_at if latest else (lead.created_at if lead else ""),
            "last_meaningful_event": events[0]["label"] if events else (current_activity if latest else "Lead recorded"),
            "journey": self._journey(lifecycle, runs, run_details),
            "artefacts": artefacts,
            "quality_history": self._quality_history(runs),
            "activity": events,
            "profile": {"summary": lead.ai_summary if lead else "", "source": lead.source if lead else "unknown", "notion_url": lead.notion_url if lead else ""},
            "runs": run_details,
            "evidence_issues": issues,
            "last_successful_activity_at": successful_events[0]["occurred_at"] if successful_events else None,
            "readiness": "blocked" if issues or blocker else "awaiting_approval" if requires_matt else "not_verified",
            "acquisition_path": "inbound" if lead and lead.source.strip().casefold() in {"tally", "growth diagnostic", "website"} else "unknown",
            "evidence": [f"workflow:{state.run_id}" for state in runs] + ([f"lead:{lead.lead_id}"] if lead else []),
        }

    @staticmethod
    def _explicit_synthetic(state: WorkflowState) -> bool:
        payload = state.input_payload
        return payload.get("synthetic") is True or payload.get("test_fixture") is True or any(
            str(item).startswith("synthetic:") for item in payload.get("evidence", []) if isinstance(item, str)
        )

    @staticmethod
    def _lead_is_synthetic(lead: InboundLead) -> bool:
        if lead.disposition in {"suppressed", "test", "archived"}:
            return True
        label = f"{lead.company} {lead.contact}".strip().casefold()
        return label.startswith(("safe ", "test ", "qa test ", "qa proposition "))

    @staticmethod
    def _lifecycle(runs: list[WorkflowState], lead: InboundLead | None) -> str:
        stage = LEAD_STAGE.get(" ".join((lead.pipeline_stage if lead else "").casefold().replace("_", " ").split()), "lead")
        for state in runs:
            candidate = WORKFLOW_STAGE.get(state.workflow_id, "delivery" if state.workflow_id in DELIVERY_STEPS else stage)
            if LIFECYCLE.index(candidate) > LIFECYCLE.index(stage):
                stage = candidate
        return stage

    @staticmethod
    def _owner(state: WorkflowState | None) -> str:
        if not state:
            return "Tony"
        if state.current_stage_id:
            return state.stage(state.current_stage_id).agent_ref or "Tony"
        return state.revision_owner or "Tony"

    @staticmethod
    def _activity(state: WorkflowState | None, attention: str = "") -> str:
        if not state:
            return "Opportunity recorded"
        label = DELIVERY_STEPS.get(state.workflow_id) or ARTEFACT_NAMES.get(state.workflow_id) or state.workflow_id.replace("_", " ").title()
        if state.status.value == "awaiting_approval":
            return f"{label} awaiting Matt review"
        if state.status.value == "complete":
            return f"{label} complete"
        if state.status.value == "blocked":
            return f"{label} blocked"
        if attention == "stalled":
            return f"{label} stalled"
        if attention == "retrying":
            return f"{label} recovered; governed retry ready"
        if attention == "queued":
            return f"{label} queued"
        return f"{label} in progress"

    def _stage_is_stalled(
        self,
        state: WorkflowState,
        stage: StageRecord,
        generated_at: str,
    ) -> bool:
        if state.status.value != "active" or stage.status.value != "running" or not stage.started_at:
            return False
        timeout = self.worker_timeout_seconds.get(stage.capability)
        if timeout is None:
            return False
        try:
            now = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            started = datetime.fromisoformat(stage.started_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        return (now - started).total_seconds() > max(timeout * 2, 300)

    @staticmethod
    def _started(state: WorkflowState | None) -> str | None:
        if not state:
            return None
        if state.current_stage_id:
            return state.stage(state.current_stage_id).started_at or state.created_at
        return state.created_at

    def _journey(self, lifecycle: str, runs: list[WorkflowState], details: list[dict[str, Any]]) -> list[dict[str, str]]:
        current = LIFECYCLE.index(lifecycle)
        verified = {run["run_id"] for run in details if run["completion_verified"]}
        journey = []
        for i, item in enumerate(LIFECYCLE):
            matching = [run for run in runs if WORKFLOW_STAGE.get(run.workflow_id, "delivery" if run.workflow_id in DELIVERY_STEPS else "") == item]
            status = "complete" if matching and all(run.run_id in verified for run in matching) else "active" if i == current else "unknown" if i < current else "not_started"
            journey.append({"id": item, "label": item.replace("_", " ").title(), "state": status})
        if lifecycle == "delivery":
            for state in runs:
                if state.workflow_id in DELIVERY_STEPS:
                    journey.append({"id": state.workflow_id, "label": DELIVERY_STEPS[state.workflow_id], "state": "blocked" if state.status.value in {"blocked", "failed"} else "complete" if state.run_id in verified else "unknown" if state.status.value == "complete" else "active"})
        return journey

    def _run_detail(self, state: WorkflowState, events: tuple[WorkflowEvent, ...]) -> dict[str, Any]:
        issues = []
        if not events:
            issues.append("No readable scoped workflow event history.")
        steps = []
        for stage in state.stages:
            verified_files = bool(stage.output_artifacts)
            for artifact in stage.output_artifacts:
                path = Path(artifact.location)
                valid = self._within_scope(path, state) and bool(artifact.checksum)
                if valid:
                    try:
                        valid = hashlib.sha256(path.read_bytes()).hexdigest() == artifact.checksum
                    except OSError:
                        valid = False
                verified_files = verified_files and valid
            completion_event = any(
                event.event_type == "stage.completed"
                and event.payload.get("stage_id") == stage.stage_id
                and event.payload.get("output_artifact_ids") == [item.artifact_id for item in stage.output_artifacts]
                for event in events
            )
            verified = stage.status.value == "completed" and verified_files and completion_event and (stage.quality_result or {}).get("passed") is True
            if stage.status.value == "completed" and not verified:
                issues.append(f"{stage.stage_id}: completion lacks output/checksum, quality or stage-completed event evidence.")
            if stage.blocker or stage.failure_reason:
                issues.append(stage.blocker or stage.failure_reason)
            steps.append({"stage_id": stage.stage_id, "owner": stage.agent_ref,
                          "status": stage.status.value, "completion_verified": verified,
                          "quality_passed": (stage.quality_result or {}).get("passed"),
                          "output_verified": verified_files, "retry_count": stage.retry_count,
                          "attempt_count": len(stage.attempts), "revision_count": stage.revision_count,
                          "started_at": stage.started_at, "completed_at": stage.completed_at,
                          "blocker": stage.blocker or stage.failure_reason,
                          "artifact_ids": [item.artifact_id for item in stage.output_artifacts]})
        if state.blocker and state.blocker not in issues:
            issues.append(state.blocker)
        latest_artifact = next((stage.output_artifacts[-1] for stage in reversed(state.stages) if stage.output_artifacts), None)
        approval = state.approval_history[-1] if state.approval_history else {}
        binding = approval.get("approval_binding") or {}
        approval_verified = not state.approval_required or bool(
            state.approval_status == "approved" and latest_artifact
            and approval.get("approver") and approval.get("rationale") and approval.get("approved_at")
            and binding.get("artifact_id") == latest_artifact.artifact_id
            and binding.get("artifact_checksum") == latest_artifact.checksum
            and any(event.event_type == "approval.granted" and event.payload == approval for event in events)
        )
        if state.status.value == "complete" and not approval_verified:
            issues.append("Completion lacks recorded human approval evidence.")
        return {"run_id": state.run_id, "workflow_id": state.workflow_id,
                "status": state.status.value, "owner": self._owner(state),
                "updated_at": state.updated_at, "stages": steps,
                "completion_verified": state.status.value == "complete" and bool(steps) and all(step["completion_verified"] for step in steps) and approval_verified and not issues,
                "approval_status": state.approval_status,
                "external_action_taken": state.external_action_taken,
                "next_action": state.current_proposed_next_action() or "Inspect the recorded workflow evidence through Tony.",
                "issues": list(dict.fromkeys(issues))}

    def _artefacts(self, runs: list[WorkflowState], run_events: Mapping[str, tuple[WorkflowEvent, ...]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        versions: dict[str, int] = defaultdict(int)
        for state in runs:
            for stage in state.stages:
                candidates: list[tuple[ArtifactRef, bool, int]] = []
                for attempt in stage.attempts:
                    raw = attempt.get("candidate_artifact")
                    if isinstance(raw, Mapping):
                        candidates.append((ArtifactRef(**raw), bool(attempt.get("quality_passed")), int(attempt.get("revision", 0)) + 1))
                candidates.extend((artifact, bool(stage.quality_result and stage.quality_result.get("passed")), stage.revision_count + 1) for artifact in stage.output_artifacts)
                for artifact, passed, version in candidates:
                    title = ARTEFACT_NAMES.get(state.workflow_id, artifact.artifact_type.replace("_", " ").title())
                    versions[title] = max(versions[title], version)
                    location = Path(artifact.location)
                    if not location.is_absolute():
                        location = Path.cwd() / location
                    safe = self._within_scope(location, state)
                    approval_status = "not_recorded"
                    if state.approval_status == "pending" and artifact == next((step.output_artifacts[-1] for step in reversed(state.stages) if step.output_artifacts), None):
                        approval_status = "pending"
                    for decision in state.approval_history:
                        binding = decision.get("approval_binding") or {}
                        if binding.get("artifact_id") == artifact.artifact_id and binding.get("artifact_checksum") == artifact.checksum:
                            if decision.get("approver") and decision.get("approved_at") and any(event.event_type == "approval.granted" and event.payload == decision for event in run_events[state.run_id]):
                                approval_status = "approved"
                            elif decision.get("reviewer"):
                                approval_status = "rejected"
                    items.append({
                        "artifact_id": artifact.artifact_id, "name": title, "type": artifact.artifact_type,
                        "version": version, "created_at": stage.completed_at or state.updated_at,
                        "producer": stage.agent_ref, "quality_status": "passed" if passed else "failed" if artifact.artifact_type == "worker_attempt_output" else "not_recorded",
                        "approval_status": approval_status, "checksum": artifact.checksum,
                        "location": artifact.location, "open_url": f"/mission-control/artifact?artifact_id={artifact.artifact_id}" if safe else None,
                        "parent_artifact_ids": list(artifact.metadata.get("parent_artifact_ids", [])),
                    })
        return list({item["artifact_id"]: item for item in items}.values())

    def _within_scope(self, path: Path, state: WorkflowState) -> bool:
        scope = hashlib.sha256(
            f"{state.workspace_id}:{state.client_id}".encode("utf-8")
        ).hexdigest()[:24]
        artifact_root = self.workflow_root / scope / "artifacts"
        try:
            path.resolve().relative_to(artifact_root.resolve())
            return path.is_file()
        except (OSError, ValueError):
            return False

    @staticmethod
    def _quality_history(runs: list[WorkflowState]) -> list[dict[str, Any]]:
        history = []
        for state in runs:
            for stage in state.stages:
                for index, attempt in enumerate(stage.attempts, 1):
                    if "quality_passed" in attempt or attempt.get("status") == "failed":
                        history.append({"workflow_id": state.workflow_id, "stage_id": stage.stage_id, "version": int(attempt.get("revision", index - 1)) + 1, "passed": attempt.get("quality_passed") is True, "failed_criteria": list((stage.quality_result or {}).get("failed_checks", [])) if attempt.get("quality_passed") is False else [], "revision_requested": attempt.get("quality_passed") is False, "artifact_id": (attempt.get("candidate_artifact") or {}).get("artifact_id")})
                if stage.quality_result:
                    history.append({"workflow_id": state.workflow_id, "stage_id": stage.stage_id, "version": stage.revision_count + 1, "passed": stage.quality_result.get("passed") is True, "failed_criteria": list(stage.quality_result.get("failed_checks", [])), "revision_requested": stage.quality_result.get("passed") is False, "artifact_id": stage.output_artifacts[-1].artifact_id if stage.output_artifacts else None})
        return history

    @staticmethod
    def _event_item(state: WorkflowState, event: WorkflowEvent, company: str) -> dict[str, str] | None:
        labels = {
            "workflow.created": "Workflow started", "stage.started": "Specialist work started",
            "stage.completed": "Workflow stage completed", "stage.quality_recorded": "Quality review recorded",
            "workflow.outputs_promoted": "Governed output promoted", "workflow.handoff_created": "Next workflow commissioned",
            "workflow.approved": "Human approval recorded", "workflow.blocked": "Workflow blocked",
            "approval.granted": "Human approval recorded", "approval.requested": "Human review requested",
        }
        label = labels.get(event.event_type)
        if not label:
            label = event.event_type.replace(".", " · ").replace("_", " ")
        if event.event_type == "stage.quality_recorded":
            label = "Quality gate passed" if event.payload.get("passed") else "Quality review failed"
        return {"event_id": event.event_id, "event_type": event.event_type, "company": company, "label": label, "occurred_at": event.occurred_at, "run_id": state.run_id}

    @staticmethod
    def _queue_item(item: Mapping[str, Any]) -> dict[str, Any]:
        return {"opportunity_id": item["id"], "company": item["company"], "decision": item["next_action"], "why": "A persisted workflow approval gate requires Matt.", "requested_at": item["updated_at"], "safe_next_action": "Use the existing governed Tony approval flow for the exact artefact version."}

    @staticmethod
    def _connections(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
        result = []
        for item in snapshot.get("connections", []):
            if not isinstance(item, Mapping):
                continue
            state = str(item.get("state", "unknown"))
            if state not in VALID_CONNECTION_STATES:
                state = "unknown"
            if state == "connected" and not item.get("evidence"):
                state = "unknown"
            result.append({"name": item.get("name"), "state": state, "evidence": item.get("evidence"), "last_checked_at": item.get("last_checked_at")})
        return result
