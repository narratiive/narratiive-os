from __future__ import annotations

from typing import Any, Mapping

from runtime.executive_message import (
    ExecutiveConfidence,
    ExecutiveMessage,
    ExecutiveUrgency,
    build_executive_message,
)


_SUPPORTED_ACTIONS = frozenset({"health", "run.status", "job.get", "approval.list", "approval.get"})


def interpret_observability_result(
    *,
    action: str,
    data: Mapping[str, Any],
    evidence_reference: str,
) -> ExecutiveMessage:
    """Translate gateway observability data into a bounded executive interpretation.

    Raw gateway data remains owned by the orchestration response. This projection only
    uses explicit status/count fields and never exposes provider diagnostics, stack
    traces, credentials, or arbitrary gateway prose.
    """

    if action not in _SUPPORTED_ACTIONS:
        raise ValueError(f"unsupported observability action: {action}")
    if not evidence_reference.strip():
        raise ValueError("evidence_reference is required")

    evidence = [{"reference": evidence_reference, "label": "Narratiive OS gateway result"}]

    if action == "health":
        status = _clean(data.get("status"), "unknown")
        healthy = status.lower() in {"ok", "healthy", "ready", "available"}
        return build_executive_message(
            observation=f"Narratiive OS is reporting {status} health.",
            implication=(
                "Tony can continue normal orchestration."
                if healthy
                else "Automation reliability may be reduced until the platform state is checked."
            ),
            recommendation=(
                "Continue with the current priority queue."
                if healthy
                else "Review the health evidence before dispatching new work."
            ),
            human_effort="None." if healthy else "A short health review is required.",
            evidence=evidence,
            confidence=ExecutiveConfidence.HIGH,
            urgency=ExecutiveUrgency.ROUTINE if healthy else ExecutiveUrgency.TODAY,
            interruption_eligible=False,
        )

    if action == "run.status":
        status = _clean(data.get("status") or data.get("workflow_status"), "available")
        blocked = status.lower() in {"blocked", "failed", "awaiting_approval", "needs_revision"}
        return build_executive_message(
            observation=f"The workflow is {status}.",
            implication=(
                "Progress depends on a decision or corrective action."
                if blocked
                else "The workflow can remain in Tony's active delivery queue."
            ),
            recommendation=(
                "Review the recorded run evidence and resolve the outstanding gate."
                if blocked
                else "Allow Tony to continue tracking the run."
            ),
            human_effort="A focused review may be required." if blocked else "None at this stage.",
            evidence=evidence,
            confidence=ExecutiveConfidence.HIGH,
            urgency=ExecutiveUrgency.TODAY if blocked else ExecutiveUrgency.ROUTINE,
            interruption_eligible=False,
        )

    if action == "job.get":
        status = _clean(data.get("status"), "available")
        failed = status.lower() in {"failed", "blocked", "cancelled"}
        return build_executive_message(
            observation=f"The job is {status}.",
            implication=(
                "The associated deliverable will not advance without intervention."
                if failed
                else "No executive intervention is currently indicated."
            ),
            recommendation=(
                "Inspect the recorded job evidence and choose recovery or cancellation."
                if failed
                else "Keep the job under routine monitoring."
            ),
            human_effort="A brief decision is required." if failed else "None.",
            evidence=evidence,
            confidence=ExecutiveConfidence.HIGH,
            urgency=ExecutiveUrgency.TODAY if failed else ExecutiveUrgency.ROUTINE,
            interruption_eligible=False,
        )

    if action == "approval.list":
        count = _bounded_count(data.get("count"))
        return build_executive_message(
            observation=f"There {'is' if count == 1 else 'are'} {count} approval item{'s' if count != 1 else ''} waiting.",
            implication=(
                "Delivery is waiting for human judgement."
                if count
                else "No approval decision is currently holding delivery."
            ),
            recommendation=(
                "Review the approval queue in priority order."
                if count
                else "No approval action is needed."
            ),
            human_effort="A short decision pass is required." if count else "None.",
            evidence=evidence,
            confidence=ExecutiveConfidence.HIGH,
            urgency=ExecutiveUrgency.TODAY if count else ExecutiveUrgency.ROUTINE,
            interruption_eligible=False,
        )

    current = data.get("current")
    status = _clean(current.get("status") if isinstance(current, Mapping) else None, "available")
    waiting = status.lower() in {"awaiting_approval", "pending", "needs_revision"}
    return build_executive_message(
        observation=f"The approval is {status}.",
        implication=(
            "The gated work cannot advance until the recorded decision is made."
            if waiting
            else "The approval state does not currently require executive action."
        ),
        recommendation=(
            "Review the evidence and record an approve, revise, comment, or block decision."
            if waiting
            else "Keep the approval under routine monitoring."
        ),
        human_effort="A focused decision is required." if waiting else "None.",
        evidence=evidence,
        confidence=ExecutiveConfidence.HIGH,
        urgency=ExecutiveUrgency.TODAY if waiting else ExecutiveUrgency.ROUTINE,
        interruption_eligible=False,
    )


def _clean(value: Any, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    return text[:80] if text else fallback


def _bounded_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(count, 999))
