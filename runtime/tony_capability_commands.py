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
    _FOLLOW_UP_MARKERS = (
        "tell me more",
        "what about",
        "more on",
        "more about",
        "go deeper",
        "why them",
        "why this",
    )

    def __init__(self, command_service, registry: TonyCapabilityRegistry | None = None) -> None:
        self.command_service = command_service
        self.registry = registry or TonyCapabilityRegistry()
        self._last_leads: tuple[InboundLead, ...] = ()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        name = normalized.split(" ", 1)[0].lower().lstrip("/") if normalized else ""
        if name not in self._COMMANDS:
            follow_up = self._lead_follow_up(normalized)
            if follow_up is not None:
                return follow_up
            response = self.command_service.execute(command, objects)
            return self._executive_response(command, response)

        configured = self._configured_features()
        snapshot = self.registry.snapshot(configured)
        return CommandResponse(
            command="capabilities",
            status=snapshot["status"],
            message=self.registry.telegram_summary(configured),
            data=snapshot,
        )

    @staticmethod
    def _reference_tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", value.casefold())
            if len(token) >= 3
        }

    def _lead_follow_up(self, command: str) -> CommandResponse | None:
        if not self._last_leads:
            return None
        lowered = command.casefold()
        if not any(marker in lowered for marker in self._FOLLOW_UP_MARKERS):
            return None

        command_tokens = self._reference_tokens(lowered)
        matches = []
        for lead in self._last_leads:
            reference_tokens = self._reference_tokens(" ".join((lead.contact, lead.company)))
            if command_tokens.intersection(reference_tokens):
                matches.append(lead)
        if len(matches) != 1:
            return None

        lead = matches[0]
        return CommandResponse(
            command="leads",
            status="healthy",
            message=render_inbound_leads((lead,), scope="selected lead", detailed=True),
            data={"scope": "selected lead", "count": 1, "leads": [lead.to_dict()]},
        )

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
        message = render_inbound_leads(
            leads,
            scope=scope,
            detailed=wants_lead_detail(command),
        )
        return CommandResponse(
            command=response.command,
            status=response.status,
            message=message,
            data=response.data,
        )

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
