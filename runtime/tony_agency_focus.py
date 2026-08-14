from __future__ import annotations

from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyAgencyFocusCommandService:
    """Turn agency and commercial signals into one reasoned executive focus view."""

    _FOCUS_MARKERS = (
        "what should i focus on",
        "what should we focus on",
        "what matters now",
        "what matters most",
        "what should i do today",
        "what are my priorities",
        "what are our priorities",
        "top priorities",
        "where should i focus",
    )
    _RATIONALE_MARKERS = (
        "why",
        "why that",
        "why first",
        "why is that",
        "why should i",
        "why should we",
    )
    _FIRST_ACTION_MARKERS = (
        "do the first one",
        "do the first",
        "take the first one",
        "take the first",
        "go ahead with the first",
        "start with the first",
        "take care of the first",
        "do that first",
        "do that",
        "go ahead with that",
        "take that forward",
    )
    _INTERNAL_WORK_MARKERS = (
        "engineering",
        "infrastructure",
        "runtime",
        "repository",
        "deployment",
        "automation",
        "backend",
        "system work",
        "internal systems",
    )
    _CHOICE_MARKERS = (
        "let's work on",
        "lets work on",
        "i want to work on",
        "i'm going to work on",
        "im going to work on",
        "we should work on",
        "i think we should work on",
    )
    _AREA_PRIORITY = {
        "commercial": 0,
        "clients": 1,
        "delivery": 2,
        "finance": 3,
        "operations": 4,
        "automation": 5,
        "engineering": 6,
        "infrastructure": 7,
    }
    _BUSINESS_AREAS = {"commercial", "clients", "delivery", "finance", "operations", "automation"}
    _CURRENT_REVENUE_RISK_AREAS = {"clients", "delivery", "finance"}
    _REASON_EXPLANATIONS = {
        "current_revenue_or_delivery_risk": "it protects existing revenue or a current client commitment",
        "new_positive_commercial_intent": "there is fresh positive buying intent and response speed matters",
        "commercial_blocker": "it is actively blocking a commercial outcome",
        "overdue_commercial_commitment": "we have already made a commercial commitment and it is overdue",
        "matt_decision_required": "the work cannot progress without your judgement",
        "business_priority": "it is the strongest verified business priority once urgent risks and decisions are cleared",
    }

    def __init__(self, command_service) -> None:
        self.command_service = command_service
        self._last_priorities: tuple[dict[str, Any], ...] = ()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()

        if self._last_priorities and self._is_rationale_query(lowered):
            return self._explain_last_focus()

        if self._last_priorities and self._is_first_action_query(lowered):
            return self._prepare_first_priority_action()

        if self._last_priorities and self._is_internal_work_choice(lowered):
            first = self._last_priorities[0]
            if str(first.get("area") or "").casefold() not in {"engineering", "infrastructure"}:
                return self._challenge_internal_choice(normalized, first)

        if not any(marker in lowered for marker in self._FOCUS_MARKERS):
            return self.command_service.execute(command, objects)

        evidence = tuple(objects)
        agency_response = self.command_service.execute("morning", evidence)
        if agency_response.status == "error":
            return agency_response
        return self._focus_response(agency_response)

    def _focus_response(self, agency_response: CommandResponse) -> CommandResponse:
        data = dict(agency_response.data) if isinstance(agency_response.data, dict) else {}
        agency_state = data.get("agency_state") if isinstance(data.get("agency_state"), dict) else {}
        executive_items = agency_state.get("executive_items") if isinstance(agency_state.get("executive_items"), list) else []
        commercial_watch = data.get("commercial_watch") if isinstance(data.get("commercial_watch"), dict) else {}

        priorities: list[dict[str, Any]] = []

        for item in executive_items:
            if not isinstance(item, dict):
                continue
            area = str(item.get("area") or "").strip().casefold()
            blocked = bool(item.get("blocked"))
            if blocked and area in self._CURRENT_REVENUE_RISK_AREAS:
                priorities.append(self._agency_priority(item, tier=0, reason="current_revenue_or_delivery_risk"))

        positive_replies = commercial_watch.get("positive_replies")
        if isinstance(positive_replies, list):
            for reply in positive_replies:
                if isinstance(reply, dict):
                    priorities.append(self._positive_reply_priority(reply))

        for item in executive_items:
            if not isinstance(item, dict):
                continue
            area = str(item.get("area") or "").strip().casefold()
            if bool(item.get("blocked")) and area == "commercial":
                priorities.append(self._agency_priority(item, tier=15, reason="commercial_blocker"))

        overdue = commercial_watch.get("overdue")
        if isinstance(overdue, list):
            for follow_up in overdue:
                if isinstance(follow_up, dict):
                    priorities.append(self._overdue_priority(follow_up))

        for item in executive_items:
            if not isinstance(item, dict):
                continue
            area = str(item.get("area") or "").strip().casefold()
            if bool(item.get("requires_matt")) and area in self._BUSINESS_AREAS and not bool(item.get("blocked")):
                priorities.append(self._agency_priority(item, tier=30, reason="matt_decision_required"))

        for item in executive_items:
            if not isinstance(item, dict):
                continue
            area = str(item.get("area") or "").strip().casefold()
            if area not in self._BUSINESS_AREAS or bool(item.get("blocked")) or bool(item.get("requires_matt")):
                continue
            priorities.append(self._agency_priority(item, tier=50, reason="business_priority"))

        priorities = self._deduplicate_and_sort(priorities)
        top = priorities[:3]
        self._last_priorities = tuple(dict(item) for item in top)

        if not top:
            message = (
                "There is no verified agency issue demanding your attention right now. "
                "I would use the next block of time to create or advance a commercial opportunity rather than work on internal systems."
            )
            return CommandResponse(
                command="agency_focus",
                status="healthy",
                message=message,
                data={"intent": "synthesise_agency_focus", "priorities": [], "source_brief_status": agency_response.status},
            )

        first = top[0]
        lines = [f"Your first priority is {first['label']}. {first['action']}"]
        if len(top) > 1:
            lines.append("Then:")
            for priority in top[1:]:
                lines.append(f"- {priority['label']} — {priority['action']}")
        lines.append("I would leave engineering or infrastructure work alone unless it is directly blocking one of these agency outcomes.")

        return CommandResponse(
            command="agency_focus",
            status="attention" if any(item["tier"] < 50 for item in top) else "healthy",
            message="\n".join(lines),
            data={
                "intent": "synthesise_agency_focus",
                "priorities": top,
                "source_brief_status": agency_response.status,
                "commercial_watch": commercial_watch,
            },
        )

    def _explain_last_focus(self) -> CommandResponse:
        first = self._last_priorities[0]
        first_reason = self._reason_text(first)
        lines = [f"I put {first['label']} first because {first_reason}."]
        if len(self._last_priorities) > 1:
            second = self._last_priorities[1]
            lines.append(f"{second['label']} comes next because {self._reason_text(second)}, but it has less immediate business consequence.")
        lines.append("That ordering is evidence-led rather than absolute; if new client, revenue or delivery evidence appears, I would re-rank it.")
        return CommandResponse(
            command="agency_focus_rationale",
            status="healthy",
            message="\n".join(lines),
            data={
                "intent": "explain_agency_focus",
                "priorities": [dict(item) for item in self._last_priorities],
                "first_priority_reason": first.get("reason"),
            },
        )

    def _prepare_first_priority_action(self) -> CommandResponse:
        priority = dict(self._last_priorities[0])
        handoff = self._execution_handoff(priority)
        worker = handoff["worker"]
        action = handoff["action"]
        message = (
            f"Yes. I’ll take {priority['label']} forward first. "
            f"The next controlled step is for {worker} to {action}. "
            "I have prepared the handoff, but I have not claimed that any external tool, message or record change has happened yet."
        )
        if handoff["approval_required"]:
            message += " Any external send or irreversible change remains behind your approval."
        return CommandResponse(
            command="agency_focus_action",
            status="attention" if priority["tier"] < 50 else "healthy",
            message=message,
            data={
                "intent": "progress_top_agency_priority",
                "priority": priority,
                "execution_handoff": handoff,
                "execution_status": "ready_for_handoff",
                "external_action_taken": False,
            },
        )

    def _execution_handoff(self, priority: dict[str, Any]) -> dict[str, Any]:
        reason = str(priority.get("reason") or "")
        target = dict(priority.get("target") or {})
        if reason == "new_positive_commercial_intent":
            return {
                "worker": "Gmail",
                "action": "retrieve the verified reply thread so Tony can assess the response and prepare the right discovery follow-up",
                "then_owner": "Tony",
                "approval_required": True,
                "target": target,
            }
        if reason == "overdue_commercial_commitment":
            return {
                "worker": "Gmail",
                "action": "check the lead thread for a reply before Tony decides the next commercial move",
                "then_owner": "Tony",
                "approval_required": True,
                "target": target,
            }
        if bool(priority.get("requires_matt")):
            return {
                "worker": "Matt",
                "action": str(priority.get("action") or "make the required executive decision"),
                "then_owner": "Tony",
                "approval_required": False,
                "target": target,
            }
        return {
            "worker": "Claude",
            "action": f"prepare the work needed to advance this priority: {priority.get('action')}",
            "then_owner": "Tony",
            "approval_required": True,
            "target": target,
        }

    def _challenge_internal_choice(self, choice: str, first: dict[str, Any]) -> CommandResponse:
        reason = self._reason_text(first)
        message = (
            f"I would not prioritise {choice.rstrip('.')} yet. "
            f"{first['label']} has the stronger business consequence because {reason}. "
            "My recommendation is to clear that first, then return to the internal work. "
            "If you still choose the internal work, I will follow that decision rather than quietly overriding it."
        )
        return CommandResponse(
            command="agency_focus_challenge",
            status="attention",
            message=message,
            data={
                "intent": "challenge_lower_value_focus_choice",
                "proposed_choice": choice,
                "recommended_priority": dict(first),
                "external_action_taken": False,
            },
        )

    def _reason_text(self, priority: dict[str, Any]) -> str:
        reason = str(priority.get("reason") or "").strip()
        return self._REASON_EXPLANATIONS.get(reason, "it has the strongest verified business consequence in the current evidence")

    @classmethod
    def _is_rationale_query(cls, lowered: str) -> bool:
        return any(lowered == marker or lowered.startswith(marker + " ") for marker in cls._RATIONALE_MARKERS)

    @classmethod
    def _is_first_action_query(cls, lowered: str) -> bool:
        return any(lowered == marker or lowered.startswith(marker + " ") for marker in cls._FIRST_ACTION_MARKERS)

    @classmethod
    def _is_internal_work_choice(cls, lowered: str) -> bool:
        return any(marker in lowered for marker in cls._CHOICE_MARKERS) and any(marker in lowered for marker in cls._INTERNAL_WORK_MARKERS)

    def _agency_priority(self, item: dict[str, Any], *, tier: int, reason: str) -> dict[str, Any]:
        area = str(item.get("area") or "").strip().casefold()
        title = str(item.get("title") or "Agency work").strip()
        action = str(item.get("next_action") or "Review and decide the next action.").strip()
        return {
            "key": f"agency:{item.get('item_id') or title}",
            "tier": tier,
            "area_rank": self._AREA_PRIORITY.get(area, 99),
            "area": area,
            "label": title,
            "action": action,
            "reason": reason,
            "source": "agency_state",
            "requires_matt": bool(item.get("requires_matt")),
            "target": {"item_id": str(item.get("item_id") or ""), "area": area},
        }

    def _positive_reply_priority(self, item: dict[str, Any]) -> dict[str, Any]:
        contact = str(item.get("contact") or "A lead").strip()
        company = str(item.get("company") or "").strip()
        label = f"the positive reply from {contact} at {company}" if company else f"the positive reply from {contact}"
        action = str(item.get("recommended_next_action") or "Review the reply and decide whether to move to discovery.").strip()
        return {
            "key": f"positive_reply:{item.get('lead_id') or contact}",
            "tier": 10,
            "area_rank": 0,
            "area": "commercial",
            "label": label,
            "action": action,
            "reason": "new_positive_commercial_intent",
            "source": "commercial_watch",
            "requires_matt": False,
            "target": {"lead_id": str(item.get("lead_id") or ""), "contact": contact, "company": company},
        }

    @staticmethod
    def _overdue_priority(item: dict[str, Any]) -> dict[str, Any]:
        contact = str(item.get("contact") or "a lead").strip()
        company = str(item.get("company") or "").strip()
        due_on = str(item.get("due_on") or "").strip()
        label = f"the overdue follow-up with {contact} at {company}" if company else f"the overdue follow-up with {contact}"
        action = "Check for a reply and decide the next commercial move."
        if due_on:
            action = f"It was due on {due_on}; check for a reply and decide the next commercial move."
        return {
            "key": f"overdue:{item.get('commitment_id') or item.get('lead_id') or contact}",
            "tier": 20,
            "area_rank": 0,
            "area": "commercial",
            "label": label,
            "action": action,
            "reason": "overdue_commercial_commitment",
            "source": "commercial_watch",
            "requires_matt": False,
            "target": {
                "commitment_id": str(item.get("commitment_id") or ""),
                "lead_id": str(item.get("lead_id") or ""),
                "contact": contact,
                "company": company,
            },
        }

    @staticmethod
    def _deduplicate_and_sort(priorities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for priority in priorities:
            key = str(priority.get("key") or "")
            current = unique.get(key)
            if current is None or (priority["tier"], priority["area_rank"]) < (current["tier"], current["area_rank"]):
                unique[key] = priority
        return sorted(unique.values(), key=lambda item: (item["tier"], item["area_rank"], str(item["label"]).casefold()))
