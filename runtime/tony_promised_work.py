from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from typing import Any

from runtime.models import WorkflowState
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
            ),
            key=lambda state: (state.created_at, state.run_id),
        )
        if not candidates:
            return None
        state = candidates[0]
        try:
            if state.status.value == "active":
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
            return self._deliver_once(
                state,
                "The promised internal work is complete and recorded. No consequential next step has been taken.",
                "work_complete",
            )
        return state

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
            return notification[:3500]
        conclusions = [
            " ".join(str(item).split())[:320]
            for item in delivery.get("conclusions", [])
            if str(item).strip()
        ][:3]
        points = " ".join(f"• {item}" for item in conclusions)
        return (
            "Gate 2 is ready. I’ve completed the Growth Sprint proposal and sent the full review copy to "
            "hello@narratiive.com. "
            + (points + " " if points else "")
            + "I need your judgement on the proposed engagement. You can approve it here, request a revision, or tell me what should change."
        )[:3500]
