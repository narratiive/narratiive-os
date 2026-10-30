from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote

from runtime.models import WorkflowState
from runtime.tony_internal_review_delivery import reviewable_artifact
from runtime.tony_workflow_commands import WorkflowCommandBackend


MessageSender = Callable[[str], Mapping[str, Any] | None]


class TonyPromisedWorkWorker:
    """Advance durable conversational commitments and proactively close the loop."""

    def __init__(self, backend: WorkflowCommandBackend, sender: MessageSender) -> None:
        self.backend = backend
        self.sender = sender

    def run_once(self) -> WorkflowState | None:
        candidates = sorted(
            (
                state
                for state in self.backend.list_states()
                if isinstance(state.input_payload.get("_promised_work"), Mapping)
                and not state.promised_work_delivery
                and not self._already_running(state)
            ),
            key=lambda state: (state.created_at, state.run_id),
        )
        if not candidates:
            return None
        state = candidates[0]
        try:
            if state.status.value == "active":
                current = state.stage(state.current_stage_id) if state.current_stage_id else None
                # A RUNNING step is already owned by the canonical coordinator.
                # Calling advance again would convert an interrupted/in-flight
                # provider request into a false workflow_step_not_ready blocker.
                if current is not None and current.status.value == "running":
                    return state
                state = self.backend.advance(state)
        except Exception as exc:
            return self._deliver_once(
                state,
                "I couldn’t continue the promised work reliably. The durable work item is preserved for recovery; "
                f"the current blocker is {type(exc).__name__}.",
                "worker_failure",
            )
        if state.status.value == "awaiting_approval":
            try:
                delivery = dict(self.backend.deliver_internal_review(state, recipient="hello@narratiive.com"))
            except Exception:
                delivery = {"delivered": False}
            message = self._gate_message(state, delivery)
            return self._deliver_once(state, message, "gate_ready")
        if state.status.value in {"blocked", "failed"}:
            blocker = str(state.blocker or "specialist work did not complete reliably").replace("_", " ")
            return self._deliver_once(
                state,
                "I couldn’t complete the promised work reliably. "
                f"I’ve preserved the work and failure evidence; it is blocked by {blocker}. "
                "I haven’t treated it as complete or moved past the gate.",
                "work_failed",
            )
        if state.status.value == "complete":
            artifact = reviewable_artifact(state)
            receipt = next(
                (item.get("receipt", {}) for item in reversed(state.external_action_receipts)
                 if item.get("receipt", {}).get("kind") == "internal_artifact_review_delivery"
                 and item.get("receipt", {}).get("message_id")
                 and artifact is not None
                 and item.get("receipt", {}).get("artifact_checksum") == artifact.checksum),
                {},
            )
            link = ("https://mail.google.com/mail/u/0/#all/" + quote(str(receipt.get("thread_id") or receipt["message_id"]), safe="")) if receipt else ""
            return self._deliver_once(
                state,
                (f"The promised internal work is complete and recorded. Review copy: {link}"
                 if link else "The work is recorded as complete, but no verified review-copy delivery is recorded. Review delivery needs recovery."),
                "work_complete" if link else "review_delivery_blocked",
            )
        return state

    @staticmethod
    def _already_running(state: WorkflowState) -> bool:
        # Leave in-flight work with its coordinator, but do not let it hide
        # later ready commitments or spin the polling loop without work.
        return (
            state.status.value == "active"
            and state.current_stage_id is not None
            and state.stage(state.current_stage_id).status.value == "running"
        )

    def _deliver_once(self, state: WorkflowState, message: str, kind: str) -> WorkflowState:
        marker = state.input_payload.get("_promised_work", {})
        commitment_id = str(marker.get("commitment_id") or "") if isinstance(marker, Mapping) else ""
        delivery_key = hashlib.sha256(
            f"{state.workspace_id}\0{state.run_id}\0{commitment_id}\0{kind}".encode("utf-8")
        ).hexdigest()
        state = self.backend.begin_promised_delivery(state, delivery_key=delivery_key, kind=kind)
        # An attempting record is written before the provider call. A crash in
        # the narrow send/receipt window therefore becomes an explicit ambiguous
        # delivery instead of a blind replay and duplicate Telegram message.
        try:
            evidence = dict(self.sender(message) or {})
        except Exception:
            return state
        if not str(evidence.get("message_id") or "").strip():
            return state
        return self.backend.finish_promised_delivery(
            state,
            delivery_key=delivery_key,
            evidence={
                "provider": "telegram",
                "message_id": str(evidence.get("message_id") or ""),
                "date": evidence.get("date"),
            },
        )

    @staticmethod
    def _gate_message(state: WorkflowState, delivery: Mapping[str, Any]) -> str:
        if delivery.get("delivered") is not True:
            return (
                "The promised work has reached its review gate, but I couldn’t verify delivery of the full review copy. "
                "I’ve kept the gate pending and won’t claim it was emailed."
            )
        notification = str(delivery.get("telegram_notification") or "").strip()
        if notification:
            link = str(delivery.get("review_link") or "").strip()
            return notification[:2800] + (f"\nReview copy: {link}" if link else "")
        conclusions = [
            " ".join(str(item).split())[:320]
            for item in delivery.get("conclusions", [])
            if str(item).strip()
        ][:3]
        points = " ".join(f"• {item}" for item in conclusions)
        return (
            "The promised work is ready for review. I sent the full review copy to "
            "hello@narratiive.com. "
            + (points + " " if points else "")
            + "Please approve it here or request changes."
            + (f" Review copy: {delivery['review_link']}" if delivery.get("review_link") else "")
        )[:3500]
