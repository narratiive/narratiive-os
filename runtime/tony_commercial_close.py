from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyCommercialCloseCommandService:
    """Convert verified proposal acceptance intent into an approval-gated close.

    A positive reply is not a won deal. This layer requires Tony to surface the
    unresolved commercial-close checks and requires Matt to make an explicit,
    scoped close attestation before Notion may be moved to Won. Tony only treats
    the close as authoritative after verified Notion mutation evidence returns.
    Onboarding remains a downstream step; this layer merely exposes a verified
    onboarding-ready state after the authoritative commercial close.
    """

    CLOSE_APPROVALS = {
        "confirm commercial close",
        "confirm the commercial close",
        "mark it won",
        "mark this won",
        "mark the opportunity won",
        "close it as won",
    }

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
        if pending and normalized in self.CLOSE_APPROVALS:
            return self._close(pending)

        response = self.command_service.execute(command, objects)
        return self._prepare(response)

    def _prepare(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        judgement = data.get("commercial_judgement") if isinstance(data.get("commercial_judgement"), dict) else {}
        if data.get("execution_status") != "proposal_outcome_verified" or judgement.get("disposition") != "proposal_acceptance_intent":
            return response

        outcome = data.get("proposal_outcome") if isinstance(data.get("proposal_outcome"), dict) else {}
        gmail = data.get("gmail_reply_evidence") if isinstance(data.get("gmail_reply_evidence"), dict) else {}
        reply_id = str(gmail.get("message_id") or gmail.get("gmail_message_id") or "").strip()
        if not reply_id:
            return response

        completed = set(str(item) for item in self.state.get("completed", []) if item)
        existing = self.state.get("pending") if isinstance(self.state.get("pending"), dict) else {}
        if reply_id in completed:
            return response
        if existing.get("acceptance_message_id") == reply_id:
            return self._pending_close_response(response, data, existing, repeated=True)

        pending = {
            "acceptance_message_id": reply_id,
            "proposal_message_id": str(outcome.get("gmail_message_id") or ""),
            "lead_id": str(outcome.get("lead_id") or ""),
            "contact": str(outcome.get("contact") or ""),
            "company": str(outcome.get("company") or ""),
            "acceptance_evidence": dict(gmail),
        }
        self.state["pending"] = pending
        self._persist()
        return self._pending_close_response(response, data, pending, repeated=False)

    def _pending_close_response(
        self,
        response: CommandResponse,
        data: dict[str, Any],
        pending: dict[str, Any],
        *,
        repeated: bool,
    ) -> CommandResponse:
        data["execution_status"] = "commercial_close_approval_required"
        data["commercial_close"] = {
            "state": "awaiting_matt_attestation_and_approval",
            "deal_won": False,
            "approval_required": True,
            "attestation": {
                "scope_and_deliverables_confirmed": "required",
                "commercial_terms_confirmed": "required",
                "contract_requirement_satisfied_or_not_required": "required",
                "payment_or_purchase_order_requirement_satisfied_or_not_required": "required",
            },
            **self._public_pending(pending),
        }
        label = str(pending.get("company") or pending.get("contact") or "the opportunity")
        if repeated:
            message = (
                response.message
                + f" Acceptance intent for {label} is already verified and the commercial close is still pending. "
                "A generic approval will not mark it won. Say 'confirm commercial close' only when the agreed scope and deliverables are settled, the commercial terms are accepted, any contract requirement is satisfied or explicitly not required, and any payment or purchase-order requirement is satisfied or explicitly not required."
            )
        else:
            message = (
                response.message
                + f" Acceptance intent is verified for {label}, but I am not calling the deal won yet. "
                "Before I change the authoritative commercial state, confirm that the agreed scope and deliverables are settled, the commercial terms are accepted, any contract requirement is satisfied or explicitly not required, and any payment or purchase-order requirement is satisfied or explicitly not required. "
                "When those are genuinely true, say 'confirm commercial close'. That phrase is a scoped attestation and approval for the Notion Won update only; it does not start onboarding automatically."
            )
        return CommandResponse(response.command, response.status, message, data)

    def _close(self, pending: dict[str, Any]) -> CommandResponse:
        notion = self.dispatchers.get("Notion")
        if notion is None:
            return CommandResponse(
                "commercial_close",
                "healthy",
                "Commercial close approval is recorded, but no live Notion dispatcher is configured. I have not marked the deal won.",
                {
                    "execution_status": "commercial_close_notion_dispatcher_unavailable",
                    "commercial_close": {"state": "approved_pending_execution", "deal_won": False, **self._public_pending(pending)},
                    "external_action_taken": False,
                },
            )

        dispatch = {
            "worker": "Notion",
            "state": "approved_pending_execution",
            "execution_mode": "approval_gated_write",
            "approval_granted": True,
            "approval_scope": "verified_proposal_acceptance_commercial_close",
            "execution_truth": "not_dispatched",
            "target": {
                "lead_id": pending.get("lead_id", ""),
                "contact": pending.get("contact", ""),
                "company": pending.get("company", ""),
                "area": "commercial",
            },
            "payload": {
                "kind": "commercial_close_state_update",
                "status": "Won",
                "deal_won": True,
                "acceptance_message_id": pending.get("acceptance_message_id", ""),
                "proposal_message_id": pending.get("proposal_message_id", ""),
                "close_attested_by": "Matt",
                "close_attestation": {
                    "scope_and_deliverables_confirmed": True,
                    "commercial_terms_confirmed": True,
                    "contract_requirement_satisfied_or_not_required": True,
                    "payment_or_purchase_order_requirement_satisfied_or_not_required": True,
                },
            },
            "instruction": (
                "Update the authoritative commercial opportunity to Won. Preserve the verified proposal and acceptance message identifiers. "
                "Record that the close was explicitly attested and approved by Matt. Do not create onboarding records or trigger delivery in this write."
            ),
            "expected_evidence": "verified Notion mutation with record identifier and Won status",
            "return_to": "Tony",
        }
        try:
            evidence = notion(dict(dispatch))
        except Exception as exc:
            return CommandResponse(
                "commercial_close",
                "healthy",
                f"The approved Notion commercial-close update failed: {exc}. I have not marked the deal won.",
                {
                    "execution_status": "commercial_close_notion_write_failed",
                    "commercial_close": {"state": "approved_pending_execution", "deal_won": False, **self._public_pending(pending)},
                    "external_action_taken": False,
                },
            )

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        record_id = str(evidence.get("page_id") or evidence.get("record_id") or "").strip() if isinstance(evidence, dict) else ""
        returned_status = str(evidence.get("status") or evidence.get("commercial_status") or evidence.get("stage") or "").strip().casefold() if isinstance(evidence, dict) else ""
        if not verified or not record_id or returned_status not in {"won", "closed won", "closed_won"}:
            detail = reason if not verified else "missing record identifier or verified Won status"
            return CommandResponse(
                "commercial_close",
                "healthy",
                f"The Notion close evidence was insufficient ({detail}). I am not treating the opportunity as won.",
                {
                    "execution_status": "commercial_close_notion_write_unverified",
                    "commercial_close": {"state": "approved_pending_execution", "deal_won": False, **self._public_pending(pending)},
                    "notion_evidence": dict(evidence) if isinstance(evidence, dict) else {},
                    "external_action_taken": False,
                },
            )

        acceptance_id = str(pending.get("acceptance_message_id") or "")
        completed = [str(item) for item in self.state.get("completed", []) if item]
        if acceptance_id and acceptance_id not in completed:
            completed.append(acceptance_id)
        self.state = {"pending": None, "completed": completed[-100:]}
        self._persist()

        close = {
            "state": "won_verified",
            "deal_won": True,
            "notion_record_id": record_id,
            "onboarding_ready": True,
            "onboarding_started": False,
            **self._public_pending(pending),
        }
        return CommandResponse(
            "commercial_close",
            "healthy",
            f"Commercial close verified. Notion now records the opportunity as Won on record {record_id}. The deal is now authoritative and ready for onboarding, but I have not started onboarding yet.",
            {
                "execution_status": "commercial_close_verified",
                "commercial_close": close,
                "notion_evidence": dict(evidence),
                "onboarding": {"state": "ready", "approval_required": True, "started": False, **self._public_pending(pending)},
                "external_action_taken": True,
            },
        )

    @staticmethod
    def _public_pending(pending: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in pending.items() if key != "acceptance_evidence"}

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "completed": []}
        return value if isinstance(value, dict) else {"pending": None, "completed": []}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.store_path)
