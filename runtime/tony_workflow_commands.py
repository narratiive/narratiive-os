from __future__ import annotations

import json
import hashlib
import shlex
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage
from runtime.models import WorkflowState
from runtime.serialization import workflow_from_dict, workflow_to_dict
from runtime.tony_command_service import CommandResponse
from runtime.tony_workflow_runtime import TonyWorkflowRuntime, build_tony_workflow_runtime


class WorkflowCommandBackend(Protocol):
    def list_states(self) -> tuple[WorkflowState, ...]: ...
    def approve(self, state: WorkflowState, *, approver: str, rationale: str) -> WorkflowState: ...
    def reject(self, state: WorkflowState, *, reviewer: str, rationale: str) -> WorkflowState: ...
    def resume(self, state: WorkflowState) -> WorkflowState: ...
    def advance(self, state: WorkflowState) -> WorkflowState: ...
    def recover(self) -> int: ...
    def latest_output(self, state: WorkflowState) -> Mapping[str, Any] | None: ...


class FileWorkflowCommandBackend:
    """Operate existing scoped workflow runs through the canonical runtime API."""

    def __init__(self, root: str | Path, *, dispatchers=None, environ=None) -> None:
        self.root = Path(root).resolve()
        self.dispatchers = dispatchers
        self.environ = environ

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
            states.append(state)
        return tuple(states)

    def approve(self, state: WorkflowState, *, approver: str, rationale: str) -> WorkflowState:
        runtime = self._runtime(state)
        runtime.approve(state.run_id, approver=approver, rationale=rationale)
        return runtime.runs.load_run(state.run_id)

    def reject(self, state: WorkflowState, *, reviewer: str, rationale: str) -> WorkflowState:
        runtime = self._runtime(state)
        runtime.reject_for_revision(state.run_id, reviewer=reviewer, rationale=rationale)
        return runtime.runs.load_run(state.run_id)

    def resume(self, state: WorkflowState) -> WorkflowState:
        runtime = self._runtime(state)
        runtime.resume(state.run_id)
        return runtime.runs.load_run(state.run_id)

    def advance(self, state: WorkflowState) -> WorkflowState:
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
            outcome = runtime.handoff(state.run_id, lifecycle)
            return runtime.runs.load_run(outcome.next_run_id or f"{state.run_id}-{runtime.coordinator.registry.resolve(state.workflow_id).next_workflow_id}")
        runtime.advance(state.run_id, lifecycle)
        return runtime.runs.load_run(state.run_id)

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

    def _runtime(self, state: WorkflowState) -> TonyWorkflowRuntime:
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
    }

    def __init__(self, command_service, backend: WorkflowCommandBackend) -> None:
        self.command_service = command_service
        self.backend = backend

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
            if name == "proposed":
                return self._proposed(state)
            if name in {"approve", "reject", "revise"}:
                if not principal_id.strip():
                    return self._error(name, "authorised_principal_required", "This decision requires an authenticated human identity.")
                if not rationale:
                    return self._error(name, "rationale_required", f"Use /{name} <run or company> because <reason>.")
                if name == "approve":
                    changed = self.backend.approve(state, approver=principal_id, rationale=rationale)
                    return CommandResponse(name, "healthy", f"Approved {changed.run_id} for its exact proposed action. No external action was performed.", self._summary(changed))
                changed = self.backend.reject(state, reviewer=principal_id, rationale=rationale)
                return CommandResponse("reject", "healthy", f"Revision requested for {changed.run_id}; progression remains stopped until revised work passes quality.", self._summary(changed))
            if name == "resume":
                changed = self.backend.resume(state)
                return CommandResponse(name, "healthy", f"Resumed {changed.run_id} from persisted state. No external action was performed.", self._summary(changed))
            changed = self.backend.advance(state)
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

    def _status(self, state: WorkflowState) -> CommandResponse:
        summary = self._summary(state)
        message = f"{_state_name(state)} — {state.workflow_id}: {state.status.value.replace('_', ' ')}."
        if state.current_stage_id:
            message += f" Current step: {state.current_stage_id.replace('_', ' ')}."
        if state.blocker:
            message += f" Blocker: {state.blocker}."
        if state.proposed_next_action:
            message += f" Next: {state.proposed_next_action}"
        return CommandResponse("workflow", "blocked" if state.status.value == "blocked" else "healthy", message, summary)

    def _approval(self, state: WorkflowState) -> CommandResponse:
        pending = state.approval_status == "pending"
        message = f"{state.run_id}: " + (f"approval required for: {state.proposed_next_action}" if pending else f"approval status is {state.approval_status}.")
        return CommandResponse("approvals", "blocked" if pending else "healthy", message, self._summary(state))

    def _blocker(self, state: WorkflowState) -> CommandResponse:
        message = f"{state.run_id}: " + (f"blocked by {state.blocker}. Next: {state.proposed_next_action}" if state.blocker else "no blocker is recorded.")
        return CommandResponse("blockers", "blocked" if state.blocker else "healthy", message, self._summary(state))

    def _proposed(self, state: WorkflowState) -> CommandResponse:
        action = state.proposed_next_action or "No proposed next action is recorded."
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
        current = state.stage(state.current_stage_id) if state.current_stage_id else None
        latest = next((stage for stage in reversed(state.stages) if stage.output_artifacts), None)
        return {
            "run_id": state.run_id,
            "workflow_id": state.workflow_id,
            "entity_id": state.entity_id,
            "client_id": state.client_id,
            "company": _state_name(state),
            "status": state.status.value,
            "current_step": state.current_stage_id,
            "attempt_count": len(current.attempts) if current else 0,
            "quality_passed": current.quality_result.get("passed") if current and current.quality_result else (latest.quality_result.get("passed") if latest and latest.quality_result else None),
            "approval_status": state.approval_status,
            "approval_required": state.approval_status == "pending",
            "blocker": state.blocker,
            "proposed_next_action": state.proposed_next_action,
            "latest_artefact_id": latest.output_artifacts[-1].artifact_id if latest else None,
            "external_action_taken": state.external_action_taken,
            "updated_at": state.updated_at,
        }

    @staticmethod
    def _error(command: str, code: str, message: str) -> CommandResponse:
        return CommandResponse(command, "error", message, {"error_code": code})


def _state_name(state: WorkflowState) -> str:
    payload = state.input_payload
    candidates = (
        payload.get("company"), payload.get("company_name"),
        payload.get("company_context", {}).get("name") if isinstance(payload.get("company_context"), Mapping) else None,
        payload.get("client_context", {}).get("name") if isinstance(payload.get("client_context"), Mapping) else None,
    )
    return next((str(value).strip() for value in candidates if str(value or "").strip()), state.entity_id or state.client_id)


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
