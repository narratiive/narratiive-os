from __future__ import annotations

import json
import hashlib
import shlex
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.campaign_learning_coordinator import CampaignLearningCoordinator
from runtime.models import WorkflowState
from runtime.serialization import workflow_from_dict, workflow_to_dict
from runtime.tony_command_service import CommandResponse
from runtime.tony_internal_review_delivery import (
    INTERNAL_REVIEW_ADDRESS,
    InternalReviewDeliveryService,
    approval_binding_evidence,
    workflow_approval_token,
)
from runtime.tony_workflow_runtime import TonyWorkflowRuntime, build_tony_workflow_runtime
from runtime.workflow_action_preview import WorkflowActionPreviewService
from runtime.workflow_deliverable_persistence import WorkflowDeliverablePersistenceService
from runtime.workflow_run_identity import downstream_run_id
from runtime.workflow_mission_control import workflow_state_name, workflow_state_summary
from runtime.workflow_portfolio import project_client_portfolio


class WorkflowCommandBackend(Protocol):
    def list_states(self) -> tuple[WorkflowState, ...]: ...
    def approve(self, state: WorkflowState, *, approver: str, rationale: str, approval_token: str) -> WorkflowState: ...
    def reject(self, state: WorkflowState, *, reviewer: str, rationale: str, approval_token: str) -> WorkflowState: ...
    def resume(self, state: WorkflowState) -> WorkflowState: ...
    def advance(self, state: WorkflowState, additional_inputs: Mapping[str, Any] | None = None) -> WorkflowState: ...
    def recover(self) -> int: ...
    def latest_output(self, state: WorkflowState) -> Mapping[str, Any] | None: ...
    def artifact_detail(self, state: WorkflowState) -> Mapping[str, Any]: ...
    def action_preview(
        self, state: WorkflowState, *, simulation_mode: bool, delivery_override: str
    ) -> Mapping[str, Any]: ...
    def execute_action(
        self, state: WorkflowState, *, action_digest: str, approver: str, rationale: str
    ) -> Mapping[str, Any]: ...
    def drive_persistence_preview(self, state: WorkflowState, *, drive_folder_id: str) -> Mapping[str, Any]: ...
    def execute_drive_persistence(
        self,
        state: WorkflowState,
        *,
        drive_folder_id: str,
        action_digest: str,
        approver: str,
        rationale: str,
    ) -> Mapping[str, Any]: ...
    def campaign_world_selection_brief(self, state: WorkflowState) -> Mapping[str, Any]: ...
    def select_campaign_world(
        self,
        state: WorkflowState,
        *,
        candidate_id: str,
        candidate_checksum: str,
        approver: str,
        rationale: str,
    ) -> WorkflowState: ...
    def creative_bible_approval_brief(self, state: WorkflowState) -> Mapping[str, Any]: ...
    def approve_creative_bible(
        self,
        state: WorkflowState,
        *,
        creative_bible_checksum: str,
        approval_token: str,
        approver: str,
        rationale: str,
    ) -> WorkflowState: ...
    def asset_suite_approval_brief(self, state: WorkflowState) -> Mapping[str, Any]: ...
    def approve_asset_suite(
        self,
        state: WorkflowState,
        *,
        asset_suite_checksum: str,
        approval_token: str,
        approver: str,
        rationale: str,
    ) -> WorkflowState: ...
    def projection(self, state: WorkflowState) -> Mapping[str, Any]: ...
    def sync_projection(self, state: WorkflowState, *, approver: str, rationale: str) -> Mapping[str, Any]: ...
    def deliver_internal_review(self, state: WorkflowState, *, recipient: str) -> Mapping[str, Any]: ...
    def commission(
        self,
        state: WorkflowState,
        *,
        target_workflow_id: str,
        inputs: Mapping[str, Any],
        commitment_id: str,
    ) -> tuple[WorkflowState, bool]: ...
    def begin_promised_delivery(self, state: WorkflowState, *, delivery_key: str, kind: str) -> WorkflowState: ...
    def finish_promised_delivery(self, state: WorkflowState, *, delivery_key: str, evidence: Mapping[str, Any]) -> WorkflowState: ...
    def commission_additional_research(
        self,
        state: WorkflowState,
        *,
        focus: Mapping[str, Any],
        sources: list[Mapping[str, Any]] | None,
        requester: str,
        rationale: str,
    ) -> WorkflowState: ...


