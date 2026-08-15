from __future__ import annotations

from typing import Any


class TonyExecutiveToolRouter:
    """Select the most appropriate execution surface for an agency priority.

    Routing is intentionally deterministic and conservative. It prepares a handoff;
    it never claims that the selected tool has run or that an external mutation has
    occurred.
    """

    _CALENDAR_MARKERS = (
        "calendar",
        "schedule",
        "book a meeting",
        "book the meeting",
        "arrange a meeting",
        "set up a meeting",
        "meeting invite",
    )
    _GMAIL_MARKERS = (
        "email",
        "reply",
        "inbox",
        "thread",
        "follow up",
        "follow-up",
        "outreach",
        "send a note",
        "send the note",
        "send the message",
    )
    _NOTION_MARKERS = (
        "notion",
        "crm",
        "database",
        "record",
        "pipeline stage",
        "lead status",
        "update the lead",
        "update the client",
    )
    _REPLIT_MARKERS = (
        "website",
        "landing page",
        "site",
        "replit",
        "web page",
        "homepage",
    )
    _N8N_MARKERS = (
        "n8n",
        "workflow",
        "webhook",
        "automation flow",
        "automate",
        "integration flow",
    )
    _GITHUB_MARKERS = (
        "github",
        "repository",
        "pull request",
        "pr ",
        "code change",
        "runtime",
        "deployment",
        "backend",
        "test suite",
    )

    def route(self, priority: dict[str, Any]) -> dict[str, Any]:
        action = str(priority.get("action") or "").strip()
        label = str(priority.get("label") or "").strip()
        area = str(priority.get("area") or "").strip().casefold()
        text = f"{label} {action}".casefold()
        target = dict(priority.get("target") or {})

        worker = "Claude"
        rationale = "the work needs reasoning, drafting or synthesis before execution"

        if self._contains(text, self._CALENDAR_MARKERS):
            worker = "Google Calendar"
            rationale = "the next step is primarily scheduling or meeting coordination"
        elif self._contains(text, self._GMAIL_MARKERS):
            worker = "Gmail"
            rationale = "the next step depends on an email thread, reply or outreach action"
        elif self._contains(text, self._NOTION_MARKERS):
            worker = "Notion"
            rationale = "the next step is primarily a structured agency or commercial record action"
        elif self._contains(text, self._REPLIT_MARKERS):
            worker = "Replit"
            rationale = "the next step is a website or web-product implementation task"
        elif self._contains(text, self._N8N_MARKERS) or area == "automation":
            worker = "n8n"
            rationale = "the next step is an automation or workflow-orchestration task"
        elif self._contains(text, self._GITHUB_MARKERS) or area in {"engineering", "infrastructure"}:
            worker = "GitHub"
            rationale = "the next step is repository, runtime or deployment work"

        return {
            "worker": worker,
            "action": self._worker_action(worker, action),
            "then_owner": "Tony",
            "approval_required": self._approval_required(worker, action),
            "target": target,
            "routing_reason": rationale,
            "execution_truth": "handoff_prepared_only",
        }

    @staticmethod
    def _contains(text: str, markers: tuple[str, ...]) -> bool:
        return any(marker in text for marker in markers)

    @staticmethod
    def _worker_action(worker: str, action: str) -> str:
        requested = action or "advance the priority using the available evidence"
        if worker == "Claude":
            return f"prepare the reasoning or work product needed to advance this priority: {requested}"
        if worker == "Gmail":
            return f"work from the verified email thread needed to advance this priority: {requested}"
        if worker == "Google Calendar":
            return f"prepare the required scheduling action without inventing availability: {requested}"
        if worker == "Notion":
            return f"prepare the required structured record action against the authoritative workspace state: {requested}"
        if worker == "Replit":
            return f"prepare the website implementation needed to advance this priority: {requested}"
        if worker == "n8n":
            return f"prepare the workflow or automation change needed to advance this priority: {requested}"
        if worker == "GitHub":
            return f"prepare the repository change needed to advance this priority: {requested}"
        return requested

    @staticmethod
    def _approval_required(worker: str, action: str) -> bool:
        lowered = action.casefold()
        if worker == "Gmail" and any(marker in lowered for marker in ("send", "reply", "outreach", "follow up", "follow-up")):
            return True
        if worker == "Google Calendar":
            return True
        if worker in {"Notion", "Replit", "n8n", "GitHub"}:
            return True
        return True
