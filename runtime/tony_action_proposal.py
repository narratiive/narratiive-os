from __future__ import annotations

from typing import Any, Mapping

from runtime.tony_tool_routing import TonyExecutiveToolRouter


class TonyActionProposalService:
    """Turn an agent-interpreted action into a bounded Narratiive execution proposal.

    The language model owns semantic interpretation. This service receives structured
    intent and applies only deterministic worker/risk policy. It never dispatches work,
    grants approval, or claims execution.
    """

    def __init__(self, router: TonyExecutiveToolRouter | None = None) -> None:
        self.router = router or TonyExecutiveToolRouter()

    def propose(self, request: Mapping[str, Any]) -> dict[str, Any]:
        action = str(request.get("action") or "").strip()
        if not action:
            raise ValueError("action is required")
        if len(action) > 4000:
            raise ValueError("action is too long")

        target = request.get("target") or {}
        if not isinstance(target, dict):
            raise ValueError("target must be an object")

        priority = {
            "action": action,
            "label": str(request.get("label") or "").strip(),
            "area": str(request.get("area") or "").strip(),
            "target": dict(target),
        }
        handoff = self.router.route(priority)
        approval_required = bool(handoff.get("approval_required"))
        execution_mode = str(handoff.get("execution_mode") or "")

        if approval_required:
            next_step = "Ask Matt for explicit scoped approval before any dispatch or external mutation."
        elif execution_mode in {"autonomous_read", "autonomous_prepare"}:
            next_step = "Tony may proceed through an authorised bounded worker/tool and must verify returned evidence before claiming completion."
        else:
            next_step = "Do not execute until the control plane can classify the action safely."

        return {
            "ok": True,
            "status": "proposal_prepared",
            "proposal": {
                "requested_action": action,
                "label": priority["label"],
                "area": priority["area"],
                "worker": handoff.get("worker"),
                "worker_action": handoff.get("action"),
                "target": dict(handoff.get("target") or {}),
                "routing_reason": handoff.get("routing_reason"),
                "approval_required": approval_required,
                "approval_reason": handoff.get("approval_reason"),
                "execution_mode": execution_mode,
                "dispatch": dict(handoff.get("dispatch") or {}),
            },
            "next_step": next_step,
            "external_action_taken": False,
            "approval_granted": False,
            "execution_truth": "proposal_only_not_dispatched",
        }