class FileWorkflowCommandBackend:
    """Operate existing scoped workflow runs through the canonical runtime API."""

    def __init__(
        self,
        root: str | Path,
        *,
        dispatchers=None,
        environ=None,
        workspace_id: str | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.dispatchers = dispatchers
        self.environ = environ
        if workspace_id is not None and not workspace_id.strip():
            raise ValueError("workspace_id must not be empty")
        self.workspace_id = workspace_id.strip() if workspace_id is not None else None

    def list_states(self) -> tuple[WorkflowState, ...]:
        if not self.root.is_dir():
            return ()
        states: list[WorkflowState] = []
        for path in sorted(self.root.glob("*/runs/*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                state = workflow_from_dict(raw)
                expected_scope = hashlib.sha256(
                    f"{state.workspace_id}:{state.client_id}".encode("utf-8")
                ).hexdigest()[:24]
                if path.parent.parent.name != expected_scope:
                    raise ValueError("workflow scope does not match its storage location")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(f"workflow state is unreadable: {path.name}") from exc
            if self.workspace_id is not None and state.workspace_id != self.workspace_id:
                continue
            states.append(state)
        return tuple(states)

    def approve(self, state: WorkflowState, *, approver: str, rationale: str, approval_token: str) -> WorkflowState:
        binding = approval_binding_evidence(state, approval_token)
        runtime = self._runtime(state)
        runtime.approve(
            state.run_id,
            approver=approver,
            rationale=rationale,
            approval_binding=binding,
        )
        return runtime.runs.load_run(state.run_id)

    def reject(self, state: WorkflowState, *, reviewer: str, rationale: str, approval_token: str) -> WorkflowState:
        binding = None
        if state.approval_status == "pending":
            binding = approval_binding_evidence(state, approval_token)
        runtime = self._runtime(state)
        runtime.reject_for_revision(
            state.run_id,
            reviewer=reviewer,
            rationale=rationale,
            approval_binding=binding,
        )
        return runtime.runs.load_run(state.run_id)

    def resume(self, state: WorkflowState) -> WorkflowState:
        runtime = self._runtime(state)
        runtime.resume(state.run_id)
        return runtime.runs.load_run(state.run_id)

    def advance(self, state: WorkflowState, additional_inputs: Mapping[str, Any] | None = None) -> WorkflowState:
        runtime = self._runtime(state)
        lifecycle = ClientLifecycleRecord(
            client_id=state.client_id,
            client_name=_state_name(state),
            stage=ClientLifecycleStage.RESEARCH,
            owner="Tony",
            next_action=state.proposed_next_action or "Continue authorised internal workflow preparation.",
            evidence=(f"workflow_run:{state.run_id}",),
        )
        if state.status.value == "complete" and runtime.coordinator.registry.resolve(state.workflow_id).next_workflow_id:
            outcome = runtime.handoff(state.run_id, lifecycle, additional_inputs)
            next_workflow_id = runtime.coordinator.registry.resolve(state.workflow_id).next_workflow_id
            return runtime.runs.load_run(
                outcome.next_run_id or downstream_run_id(state.run_id, next_workflow_id)
            )
        if additional_inputs:
            raise ValueError("additional inputs can only be supplied to an approved cross-workflow handoff")
        runtime.advance(state.run_id, lifecycle)
        return runtime.runs.load_run(state.run_id)

    def commission(
        self,
        state: WorkflowState,
        *,
        target_workflow_id: str,
        inputs: Mapping[str, Any],
        commitment_id: str,
    ) -> tuple[WorkflowState, bool]:
        runtime = self._runtime(state)
        return runtime.commission(
            state.run_id,
            target_workflow_id,
            inputs,
            commitment_id=commitment_id,
        )

    def begin_promised_delivery(self, state: WorkflowState, *, delivery_key: str, kind: str) -> WorkflowState:
        return self._runtime(state).runs.begin_promised_delivery(
            state.run_id,
            delivery_key=delivery_key,
            kind=kind,
        )

    def finish_promised_delivery(
        self,
        state: WorkflowState,
        *,
        delivery_key: str,
        evidence: Mapping[str, Any],
    ) -> WorkflowState:
        return self._runtime(state).runs.finish_promised_delivery(
            state.run_id,
            delivery_key=delivery_key,
            evidence=evidence,
        )

    def recover(self) -> int:
        recovered = 0
        seen: set[tuple[str, str]] = set()
        for state in self.list_states():
            scope = (state.workspace_id, state.client_id)
            if scope in seen:
                continue
            seen.add(scope)
            recovered += self._runtime(state).recover_pending()
        return recovered

    def latest_output(self, state: WorkflowState) -> Mapping[str, Any] | None:
        artifacts = [artifact for stage in state.stages for artifact in stage.output_artifacts]
        if not artifacts:
            return None
        location = Path(artifacts[-1].location).resolve()
        try:
            location.relative_to(self.root)
        except ValueError:
            return None
        try:
            value = json.loads(location.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, Mapping) else None

    def artifact_detail(self, state: WorkflowState) -> Mapping[str, Any]:
        return WorkflowActionPreviewService(
            self.root,
            self.dispatchers.get("Gmail") if self.dispatchers else None,
        ).artifact_detail(state)

    def action_preview(
        self,
        state: WorkflowState,
        *,
        simulation_mode: bool,
        delivery_override: str,
    ) -> Mapping[str, Any]:
        return WorkflowActionPreviewService(
            self.root,
            self.dispatchers.get("Gmail") if self.dispatchers else None,
        ).preview_simulated_email(
            state,
            simulation_mode=simulation_mode,
            delivery_override=delivery_override,
        )

    def execute_action(
        self,
        state: WorkflowState,
        *,
        action_digest: str,
        approver: str,
        rationale: str,
    ) -> Mapping[str, Any]:
        runtime = self._runtime(state)
        return WorkflowActionPreviewService(
            self.root,
            self.dispatchers.get("Gmail") if self.dispatchers else None,
        ).execute_simulated_email(
            runtime,
            state,
            action_digest=action_digest,
            approver=approver,
            rationale=rationale,
        )

    def drive_persistence_preview(
        self,
        state: WorkflowState,
        *,
        drive_folder_id: str,
    ) -> Mapping[str, Any]:
        return WorkflowDeliverablePersistenceService(
            self.root,
            self.dispatchers.get("Google Drive") if self.dispatchers else None,
        ).preview(state, drive_folder_id=drive_folder_id)

    def execute_drive_persistence(
        self,
        state: WorkflowState,
        *,
        drive_folder_id: str,
        action_digest: str,
        approver: str,
        rationale: str,
    ) -> Mapping[str, Any]:
        runtime = self._runtime(state)
        return WorkflowDeliverablePersistenceService(
            self.root,
            self.dispatchers.get("Google Drive") if self.dispatchers else None,
        ).execute(
            runtime,
            state,
            drive_folder_id=drive_folder_id,
            action_digest=action_digest,
            approver=approver,
            rationale=rationale,
        )

    def campaign_world_selection_brief(self, state: WorkflowState) -> Mapping[str, Any]:
        return self._runtime(state).campaign_world_selection_brief(state.run_id)

    def select_campaign_world(
        self,
        state: WorkflowState,
        *,
        candidate_id: str,
        candidate_checksum: str,
        approver: str,
        rationale: str,
    ) -> WorkflowState:
        runtime = self._runtime(state)
        runtime.select_campaign_world(
            state.run_id,
            candidate_id=candidate_id,
            candidate_checksum=candidate_checksum,
            approver=approver,
            rationale=rationale,
        )
        return runtime.runs.load_run(state.run_id)

    def creative_bible_approval_brief(self, state: WorkflowState) -> Mapping[str, Any]:
        return self._runtime(state).creative_bible_approval_brief(state.run_id)

    def approve_creative_bible(
        self,
        state: WorkflowState,
        *,
        creative_bible_checksum: str,
        approval_token: str,
        approver: str,
        rationale: str,
    ) -> WorkflowState:
        runtime = self._runtime(state)
        brief = runtime.creative_bible_approval_brief(state.run_id)
        if creative_bible_checksum.strip() != str(brief.get("creative_bible_checksum") or ""):
            raise ValueError("Creative Bible approval checksum is stale or incorrect")
        if state.status.value == "awaiting_approval":
            binding = approval_binding_evidence(state, approval_token)
            runtime.approve(
                state.run_id,
                approver=approver,
                rationale=rationale,
                approval_binding=binding,
            )
        runtime.approve_creative_bible(
            state.run_id,
            creative_bible_checksum=creative_bible_checksum,
            approver=approver,
            rationale=rationale,
        )
        return runtime.runs.load_run(state.run_id)

    def asset_suite_approval_brief(self, state: WorkflowState) -> Mapping[str, Any]:
        return self._runtime(state).asset_suite_approval_brief(state.run_id)

    def approve_asset_suite(
        self,
        state: WorkflowState,
        *,
        asset_suite_checksum: str,
        approval_token: str,
        approver: str,
        rationale: str,
    ) -> WorkflowState:
        runtime = self._runtime(state)
        brief = runtime.asset_suite_approval_brief(state.run_id)
        if asset_suite_checksum.strip() != str(brief.get("asset_suite_checksum") or ""):
            raise ValueError("asset-suite approval checksum is stale or incorrect")
        if state.status.value == "awaiting_approval":
            binding = approval_binding_evidence(state, approval_token)
            runtime.approve(
                state.run_id,
                approver=approver,
                rationale=rationale,
                approval_binding=binding,
            )
        runtime.approve_asset_suite(
            state.run_id,
            asset_suite_checksum=asset_suite_checksum,
            approver=approver,
            rationale=rationale,
        )
        return runtime.runs.load_run(state.run_id)

    def projection(self, state: WorkflowState) -> Mapping[str, Any]:
        runtime = self._runtime(state)
        if runtime.business_projection is None:
            raise ValueError("business projection is not configured")
        return runtime.business_projection.prepare(state)

    def sync_projection(self, state: WorkflowState, *, approver: str, rationale: str) -> Mapping[str, Any]:
        return self._runtime(state).sync_business_projection(
            state.run_id,
            approver=approver,
            rationale=rationale,
        )

    def deliver_internal_review(self, state: WorkflowState, *, recipient: str) -> Mapping[str, Any]:
        runtime = self._runtime(state)
        service = InternalReviewDeliveryService(self.root, self.dispatchers.get("Gmail") if self.dispatchers else None)
        return service.deliver(runtime, state, recipient=recipient)

    def commission_additional_research(
        self,
        state: WorkflowState,
        *,
        focus: Mapping[str, Any],
        sources: list[Mapping[str, Any]] | None,
        requester: str,
        rationale: str,
    ) -> WorkflowState:
        kind, statement = _research_focus(focus)
        base_sources = state.input_payload.get("research_sources")
        combined_sources = _merge_research_sources(base_sources, sources)
        if not combined_sources:
            raise ValueError("additional research requires at least one explicitly approved source")
        scope = state.input_payload.get("approved_growth_sprint_scope")
        client_context = state.input_payload.get("client_context")
        if not scope or not isinstance(client_context, Mapping):
            raise ValueError("additional research requires an approved Growth Sprint scope and client context")
        parent_artifacts = [
            artifact.artifact_id
            for stage in state.stages
            for artifact in stage.output_artifacts
        ]
        prior_lineage = state.input_payload.get("_lineage")
        if isinstance(prior_lineage, Mapping):
            parent_artifacts.extend(
                str(item)
                for item in prior_lineage.get("parent_artifact_ids", [])
                if str(item).strip()
            )
        inputs = {
            "approved_growth_sprint_scope": scope,
            "research_requirements": {
                "workstreams_and_questions": [
                    {
                        "workstream": f"additional_{kind}",
                        "questions": [statement],
                    }
                ],
                "known_gaps": [statement] if kind == "evidence_gap" else [],
            },
            "research_sources": combined_sources,
            "client_context": dict(client_context),
            "research_iteration": {
                "kind": kind,
                "statement": statement,
                "requested_by": requester.strip() or "Tony",
                "rationale": rationale.strip(),
                "source_run_id": state.run_id,
            },
            "_lineage": {
                "parent_workflow_id": state.workflow_id,
                "parent_run_id": state.run_id,
                "parent_artifact_ids": list(dict.fromkeys(parent_artifacts)),
            },
        }
        identity = hashlib.sha256(
            json.dumps(
                {
                    "source_run_id": state.run_id,
                    "focus": {"kind": kind, "statement": statement},
                    "research_sources": combined_sources,
                    "requested_by": requester.strip() or "Tony",
                    "rationale": rationale.strip(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        run_id = f"{state.run_id}-additional-research-{identity}"
        runtime = self._runtime(state)
        runtime.enqueue(
            "growth_sprint_to_research_engine",
            run_id,
            inputs,
            entity_id=state.entity_id,
            correlation_id=state.correlation_id,
        )
        runtime.advance(
            run_id,
            ClientLifecycleRecord(
                client_id=state.client_id,
                client_name=_state_name(state),
                stage=ClientLifecycleStage.RESEARCH,
                owner="Tony",
                next_action=f"Investigate the specific {kind.replace('_', ' ')} without crossing a human gate.",
                evidence=(f"workflow_run:{state.run_id}",),
            ),
        )
        return runtime.runs.load_run(run_id)

    def _runtime(self, state: WorkflowState) -> TonyWorkflowRuntime:
        if self.workspace_id is not None and state.workspace_id != self.workspace_id:
            raise ValueError("workflow state workspace mismatch")
        return build_tony_workflow_runtime(
            self.root,
            workspace_id=state.workspace_id,
            client_id=state.client_id,
            dispatchers=self.dispatchers,
            environ=self.environ,
        )


class TonyWorkflowCommandService:
    """Concise, deterministic executive controls over persisted workflow truth."""

    _COMMANDS = {
        "workflow", "work", "approvals", "blockers", "artefact", "artifact",
        "proposed", "approve", "reject", "revise", "resume", "recover",
        "projection", "sync-notion", "research",
        "deliver-review",
        "commission",
        "artefact-detail", "artifact-detail", "action-preview", "execute-action",
        "drive-preview", "persist-drive",
        "worlds", "select-world", "bible", "approve-bible", "assets", "approve-assets",
        "campaigns", "clients", "learning", "learning-queue", "sync-learning",
    }

    def __init__(
        self,
        command_service,
        backend: WorkflowCommandBackend,
        campaign_learning: CampaignLearningCoordinator | None = None,
    ) -> None:
        self.command_service = command_service
        self.backend = backend
        self.campaign_learning = campaign_learning

    def supports(self, command: str) -> bool:
        name = command.strip().split(" ", 1)[0].lower().lstrip("/")
        if name == "continue":
            return bool(command.strip().split(" ", 1)[1:])
        return name in self._COMMANDS

    def execute(
        self,
        command: str,
        objects: Iterable[dict[str, Any]],
        *,
        principal_id: str = "",
        inputs: Mapping[str, Any] | None = None,
    ) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        try:
            parts = shlex.split(normalized)
        except ValueError as exc:
            return self._error("workflow", "invalid_command", str(exc))
        if not parts:
            return self.command_service.execute(command, objects)
        name = parts[0].lower().lstrip("/")
        if name == "continue" and len(parts) == 1:
            return self.command_service.execute(command, objects)
        if name not in self._COMMANDS and name != "continue":
            return self.command_service.execute(command, objects)
        try:
            if name == "recover":
                recovered = self.backend.recover()
                return CommandResponse("recover", "healthy", f"Recovery checked; {recovered} interrupted run(s) recovered.", {"recovered": recovered})
            states = self.backend.list_states()
            if name in {"campaigns", "clients"}:
                return self._portfolio(states)
            if name in {"learning", "learning-queue", "sync-learning"}:
                reference, rationale = self._arguments(parts[1:])
                if self.campaign_learning is None:
                    return self._error(name, "campaign_learning_unavailable", "Campaign learning is not configured.")
                if name == "learning-queue":
                    result = self.campaign_learning.monitor(states)
                    return CommandResponse(
                        name,
                        "attention_required" if result["blocked_count"] else "healthy",
                        f"Campaign learning monitor found {result['ready_count']} review-ready and "
                        f"{result['blocked_count']} blocked campaign(s). No external action was taken.",
                        result,
                    )
                if name == "learning":
                    result = self.campaign_learning.prepare(states, reference)
                    return CommandResponse(
                        name,
                        "attention_required",
                        f"Prepared {len(result['insights'])} evidence-backed insight(s) and "
                        f"{len(result['iteration_proposals'])} bounded iteration proposal(s). "
                        "Nothing was published, funded or changed in media platforms.",
                        result,
                    )
                if not principal_id.strip():
                    return self._error(name, "authorised_principal_required", "Learning projection requires Matt's authenticated identity.")
                if not rationale:
                    return self._error(name, "rationale_required", "Use /sync-learning <campaign> because <reason>.")
                cycle_checksum = str((inputs or {}).get("cycle_checksum") or "").strip()
                result = self.campaign_learning.sync(
                    states,
                    reference,
                    cycle_checksum=cycle_checksum,
                    approver=principal_id,
                    rationale=rationale,
                )
                status = str(result.get("projection_status") or "unknown")
                return CommandResponse(
                    name,
                    "healthy" if status in {"verified", "duplicate_suppressed"} else "blocked",
                    f"Campaign learning Notion projection is {status.replace('_', ' ')}. No media mutation occurred.",
                    result,
                )
            if name in {"work", "approvals", "blockers"} and len(parts) == 1:
                return self._queue(name, states)
            reference, rationale = self._arguments(parts[1:])
            state = self._resolve(states, reference)
            if name in {"workflow", "work"}:
                return self._status(state)
            if name == "approvals":
                return self._approval(state)
            if name == "blockers":
                return self._blocker(state)
            if name in {"artefact", "artifact"}:
                return self._artefact(state)
            if name in {"artefact-detail", "artifact-detail"}:
                detail = dict(self.backend.artifact_detail(state))
                return CommandResponse(name, "healthy", f"Authoritative artefact detail resolved for {state.run_id}.", detail)
            if name == "action-preview":
                supplied = dict(inputs or {})
                if supplied.get("simulation_mode") is not True:
                    return self._error(
                        name,
                        "simulation_mode_required",
                        "This acceptance action requires explicit simulation_mode=true.",
                    )
                preview = dict(
                    self.backend.action_preview(
                        state,
                        simulation_mode=True,
                        delivery_override=str(supplied.get("delivery_override") or ""),
                    )
                )
                message = (
                    f"SIMULATION — {preview['intended_client']}. Delivery is overridden to "
                    f"{preview['delivery_override']}; no external client contact will occur. "
                    f"Proposed email: {preview['subject']} with {preview['attachments'][0]['filename']}."
                )
                return CommandResponse(name, "healthy", message, preview)
            if name == "execute-action":
                if not principal_id.strip():
                    return self._error(name, "authorised_principal_required", "This send requires Matt's authenticated Telegram approval.")
                if not rationale:
                    return self._error(name, "rationale_required", "The approved action requires a decision rationale.")
                action_digest = str((inputs or {}).get("action_digest") or "").strip()
                if not action_digest:
                    return self._error(name, "action_digest_required", "Read the action preview first and approve its exact action digest.")
                result = dict(
                    self.backend.execute_action(
                        state,
                        action_digest=action_digest,
                        approver=principal_id,
                        rationale=rationale,
                    )
                )
                return CommandResponse(
                    name,
                    "healthy",
                    f"Verified simulated delivery to {result['delivery_override']} with Gmail message {result['message_id']}.",
                    result,
                )
            if name == "drive-preview":
                drive_folder_id = str((inputs or {}).get("drive_folder_id") or "").strip()
                if not drive_folder_id:
                    return self._error(name, "drive_folder_id_required", "Supply the verified Drive folder identifier.")
                preview = dict(self.backend.drive_persistence_preview(state, drive_folder_id=drive_folder_id))
                filenames = ", ".join(str(item.get("filename") or "") for item in preview["files"])
                return CommandResponse(
                    name,
                    "healthy",
                    f"Prepared an exact internal Drive persistence preview for {filenames}. Nothing has been uploaded or shared.",
                    preview,
                )
            if name == "persist-drive":
                if not principal_id.strip():
                    return self._error(name, "authorised_principal_required", "This Drive write requires Matt's authenticated approval.")
                if not rationale:
                    return self._error(name, "rationale_required", "Use /persist-drive <run> because <reason>.")
                supplied = dict(inputs or {})
                action_digest = str(supplied.get("action_digest") or "").strip()
                drive_folder_id = str(supplied.get("drive_folder_id") or "").strip()
                if not action_digest or not drive_folder_id:
                    return self._error(name, "drive_approval_binding_required", "Read the Drive preview first and supply its exact action digest and folder identifier.")
                result = dict(
                    self.backend.execute_drive_persistence(
                        state,
                        drive_folder_id=drive_folder_id,
                        action_digest=action_digest,
                        approver=principal_id,
                        rationale=rationale,
                    )
                )
                return CommandResponse(
                    name,
                    "healthy",
                    "Verified the approved Blueprint files in the internal Drive repository. Nothing was shared, published or sent to the client.",
                    result,
                )
            if name == "worlds":
                brief = dict(self.backend.campaign_world_selection_brief(state))
                return CommandResponse(
                    name,
                    "healthy",
                    f"{len(brief.get('ready_candidate_ids') or [])} Campaign World candidates clear Tony's bar; Matt must select one exact checksum.",
                    brief,
                )
            if name == "select-world":
                if not principal_id.strip():
                    return self._error(name, "authorised_principal_required", "Campaign World selection requires Matt's authenticated identity.")
                if not rationale:
                    return self._error(name, "rationale_required", "Use /select-world <run> because <reason>.")
                supplied = dict(inputs or {})
                candidate_id = str(supplied.get("candidate_id") or "").strip()
                candidate_checksum = str(supplied.get("candidate_checksum") or "").strip()
                if not candidate_id or not candidate_checksum:
                    return self._error(name, "candidate_binding_required", "Read /worlds first and supply the exact candidate ID and checksum.")
                changed = self.backend.select_campaign_world(
                    state,
                    candidate_id=candidate_id,
                    candidate_checksum=candidate_checksum,
                    approver=principal_id,
                    rationale=rationale,
                )
                return CommandResponse(
                    name,
                    "healthy",
                    f"Recorded Matt's exact Campaign World selection {candidate_id}. No asset was produced, published or funded.",
                    self._summary(changed),
                )
            if name == "bible":
                brief = dict(self.backend.creative_bible_approval_brief(state))
                brief["approval_token"] = workflow_approval_token(state)
                return CommandResponse(
                    name,
                    "healthy",
                    "Tony has forwarded this exact Creative Bible version for Matt's approval. No production, publication or spend is authorised.",
                    brief,
                )
            if name == "approve-bible":
                if not principal_id.strip():
                    return self._error(name, "authorised_principal_required", "Creative Bible approval requires Matt's authenticated identity.")
                if not rationale:
                    return self._error(name, "rationale_required", "Use /approve-bible <run> because <reason>.")
                supplied = dict(inputs or {})
                creative_bible_checksum = str(supplied.get("creative_bible_checksum") or "").strip()
                approval_token = str(supplied.get("approval_token") or "").strip()
                if not creative_bible_checksum or (state.status.value == "awaiting_approval" and not approval_token):
                    return self._error(name, "bible_approval_binding_required", "Read /bible first and supply its exact Bible checksum and approval token.")
                changed = self.backend.approve_creative_bible(
                    state,
                    creative_bible_checksum=creative_bible_checksum,
                    approval_token=approval_token,
                    approver=principal_id,
                    rationale=rationale,
                )
                return CommandResponse(
                    name,
                    "healthy",
                    "Recorded Matt's exact Creative Bible approval. Production remains a separate planned and approved action.",
                    self._summary(changed),
                )
            if name == "assets":
                brief = dict(self.backend.asset_suite_approval_brief(state))
                brief["approval_token"] = workflow_approval_token(state)
                return CommandResponse(
                    name,
                    "healthy",
                    f"{brief['asset_count']} exact generated asset version(s) await Matt's review. Delivery, publication and spend remain unauthorised.",
                    brief,
                )
            if name == "approve-assets":
                if not principal_id.strip():
                    return self._error(name, "authorised_principal_required", "Asset-suite approval requires Matt's authenticated identity.")
                if not rationale:
                    return self._error(name, "rationale_required", "Use /approve-assets <run> because <reason>.")
                supplied = dict(inputs or {})
                asset_suite_checksum = str(supplied.get("asset_suite_checksum") or "").strip()
                approval_token = str(supplied.get("approval_token") or "").strip()
                if not asset_suite_checksum or (state.status.value == "awaiting_approval" and not approval_token):
                    return self._error(name, "asset_approval_binding_required", "Read /assets first and supply its exact suite checksum and approval token.")
                changed = self.backend.approve_asset_suite(
                    state,
                    asset_suite_checksum=asset_suite_checksum,
                    approval_token=approval_token,
                    approver=principal_id,
                    rationale=rationale,
                )
                return CommandResponse(
                    name,
                    "healthy",
                    "Recorded Matt's exact asset-suite approval. Client delivery remains a separate approval-gated action.",
                    self._summary(changed),
                )
            if name == "proposed":
                return self._proposed(state)
            if name == "projection":
                projection = dict(self.backend.projection(state))
                message = (
                    f"{state.run_id}: Notion projection is {projection.get('projection_status')}; "
                    f"runtime remains the execution source of truth."
                )
                return CommandResponse(name, "healthy", message, projection)
            if name == "sync-notion":
                if not principal_id.strip():
                    return self._error(name, "authorised_principal_required", "This Notion write requires an authenticated human identity.")
                if not rationale:
                    return self._error(name, "rationale_required", "Use /sync-notion <run or company> because <reason>.")
                projection = dict(self.backend.sync_projection(state, approver=principal_id, rationale=rationale))
                status = str(projection.get("projection_status") or "unknown")
                changed = projection.get("external_action_taken") is True
                message = (
                    f"Notion projection for {state.run_id}: {status}. "
                    + ("The returned record evidence verified this exact projection." if changed else "No new Notion write is being claimed.")
                )
                return CommandResponse(name, "healthy" if status in {"verified", "duplicate_suppressed"} else "blocked", message, projection)
            if name == "deliver-review":
                delivery = dict(
                    self.backend.deliver_internal_review(
                        state,
                        recipient=str((inputs or {}).get("recipient") or INTERNAL_REVIEW_ADDRESS),
                    )
                )
                if delivery.get("delivered") is not True:
                    status = str(delivery.get("status") or "internal_review_delivery_failed")
                    return CommandResponse(
                        name,
                        "blocked",
                        "The full review artefact could not be verified as delivered. I have not claimed that it was emailed. "
                        f"Delivery status: {status.replace('_', ' ')}. The workflow remains at its current gate.",
                        delivery,
                    )
                conclusions = [str(item) for item in delivery.get("conclusions", []) if str(item).strip()][:4]
                summary = " ".join(f"• {item}" for item in conclusions)
                message = str(delivery.get("telegram_notification") or "").strip()
                if not message:
                    message = (
                        f"{_artifact_label(state)} is ready. I sent the full review copy to {INTERNAL_REVIEW_ADDRESS}."
                        + (f" {summary}" if summary else "")
                        + " I need your judgement at the current gate: approve it, request a revision, or tell me what should change."
                    )
                return CommandResponse(name, "healthy", message, delivery)
            if name == "commission":
                supplied = dict(inputs or {})
                target_workflow_id = str(supplied.pop("target_workflow_id", "")).strip()
                commitment_id = str(supplied.pop("commitment_id", "")).strip()
                if not target_workflow_id or not commitment_id:
                    return self._error(
                        name,
                        "commission_identity_required",
                        "Durable work requires an exact target workflow and commitment identity.",
                    )
                commissioned, replay = self.backend.commission(
                    state,
                    target_workflow_id=target_workflow_id,
                    inputs=supplied,
                    commitment_id=commitment_id,
                )
                return CommandResponse(
                    name,
                    "healthy",
                    (
                        "I’ve commissioned that work against the persisted evidence and will return here "
                        "when it reaches the next review gate."
                    ),
                    {**self._summary(commissioned), "commissioned": True, "replay": replay},
                )
            if name == "research":
                if not rationale:
                    return self._error(
                        name,
                        "rationale_required",
                        "Use /research <run or company> because <why this iteration is needed>.",
                    )
                supplied = dict(inputs or {})
                focus = supplied.get("focus")
                if not isinstance(focus, Mapping):
                    return self._error(
                        name,
                        "research_focus_required",
                        "Additional research requires a structured focus with kind and statement.",
                    )
                raw_sources = supplied.get("research_sources")
                if raw_sources is not None and not isinstance(raw_sources, list):
                    return self._error(name, "research_sources_invalid", "Research sources must be a list.")
                changed = self.backend.commission_additional_research(
                    state,
                    focus=focus,
                    sources=raw_sources,
                    requester=principal_id or "Tony",
                    rationale=rationale,
                )
                status = changed.status.value
                return CommandResponse(
                    "research",
                    "healthy" if status == "complete" else status,
                    f"Additional research {changed.run_id} is {status.replace('_', ' ')}. "
                    "The iteration is persisted with its focus, sources and parent lineage; no external write occurred.",
                    self._summary(changed),
                )
            if name in {"approve", "reject", "revise"}:
                if not principal_id.strip():
                    return self._error(name, "authorised_principal_required", "This decision requires an authenticated human identity.")
                if not rationale:
                    return self._error(name, "rationale_required", f"Use /{name} <run or company> because <reason>.")
                approval_token = str((inputs or {}).get("approval_token") or "").strip()
                if state.approval_status == "pending" and not approval_token:
                    return self._error(
                        name,
                        "approval_token_required",
                        "Read the current workflow gate first and use its exact approval token; this prevents stale artefact approval.",
                    )
                if name == "approve":
                    changed = self.backend.approve(state, approver=principal_id, rationale=rationale, approval_token=approval_token)
                    return CommandResponse(name, "healthy", f"Approved {changed.run_id} for its exact proposed action. No external action was performed.", self._summary(changed))
                changed = self.backend.reject(state, reviewer=principal_id, rationale=rationale, approval_token=approval_token)
                return CommandResponse("reject", "healthy", f"Revision requested for {changed.run_id}; progression remains stopped until revised work passes quality.", self._summary(changed))
            if name == "resume":
                changed = self.backend.resume(state)
                return CommandResponse(name, "healthy", f"Resumed {changed.run_id} from persisted state. No external action was performed.", self._summary(changed))
            changed = self.backend.advance(state, inputs)
            return CommandResponse("continue", changed.status.value, f"Re-evaluated {changed.run_id}: {changed.status.value.replace('_', ' ')}.", self._summary(changed))
        except LookupError as exc:
            return self._error(name, "workflow_not_found", str(exc))
        except ValueError as exc:
            return self._error(name, "workflow_command_rejected", str(exc))
        except Exception as exc:
            return self._error(name, "workflow_state_unavailable", f"Persisted workflow state could not be used: {type(exc).__name__}")

    @staticmethod
    def _arguments(parts: list[str]) -> tuple[str, str]:
        lowered = [part.casefold() for part in parts]
        if "because" not in lowered:
            return " ".join(parts).strip(), ""
        index = lowered.index("because")
        return " ".join(parts[:index]).strip(), " ".join(parts[index + 1:]).strip()

    @staticmethod
    def _resolve(states: tuple[WorkflowState, ...], reference: str) -> WorkflowState:
        needle = reference.strip().casefold()
        if not needle:
            raise LookupError("A run, client, company or lead reference is required.")
        matches = [state for state in states if needle in _search_terms(state)]
        exact = [state for state in matches if needle in _exact_terms(state)]
        selected = exact or matches
        if not selected:
            raise LookupError(f"No persisted workflow matched: {reference}")
        if len(selected) > 1:
            identities = ", ".join(sorted(state.run_id for state in selected)[:6])
            raise LookupError(f"Reference is ambiguous; use a run ID: {identities}")
        return selected[0]

    def _queue(self, name: str, states: tuple[WorkflowState, ...]) -> CommandResponse:
        if name == "approvals":
            selected = [state for state in states if state.approval_status == "pending"]
        elif name == "blockers":
            selected = [state for state in states if state.status.value == "blocked"]
        else:
            selected = [state for state in states if state.status.value not in {"complete", "failed"}]
        selected.sort(key=lambda state: state.updated_at, reverse=True)
        label = {"work": "current workflow run", "approvals": "outstanding approval", "blockers": "workflow blocker"}[name]
        lines = [f"{len(selected)} {label}(s)."]
        lines.extend(f"• {_state_name(state)} — {state.workflow_id}: {state.status.value.replace('_', ' ')}" for state in selected[:10])
        return CommandResponse(name, "blocked" if name == "blockers" and selected else "healthy", "\n".join(lines), {"runs": [self._summary(state) for state in selected]})

    def _portfolio(self, states: tuple[WorkflowState, ...]) -> CommandResponse:
        clients = project_client_portfolio(states)
        blocked = sum(item["journey_status"] == "blocked" for item in clients)
        approvals = sum(item["human_approval_required"] for item in clients)
        fulfilled = sum(item["journey_status"] == "fulfilled" for item in clients)
        lines = [
            f"{len(clients)} client journey(s): {blocked} blocked, {approvals} awaiting human approval, {fulfilled} fulfilled."
        ]
        lines.extend(
            f"• {item['company']} — Gate {item['current_gate']}/{item['total_gates']}, "
            f"{item['current_phase']}: {item['journey_status'].replace('_', ' ')}. Next: {item['next_action']}"
            for item in clients[:10]
        )
        return CommandResponse(
            "campaigns",
            "attention_required" if blocked or approvals else "healthy",
            "\n".join(lines),
            {
                "clients": list(clients),
                "client_count": len(clients),
                "blocked_count": blocked,
                "approval_count": approvals,
                "fulfilled_count": fulfilled,
                "external_action_taken": False,
            },
        )

    def _status(self, state: WorkflowState) -> CommandResponse:
        summary = self._summary(state)
        message = f"{_state_name(state)} — {state.workflow_id}: {state.status.value.replace('_', ' ')}."
        if state.current_stage_id:
            message += f" Current step: {state.current_stage_id.replace('_', ' ')}."
        if state.blocker:
            message += f" Blocker: {state.blocker}."
        next_action = state.current_proposed_next_action()
        if next_action:
            message += f" Next: {next_action}"
        return CommandResponse("workflow", "blocked" if state.status.value == "blocked" else "healthy", message, summary)

    def _approval(self, state: WorkflowState) -> CommandResponse:
        pending = state.approval_status == "pending"
        message = f"{state.run_id}: " + (f"approval required for: {state.proposed_next_action}" if pending else f"approval status is {state.approval_status}.")
        return CommandResponse("approvals", "blocked" if pending else "healthy", message, self._summary(state))

    def _blocker(self, state: WorkflowState) -> CommandResponse:
        message = f"{state.run_id}: " + (f"blocked by {state.blocker}. Next: {state.proposed_next_action}" if state.blocker else "no blocker is recorded.")
        return CommandResponse("blockers", "blocked" if state.blocker else "healthy", message, self._summary(state))

    def _proposed(self, state: WorkflowState) -> CommandResponse:
        action = state.current_proposed_next_action() or "No current proposed next action is recorded."
        return CommandResponse("proposed", "healthy", f"{state.run_id}: {action}", self._summary(state))

    def _artefact(self, state: WorkflowState) -> CommandResponse:
        output = self.backend.latest_output(state)
        if output is None:
            return self._error("artefact", "artefact_unavailable", "No readable workflow artefact is recorded.")
        fields = sorted(str(key) for key in output)
        excerpt = _output_excerpt(output)
        message = f"Latest artefact for {state.run_id}: {', '.join(fields[:12])}."
        if excerpt:
            message += f"\n{excerpt}"
        data = self._summary(state)
        data["artefact_fields"] = fields
        data["excerpt"] = excerpt
        return CommandResponse("artefact", "healthy", message, data)

    @staticmethod
    def _summary(state: WorkflowState) -> dict[str, Any]:
        return workflow_state_summary(state)

    @staticmethod
    def _error(command: str, code: str, message: str) -> CommandResponse:
        return CommandResponse(command, "error", message, {"error_code": code})


def _state_name(state: WorkflowState) -> str:
    return workflow_state_name(state)


def _exact_terms(state: WorkflowState) -> set[str]:
    return {state.run_id.casefold(), state.entity_id.casefold(), state.client_id.casefold(), _state_name(state).casefold()}


def _search_terms(state: WorkflowState) -> str:
    return " ".join((*_exact_terms(state), state.workflow_id.casefold()))


def _output_excerpt(output: Mapping[str, Any]) -> str:
    preferred = ("blueprint_lite", "discovery_synthesis", "growth_opportunity", "draft_client_communication")
    for key in preferred:
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            compact = " ".join(value.split())
            return compact[:500] + ("…" if len(compact) > 500 else "")
    return ""


def _artifact_label(state: WorkflowState) -> str:
    labels = {
        "growth_diagnostic_to_blueprint_lite": "Gate 1 — the Blueprint Lite",
        "blueprint_lite_to_discovery_preparation": "The Discovery synthesis",
        "discovery_evidence_to_growth_sprint_proposal": "The Growth Sprint proposal",
        "research_to_growth_blueprint": "The Growth Blueprint",
    }
    return labels.get(state.workflow_id, "The review artefact")


def _research_focus(focus: Mapping[str, Any]) -> tuple[str, str]:
    kind = str(focus.get("kind") or "").strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {"gap": "evidence_gap", "question": "question", "hypothesis": "hypothesis"}
    kind = aliases.get(kind, kind)
    if kind not in {"evidence_gap", "question", "hypothesis"}:
        raise ValueError("research focus kind must be evidence_gap, question or hypothesis")
    statement = " ".join(str(focus.get("statement") or focus.get("question") or "").split())
    if len(statement) < 12 or len(statement) > 1000:
        raise ValueError("research focus statement must be specific and between 12 and 1000 characters")
    return kind, statement


def _merge_research_sources(existing: Any, supplied: list[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    values: list[Any] = []
    if isinstance(existing, list):
        values.extend(existing)
    if supplied is not None:
        values.extend(supplied)
    for item in values:
        if not isinstance(item, Mapping):
            raise ValueError("research source must be a structured object")
        source_id = str(item.get("source_id") or "").strip()
        policy = item.get("policy") if isinstance(item.get("policy"), Mapping) else {}
        if not source_id or policy.get("approved") is not True:
            raise ValueError("additional research sources must be complete and explicitly approved")
        candidate = dict(item)
        if source_id in merged and merged[source_id] != candidate:
            raise ValueError(f"conflicting research source definition: {source_id}")
        merged[source_id] = candidate
    return [merged[key] for key in sorted(merged)]
