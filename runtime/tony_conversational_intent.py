from __future__ import annotations

import re
from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyConversationalIntentCommandService:
    """Keep natural language out of Tony's legacy command-parser failure path.

    Existing executive services still get first refusal so their richer contextual
    behaviour is preserved. Only an unresolved *natural-language* request is
    intercepted here. Explicit slash commands retain the deterministic legacy
    command semantics, including unsupported-command errors for unknown commands.
    """

    _FOCUS_MARKERS = (
        "what should i focus on",
        "what should we focus on",
        "what matters now",
        "what matters most",
        "what should i do today",
        "what are my priorities",
        "what are our priorities",
        "where should i focus",
    )
    _DISCOVERY_INVITE_RE = re.compile(
        r"^(?:please\s+)?invite\s+(?P<person>.+?)\s+(?:for|to)\s+(?:a\s+)?discovery(?:\s+call|\s+conversation)?[.!?]*$",
        re.IGNORECASE,
    )

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
        materialized = tuple(objects)
        if not normalized or normalized.startswith("/"):
            return self.command_service.execute(command, materialized)

        response = self.command_service.execute(command, materialized)
        if not self._is_legacy_unsupported(response):
            return response

        lowered = normalized.casefold().rstrip("?!.")
        if any(marker in lowered for marker in self._FOCUS_MARKERS):
            # Canonicalise the wording and give the existing executive focus layer
            # one deterministic retry. This specifically protects Telegram/n8n
            # paths that previously leaked through to the first-word parser.
            retried = self.command_service.execute("What should I focus on today?", materialized)
            if not self._is_legacy_unsupported(retried):
                return retried

        invite = self._DISCOVERY_INVITE_RE.match(normalized)
        if invite:
            person = invite.group("person").strip()
            return CommandResponse(
                command="conversational_intent",
                status="attention",
                message=(
                    f"I understand: invite {person} to a discovery call. "
                    "I will treat that as a commercial workflow, not a system command. "
                    "The safe first step is to ground the contact and availability before preparing the invitation; "
                    "I have not sent a message or created a calendar event yet."
                ),
                data={
                    "intent": "invite_to_discovery",
                    "person": person,
                    "workflow": "discovery_invitation",
                    "next_controlled_step": "resolve the contact and verify availability before preparing the invitation",
                    "approval_boundary": "external send and calendar creation remain approval-gated",
                    "external_action_taken": False,
                    "legacy_command_fallback_suppressed": True,
                },
            )

        return CommandResponse(
            command="conversation",
            status="attention",
            message=(
                "I understood that as a conversational request, not a system command. "
                "I do not yet have a grounded workflow for that exact request, so I will not invent an action. "
                "Ask me naturally another way or give me the business outcome you want, and I will route it if the capability exists."
            ),
            data={
                "intent": "unresolved_conversational_request",
                "original_request": normalized,
                "legacy_command_fallback_suppressed": True,
                "external_action_taken": False,
            },
        )

    @staticmethod
    def _is_legacy_unsupported(response: CommandResponse) -> bool:
        data = response.data if isinstance(response.data, dict) else {}
        return response.status == "error" and data.get("error_code") == "unsupported_command"
