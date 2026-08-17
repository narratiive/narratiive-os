from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyPostDiscoveryCommercialCommandService:
    """Turn a verified discovery review into a bounded, approval-gated next move."""

    APPROVALS = {"do that", "do it", "go ahead", "yes do that", "yes, do that", "prepare it", "prepare the proposal"}

    def __init__(self, command_service, dispatchers: Mapping[str, Any] | None = None, *, store_path: Path) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.state = self._load()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold().rstrip("?!.,")
        pending = self.state.get("pending") if isinstance(self.state.get("pending"), dict) else None
        if pending and normalized in self.APPROVALS:
            return self._prepare(pending)
        response = self.command_service.execute(command, objects)
        data = response.data if isinstance(response.data, dict) else {}
        if data.get("execution_status") == "discovery_outcome_review_ready":
            return self._route(response)
        return response

    def _route(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data)
        outcome = data.get("discovery_outcome") if isinstance(data.get("discovery_outcome"), dict) else {}
        review = outcome.get("review_evidence") if isinstance(outcome.get("review_evidence"), dict) else {}
        recommendation = str(outcome.get("recommended_next_action") or "").strip()
        combined = " ".join(str(review.get(key) or "") for key in ("disposition", "recommendation", "recommended_next_action", "next_action", "summary")).casefold()
        positive = any(token in combined for token in ("proposal", "advance", "proceed", "buying signal", "positive"))
        stop = any(token in combined for token in ("no fit", "not a fit", "decline", "stop", "close", "nurture"))
        if not positive or stop:
            data["execution_status"] = "post_discovery_no_proposal_recommended"
            data["post_discovery_commercial"] = {"state": "recommendation_only", "recommended_next_action": recommendation, "write_actions_allowed": False}
            return CommandResponse(response.command, response.status, response.message + " I am not progressing this into proposal preparation automatically. Any close, nurture or Notion stage change remains a separate approval-gated decision.", data)
        pending = {
            "calendar_event_id": str(outcome.get("calendar_event_id") or ""),
            "lead_id": str(outcome.get("lead_id") or ""),
            "contact": str(outcome.get("contact") or ""),
            "company": str(outcome.get("company") or ""),
            "meeting_evidence": dict(outcome.get("meeting_evidence") or {}) if isinstance(outcome.get("meeting_evidence"), dict) else {},
            "review_evidence": dict(review),
            "recommended_next_action": recommendation,
        }
        self.state["pending"] = pending
        self._persist()
        data["execution_status"] = "post_discovery_proposal_approval_required"
        data["post_discovery_commercial"] = {"state": "awaiting_preparation_approval", "approval_required": True, "write_actions_allowed": False, **pending}
        return CommandResponse(response.command, response.status, response.message + " The evidence supports preparing a proposal. I have not commissioned or sent one yet. Say 'do that' to approve proposal preparation; sending it will remain a later, separate approval gate.", data)

    def _prepare(self, pending: dict[str, Any]) -> CommandResponse:
        claude = self.dispatchers.get("Claude")
        if claude is None:
            return CommandResponse("post_discovery_commercial", "healthy", "Proposal preparation is approved, but no live Claude dispatcher is configured. Nothing has been sent or changed externally.", {"execution_status": "proposal_preparation_dispatcher_unavailable", "external_action_taken": False})
        dispatch = {
            "eligible": True,
            "state": "approved_pending_execution",
            "worker": "Claude",
            "instruction": "Prepare a concise Narratiive proposal grounded only in the verified discovery evidence and commercial review supplied. Include the diagnosed business problem, recommended scope, intended outcomes, assumptions/evidence gaps and a clear next step. Do not send the proposal, update Notion, create Calendar events or change any external state.",
            "target": {"lead_id": pending.get("lead_id", ""), "contact": pending.get("contact", ""), "company": pending.get("company", ""), "area": "commercial"},
            "execution_mode": "approved_prepare",
            "approval_granted": True,
            "approval_scope": "post_discovery_proposal_preparation",
            "expected_evidence": "evidence-grounded proposal draft for Tony review",
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
            "payload": {"kind": "post_discovery_proposal_prepare", "meeting_evidence": pending.get("meeting_evidence", {}), "review_evidence": pending.get("review_evidence", {})},
        }
        try:
            evidence = claude(dict(dispatch))
        except Exception as exc:
            return CommandResponse("post_discovery_commercial", "healthy", f"Claude could not prepare the approved proposal: {exc}. Nothing has been sent.", {"execution_status": "proposal_preparation_failed", "external_action_taken": False})
        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            return CommandResponse("post_discovery_commercial", "healthy", f"Claude returned proposal material, but it did not satisfy the verified work-product contract ({reason}). Nothing has been sent.", {"execution_status": "proposal_preparation_unverified", "external_action_taken": False})
        self.state["pending"] = None
        self.state["last_prepared"] = {**dict(pending), "proposal_evidence": dict(evidence)}
        self._persist()
        return CommandResponse("post_discovery_commercial", "healthy", "The approved proposal preparation is complete and verified. The draft is ready for Tony review; nothing has been sent and no commercial state has changed.", {"execution_status": "post_discovery_proposal_draft_ready", "proposal_evidence": dict(evidence), "post_discovery_commercial": {"state": "proposal_draft_ready", **dict(pending)}, "approval_required_for_send": True, "external_action_taken": False})

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "last_prepared": None}
        return value if isinstance(value, dict) else {"pending": None, "last_prepared": None}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.store_path)
