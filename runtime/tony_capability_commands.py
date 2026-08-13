from __future__ import annotations

import re
from typing import Any, Iterable

from runtime.executive_conversation import render_inbound_leads, wants_lead_detail
from runtime.inbound_leads import InboundLead
from runtime.tony_capabilities import TonyCapabilityRegistry
from runtime.tony_command_service import CommandResponse


class TonyCapabilityCommandService:
    """Expose Tony's capabilities and apply the default executive conversation layer."""

    _COMMANDS = {"capabilities", "commands", "help"}
    _FOLLOW_UP_MARKERS = ("tell me more", "what about", "more on", "more about", "go deeper", "why them", "why this")
    _ACTION_MARKERS = ("let's pursue", "lets pursue", "pursue", "take forward", "move forward with", "follow up with", "reach out to", "go after", "progress")
    _PREPARE_MARKERS = ("prepare it", "draft it", "go ahead", "do it", "get it ready", "prepare the outreach", "draft the outreach")
    _RETURN_MARKERS = ("review the returned draft", "review the draft", "claude returned", "worker returned", "here is the draft", "here's the draft")

    def __init__(self, command_service, registry: TonyCapabilityRegistry | None = None) -> None:
        self.command_service = command_service
        self.registry = registry or TonyCapabilityRegistry()
        self._last_leads: tuple[InboundLead, ...] = ()
        self._active_lead: InboundLead | None = None
        self._pending_delegation: dict[str, Any] | None = None

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        records = list(objects)
        name = normalized.split(" ", 1)[0].lower().lstrip("/") if normalized else ""
        if name not in self._COMMANDS:
            returned = self._worker_return(normalized, records)
            if returned is not None:
                return returned
            preparation = self._lead_preparation(normalized)
            if preparation is not None:
                return preparation
            action = self._lead_action(normalized)
            if action is not None:
                return action
            follow_up = self._lead_follow_up(normalized)
            if follow_up is not None:
                return follow_up
            response = self.command_service.execute(command, records)
            return self._executive_response(command, response)

        configured = self._configured_features()
        snapshot = self.registry.snapshot(configured)
        return CommandResponse(command="capabilities", status=snapshot["status"], message=self.registry.telegram_summary(configured), data=snapshot)

    @staticmethod
    def _reference_tokens(value: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) >= 3}

    def _resolve_lead_reference(self, command: str) -> InboundLead | None:
        if not self._last_leads:
            return None
        command_tokens = self._reference_tokens(command)
        matches = []
        for lead in self._last_leads:
            reference_tokens = self._reference_tokens(" ".join((lead.contact, lead.company)))
            if command_tokens.intersection(reference_tokens):
                matches.append(lead)
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _execution_plan(lead: InboundLead) -> list[dict[str, str]]:
        contact = lead.contact or "the lead"
        company = lead.company or "their business"
        return [
            {"owner": "Tony", "action": f"Prepare a concise commercial brief for {contact} at {company} using the lead evidence already captured."},
            {"owner": "Claude", "action": f"Draft a personalised first-touch approach for {contact}, grounded in the stated business problem and Narratiive's current proposition."},
            {"owner": "Tony", "action": "Review the draft for evidence, tone and commercial relevance before anything is sent."},
            {"owner": "Matt", "action": "Approve the first external outreach until a pre-authorised sending policy is explicitly in place."},
        ]

    def _lead_action(self, command: str) -> CommandResponse | None:
        lowered = command.casefold()
        if not any(marker in lowered for marker in self._ACTION_MARKERS):
            return None
        lead = self._resolve_lead_reference(lowered)
        if lead is None:
            return None

        self._active_lead = lead
        self._pending_delegation = None
        next_action = lead.recommended_next_action.strip()
        plan = self._execution_plan(lead)
        message = f"Good. I’ll treat {lead.contact}"
        if lead.company:
            message += f" at {lead.company}"
        message += " as the lead to progress."
        if next_action:
            message += f" Commercial objective: {next_action}"
        message += " I’d handle it this way: " + " ".join(f"{index + 1}) {step['owner']}: {step['action']}" for index, step in enumerate(plan))
        message += " Nothing has been sent or changed externally yet."
        return CommandResponse(
            command="lead_action",
            status="healthy",
            message=message,
            data={"intent": "progress_lead", "lead": lead.to_dict(), "next_action": next_action, "execution_plan": plan, "approval_required": True, "external_action_taken": False},
        )

    def _lead_preparation(self, command: str) -> CommandResponse | None:
        lowered = command.casefold()
        if self._active_lead is None or not any(marker in lowered for marker in self._PREPARE_MARKERS):
            return None
        lead = self._active_lead
        objective = lead.recommended_next_action.strip() or "Progress the opportunity with a relevant first-touch approach."
        brief = {
            "task_type": "personalised_first_touch",
            "owner": "Claude",
            "reviewer": "Tony",
            "contact": lead.contact,
            "company": lead.company,
            "business_signal": lead.ai_summary.strip() or lead.notes.strip(),
            "commercial_objective": objective,
            "constraints": [
                "Use only evidence present in the lead record and current Narratiive proposition.",
                "Keep the approach concise, specific and commercially useful.",
                "Do not send externally; return the draft to Tony for review.",
            ],
        }
        self._pending_delegation = brief
        message = (
            f"Yes. I’ve turned the decision on {lead.contact} into a delegation-ready brief for Claude. "
            "I’ll remain accountable for reviewing the returned draft before it comes back to you. "
            "The brief is ready to hand off, but I have not claimed delegation or external execution until a worker confirms receipt and returns an artefact."
        )
        return CommandResponse(
            command="lead_preparation",
            status="healthy",
            message=message,
            data={"intent": "delegate_lead_preparation", "lead": lead.to_dict(), "delegation_brief": brief, "delegation_status": "ready", "approval_required_for_send": True, "external_action_taken": False},
        )

    @staticmethod
    def _returned_artifact(records: list[dict[str, Any]]) -> tuple[str, str] | None:
        for record in records:
            if not isinstance(record, dict):
                continue
            worker = str(record.get("worker") or record.get("owner") or "worker").strip()
            for key in ("artifact", "content", "draft", "result"):
                value = record.get(key)
                if isinstance(value, str) and value.strip():
                    return worker, value.strip()
        return None

    def _worker_return(self, command: str, records: list[dict[str, Any]]) -> CommandResponse | None:
        if self._active_lead is None or self._pending_delegation is None:
            return None
        lowered = command.casefold()
        artifact = self._returned_artifact(records)
        if artifact is None and not any(marker in lowered for marker in self._RETURN_MARKERS):
            return None
        if artifact is None:
            return CommandResponse(
                command="delegated_work_review",
                status="error",
                message="I’m ready to review the delegated work, but I don’t have a returned draft or artefact to assess yet.",
                data={"intent": "review_delegated_work", "delegation_status": "awaiting_artifact", "external_action_taken": False},
            )

        worker, content = artifact
        lead = self._active_lead
        lowered_content = content.casefold()
        first_name = lead.contact.split()[0].casefold() if lead.contact else ""
        contact_present = bool(first_name and first_name in lowered_content)
        company_present = not lead.company or lead.company.casefold() in lowered_content
        substantive = len(content.split()) >= 35
        checks = {
            "contact_specific": contact_present,
            "company_specific": company_present,
            "substantive": substantive,
        }
        ready = all(checks.values())
        review_status = "ready_for_approval" if ready else "revision_required"
        if ready:
            assessment = "It passes the basic evidence-and-specificity gate and is ready for your approval."
        else:
            failed = ", ".join(key.replace("_", " ") for key, passed in checks.items() if not passed)
            assessment = f"I would not put this in front of you yet; it needs revision on: {failed}."
        message = (
            f"{worker} has returned work for {lead.contact}. I’ve reviewed the artefact against the delegation brief. "
            f"{assessment} Nothing has been sent externally."
        )
        return CommandResponse(
            command="delegated_work_review",
            status="healthy",
            message=message,
            data={
                "intent": "review_delegated_work",
                "delegation_status": "returned",
                "review_status": review_status,
                "worker": worker,
                "lead": lead.to_dict(),
                "artifact": content,
                "review_checks": checks,
                "approval_required_for_send": True,
                "external_action_taken": False,
            },
        )

    def _lead_follow_up(self, command: str) -> CommandResponse | None:
        if not self._last_leads:
            return None
        lowered = command.casefold()
        if not any(marker in lowered for marker in self._FOLLOW_UP_MARKERS):
            return None
        lead = self._resolve_lead_reference(lowered)
        if lead is None:
            return None
        self._active_lead = lead
        return CommandResponse(command="leads", status="healthy", message=render_inbound_leads((lead,), scope="selected lead", detailed=True), data={"scope": "selected lead", "count": 1, "leads": [lead.to_dict()]})

    def _executive_response(self, command: str, response: CommandResponse) -> CommandResponse:
        if response.command != "leads" or response.status == "error":
            return response
        raw_leads = response.data.get("leads", []) if isinstance(response.data, dict) else []
        if not isinstance(raw_leads, list):
            return response
        leads: list[InboundLead] = []
        for item in raw_leads:
            if not isinstance(item, dict):
                continue
            try:
                leads.append(InboundLead.from_mapping(item))
            except ValueError:
                continue
        self._last_leads = tuple(leads)
        scope = str(response.data.get("scope", "current"))
        return CommandResponse(command=response.command, status=response.status, message=render_inbound_leads(leads, scope=scope, detailed=wants_lead_detail(command)), data=response.data)

    def _configured_features(self) -> set[str]:
        features: set[str] = set()
        base = self.command_service
        while hasattr(base, "command_service"):
            base = base.command_service
        if getattr(base, "mission_control_loader", None) is not None:
            features.add("mission_control")
        if getattr(base, "github_configured", False):
            features.add("github")
        if getattr(base, "execution_journal", None) is not None:
            features.add("execution_journal")
        if getattr(self.command_service, "diagnostics_runner", None) is not None:
            features.add("diagnostics")
        return features
