from __future__ import annotations

from typing import Any


class TonyExecutiveToolRouter:
    """Select the most appropriate execution surface and approval boundary.

    Routing is deterministic and conservative. Tony may move ahead with reversible
    research, reading and preparation without asking Matt for permission every time.
    External sends, state-changing writes and other consequential mutations remain
    approval-gated. A handoff is still only a handoff until execution evidence returns.
    """

    _CALENDAR_MARKERS = (
        "calendar", "schedule", "book a meeting", "book the meeting", "arrange a meeting",
        "set up a meeting", "meeting invite", "availability", "free time",
    )
    _GMAIL_MARKERS = (
        "email", "reply", "inbox", "thread", "follow up", "follow-up", "outreach",
        "send a note", "send the note", "send the message",
    )
    _NOTION_MARKERS = (
        "notion", "crm", "database", "record", "pipeline stage", "lead status",
        "update the lead", "update the client",
    )
    _REPLIT_MARKERS = (
        "website", "landing page", "site", "replit", "web page", "homepage",
    )
    _N8N_MARKERS = (
        "n8n", "workflow", "webhook", "automation flow", "automate", "integration flow",
    )
    _GITHUB_MARKERS = (
        "github", "repository", "pull request", "pr ", "code change", "runtime",
        "deployment", "backend", "test suite",
    )
    _WRITE_MARKERS = (
        "send", "reply to", "follow up with", "follow-up with", "book ", "schedule ",
        "reschedule", "cancel", "invite", "update", "change", "create", "delete",
        "remove", "publish", "deploy", "merge", "commit", "push", "edit", "fix",
        "repair", "implement", "build", "write to", "add to", "automate",
    )
    _READ_MARKERS = (
        "check", "review", "inspect", "analyse", "analyze", "audit", "read", "retrieve",
        "find", "look up", "summarise", "summarize", "assess", "compare", "availability",
        "free time", "draft", "prepare", "develop", "research",
    )

    def route(self, priority: dict[str, Any]) -> dict[str, Any]:
        action = str(priority.get("action") or "").strip()
        label = str(priority.get("label") or "").strip()
        area = str(priority.get("area") or "").strip().casefold()
        text = f"{label} {action}".casefold()
        action_text = action.casefold()
        target = dict(priority.get("target") or {})

        worker = "Claude"
        rationale = "the work needs reasoning, drafting or synthesis before execution"

        # An explicit draft-only instruction is internal preparation even when its
        # evidence source or subject mentions Calendar/Gmail. This prevents Tony from
        # routing a request to *prepare* a response back into a stateful external tool.
        draft_only = (
            self._contains(action_text, ("prepare", "draft"))
            and self._contains(action_text, ("do not send", "don't send", "without sending", "not send"))
        )

        # Prefer the execution surface that owns the primary action, not a system
        # merely mentioned as the downstream destination.
        if draft_only:
            worker = "Claude"
            rationale = "the next step is explicitly internal draft preparation and must not mutate an external system"
        elif self._contains(text, self._CALENDAR_MARKERS):
            worker = "Google Calendar"
            rationale = "the next step is primarily scheduling or meeting coordination"
        elif self._contains(text, self._GMAIL_MARKERS):
            worker = "Gmail"
            rationale = "the next step depends on an email thread, reply or outreach action"
        elif self._contains(text, self._REPLIT_MARKERS):
            worker = "Replit"
            rationale = "the next step is a website or web-product implementation task"
        elif self._contains(text, self._N8N_MARKERS) or area == "automation":
            worker = "n8n"
            rationale = "the next step is an automation or workflow-orchestration task"
        elif self._contains(text, self._GITHUB_MARKERS) or area in {"engineering", "infrastructure"}:
            worker = "GitHub"
            rationale = "the next step is repository, runtime or deployment work"
        elif self._contains(text, self._NOTION_MARKERS):
            worker = "Notion"
            rationale = "the next step is primarily a structured agency or commercial record action"

        approval_required, execution_mode, approval_reason = self._execution_policy(worker, action)
        worker_action = self._worker_action(worker, action)
        dispatch = self._dispatch_contract(
            worker=worker,
            action=worker_action,
            target=target,
            execution_mode=execution_mode,
            approval_required=approval_required,
        )
        return {
            "worker": worker,
            "action": worker_action,
            "then_owner": "Tony",
            "approval_required": approval_required,
            "execution_mode": execution_mode,
            "approval_reason": approval_reason,
            "target": target,
            "routing_reason": rationale,
            "execution_truth": "handoff_prepared_only",
            "dispatch": dispatch,
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
    def _dispatch_contract(
        *,
        worker: str,
        action: str,
        target: dict[str, Any],
        execution_mode: str,
        approval_required: bool,
    ) -> dict[str, Any]:
        """Describe exactly what may be dispatched without claiming it already ran."""
        autonomous = execution_mode in {"autonomous_prepare", "autonomous_read"} and not approval_required
        if execution_mode == "autonomous_read":
            expected_evidence = "verified read result with source identifiers and no persisted mutation"
        elif execution_mode == "autonomous_prepare":
            expected_evidence = "returned internal work product ready for Tony review"
        else:
            expected_evidence = "explicit approval followed by verified execution evidence"
        return {
            "eligible": autonomous,
            "state": "ready_for_autonomous_dispatch" if autonomous else "awaiting_approval",
            "worker": worker,
            "instruction": action,
            "target": dict(target),
            "execution_mode": execution_mode,
            "expected_evidence": expected_evidence,
            "return_to": "Tony",
            "execution_truth": "not_dispatched",
        }

    @classmethod
    def _execution_policy(cls, worker: str, action: str) -> tuple[bool, str, str]:
        lowered = action.casefold().strip()

        # Claude reasoning/drafting is internal preparation: Tony should not stop and
        # ask Matt for permission simply to think, research or draft.
        if worker == "Claude":
            return False, "autonomous_prepare", "internal reasoning and preparation is reversible"

        # Reading evidence is safe to advance autonomously. Mutation verbs win when
        # an instruction contains both read and write language.
        has_write = cls._contains(lowered, cls._WRITE_MARKERS)
        has_read = cls._contains(lowered, cls._READ_MARKERS)

        if worker == "Gmail":
            if has_write:
                return True, "approval_gated_write", "external communication changes the agency's relationship with another person"
            return False, "autonomous_read", "reading a verified thread does not send or mutate external state"

        if worker == "Google Calendar":
            if has_write:
                return True, "approval_gated_write", "creating or changing a calendar commitment affects other people"
            return False, "autonomous_read", "checking availability is read-only and reversible"

        if worker in {"Notion", "Replit", "n8n", "GitHub"}:
            if has_write:
                return True, "approval_gated_write", "the requested step changes persisted agency, product or system state"
            if has_read:
                return False, "autonomous_read", "inspection or analysis can proceed without changing persisted state"
            return True, "approval_gated_write", "the action is ambiguous on a stateful platform, so Tony should fail conservatively"

        return True, "approval_gated_write", "the execution risk could not be classified safely"
