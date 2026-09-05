from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from runtime.models import WorkflowState


NotionDispatcher = Callable[[dict[str, Any]], dict[str, Any]]


class WorkflowBusinessProjectionService:
    """Prepare and explicitly execute idempotent workflow projections into Notion.

    Runtime remains execution truth. The append-only local event log records the exact
    projection proposed, its approval, dispatch ambiguity, and verified receipt.
    """

    def __init__(self, root: str | Path, dispatcher: NotionDispatcher | None = None) -> None:
        self.root = Path(root)
        self.events_path = self.root / "events.jsonl"
        self.lock_path = self.root / ".lock"
        self.dispatcher = dispatcher

    def prepare(self, state: WorkflowState) -> dict[str, Any]:
        projection = self._projection(state)
        with self._lock():
            events = self._events()
            completed = self._event(events, projection["projection_key"], {"verified", "reconciled"})
            if completed:
                return {**projection, "projection_status": "verified", "record_id": completed.get("record_id")}
            existing = self._event(events, projection["projection_key"], {"prepared", "dispatching", "failed"})
            if not existing:
                self._append({"event": "prepared", **projection})
            status = str((existing or {}).get("event") or "prepared")
        return {**projection, "projection_status": status}

    def sync(
        self,
        state: WorkflowState,
        *,
        approver: str,
        rationale: str,
    ) -> dict[str, Any]:
        if not approver.strip() or not rationale.strip():
            raise ValueError("Notion projection requires an authenticated approver and rationale")
        projection = self.prepare(state)
        key = projection["projection_key"]
        if self.dispatcher is None:
            return {**projection, "projection_status": "notion_dispatcher_unavailable", "external_action_taken": False}
        with self._lock():
            events = self._events()
            completed = self._event(events, key, {"verified", "reconciled"})
            if completed:
                return {**projection, "projection_status": "duplicate_suppressed", "record_id": completed.get("record_id"), "external_action_taken": False}
            if self._event(events, key, {"dispatching", "failed"}):
                return {**projection, "projection_status": "reconciliation_required", "external_action_taken": False}
            self._append({
                "event": "dispatching",
                "projection_key": key,
                "run_id": state.run_id,
                "approved_by": approver.strip(),
                "rationale": rationale.strip(),
                "recorded_at": _now(),
            })
        dispatch = {
            "worker": "Notion",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "workflow_business_state_projection",
            "execution_truth": "not_dispatched",
            "idempotency_key": key,
            "target": {
                "lead_id": state.entity_id,
                "client_id": state.client_id,
                "workspace_id": state.workspace_id,
                "area": "commercial",
            },
            "payload": {"kind": "workflow_business_state_projection", **projection},
            "instruction": "Project the supplied runtime-derived workflow summary onto the matching Notion business record. Do not execute workflow work, contact anyone, or infer any unreported completion.",
            "expected_evidence": "verified Notion mutation with record identifier and exact projection key",
            "return_to": "Tony",
        }
        try:
            evidence = self.dispatcher(dispatch)
        except Exception as exc:
            self._record_failure(key, state.run_id, f"dispatch_error:{type(exc).__name__}")
            return {**projection, "projection_status": "reconciliation_required", "external_action_taken": False}
        record_id = str(evidence.get("record_id") or evidence.get("page_id") or "").strip() if isinstance(evidence, Mapping) else ""
        returned_key = str(evidence.get("projection_key") or evidence.get("idempotency_key") or "").strip() if isinstance(evidence, Mapping) else ""
        if not isinstance(evidence, Mapping) or evidence.get("external_action_taken") is not True or not record_id or returned_key != key:
            self._record_failure(key, state.run_id, "unverified_notion_evidence")
            return {**projection, "projection_status": "reconciliation_required", "external_action_taken": False}
        with self._lock():
            self._append({
                "event": "verified",
                "projection_key": key,
                "run_id": state.run_id,
                "record_id": record_id,
                "recorded_at": _now(),
            })
        return {**projection, "projection_status": "verified", "record_id": record_id, "external_action_taken": True}

    def reconcile(self, state: WorkflowState, observed: Mapping[str, Any]) -> dict[str, Any]:
        projection = self._projection(state)
        observed_key = str(observed.get("projection_key") or "").strip()
        record_id = str(observed.get("record_id") or observed.get("page_id") or "").strip()
        if observed_key != projection["projection_key"] or not record_id:
            return {**projection, "projection_status": "diverged", "external_action_taken": False}
        with self._lock():
            if not self._event(self._events(), observed_key, {"verified", "reconciled"}):
                self._append({"event": "reconciled", "projection_key": observed_key, "run_id": state.run_id, "record_id": record_id, "recorded_at": _now()})
        return {**projection, "projection_status": "reconciled", "record_id": record_id, "external_action_taken": False}

    def _projection(self, state: WorkflowState) -> dict[str, Any]:
        latest = next((stage for stage in reversed(state.stages) if stage.output_artifacts), None)
        payload = {
            "workflow_run_id": state.run_id,
            "workflow_id": state.workflow_id,
            "lifecycle_stage": _lifecycle_stage(state.workflow_id),
            "workflow_status": state.status.value,
            "outstanding_approval": state.approval_status == "pending",
            "approval_status": state.approval_status,
            "blocker": state.blocker,
            "proposed_next_action": state.current_proposed_next_action(),
            "latest_artifact_id": latest.output_artifacts[-1].artifact_id if latest else None,
            "runtime_updated_at": state.updated_at,
            "external_action_taken": state.external_action_taken,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return {**payload, "projection_key": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}

    def _record_failure(self, key: str, run_id: str, reason: str) -> None:
        with self._lock():
            self._append({"event": "failed", "projection_key": key, "run_id": run_id, "reason": reason, "recorded_at": _now()})

    def _events(self) -> list[dict[str, Any]]:
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        except (OSError, UnicodeDecodeError) as exc:
            raise RuntimeError("workflow projection history is unreadable") from exc
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError("workflow projection history is malformed") from exc
            if not isinstance(item, dict):
                raise RuntimeError("workflow projection history is malformed")
            events.append(item)
        return events

    @staticmethod
    def _event(events: list[dict[str, Any]], key: str, kinds: set[str]) -> dict[str, Any] | None:
        return next((item for item in reversed(events) if item.get("projection_key") == key and item.get("event") in kinds), None)

    def _append(self, event: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(event), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _lifecycle_stage(workflow_id: str) -> str:
    if workflow_id == "growth_diagnostic_to_blueprint_lite":
        return "blueprint_lite"
    if workflow_id == "blueprint_lite_to_discovery_preparation":
        return "discovery"
    if workflow_id == "discovery_evidence_to_growth_sprint_proposal":
        return "proposal"
    if workflow_id in {"growth_sprint_to_research_engine", "research_to_growth_blueprint"}:
        return "delivery"
    return "unchanged"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
