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

    def __init__(self, command_service) -> None:
        self.command_service = command_service

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold()
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

        # Protect existing revenue and delivery first when there is a real blocker.
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

        # Commercial blockers matter after protected-client risk but before routine follow-up work.
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

        # Decisions explicitly requiring Matt come before normal operating work.
        for item in executive_items:
            if not isinstance(item, dict):
                continue
            area = str(item.get("area") or "").strip().casefold()
            if bool(item.get("requires_matt")) and area in self._BUSINESS_AREAS and not bool(item.get("blocked")):
                priorities.append(self._agency_priority(item, tier=30, reason="matt_decision_required"))

        # Fill remaining space with the highest-value business work. Platform work is deliberately excluded here.
        for item in executive_items:
            if not isinstance(item, dict):
                continue
            area = str(item.get("area") or "").strip().casefold()
            if area not in self._BUSINESS_AREAS or bool(item.get("blocked")) or bool(item.get("requires_matt")):
                continue
            priorities.append(self._agency_priority(item, tier=50, reason="business_priority"))

        priorities = self._deduplicate_and_sort(priorities)
        top = priorities[:3]

        if not top:
            message = (
                "There is no verified agency issue demanding your attention right now. "
                "I would use the next block of time to create or advance a commercial opportunity rather than work on internal systems."
            )
            return CommandResponse(
                command="agency_focus",
                status="healthy",
                message=message,
                data={
                    "intent": "synthesise_agency_focus",
                    "priorities": [],
                    "source_brief_status": agency_response.status,
                },
            )

        first = top[0]
        lines = [
            f"Your first priority is {first['label']}. {first['action']}"
        ]
        if len(top) > 1:
            lines.append("Then:")
            for priority in top[1:]:
                lines.append(f"- {priority['label']} — {priority['action']}")
        lines.append(
            "I would leave engineering or infrastructure work alone unless it is directly blocking one of these agency outcomes."
        )

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
        }

    @staticmethod
    def _deduplicate_and_sort(priorities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for priority in priorities:
            key = str(priority.get("key") or "")
            current = unique.get(key)
            if current is None or (priority["tier"], priority["area_rank"]) < (current["tier"], current["area_rank"]):
                unique[key] = priority
        return sorted(
            unique.values(),
            key=lambda item: (item["tier"], item["area_rank"], str(item["label"]).casefold()),
        )
