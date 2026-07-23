from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from runtime.progress_engine import CampaignProgress, RepositoryProgressEngine


@dataclass(frozen=True)
class CommandResponse:
    command: str
    status: str
    message: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "status": self.status,
            "message": self.message,
            "data": self.data,
        }


class TonyCommandService:
    """Expose deterministic Tony commands backed by canonical repository state."""

    def __init__(self, progress_engine: RepositoryProgressEngine) -> None:
        self.progress_engine = progress_engine

    def execute(
        self,
        command: str,
        objects: Iterable[dict[str, Any]],
    ) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        if not normalized:
            return self._error("", "empty_command", "No command was provided.")

        parts = normalized.split(" ", 1)
        name = parts[0].lower().lstrip("/")
        argument = parts[1].strip() if len(parts) == 2 else ""
        snapshot = self.progress_engine.build_snapshot(objects)

        if name in {"status", "progress", "progress_update"}:
            return self._status(name, snapshot)
        if name == "health":
            return self._health(snapshot)
        if name == "clients":
            return self._clients(snapshot)
        if name == "client":
            return self._client(argument, snapshot)
        if name in {"next", "what_next", "continue"}:
            return self._next(name, snapshot)

        return self._error(name, "unsupported_command", f"Unsupported command: {name}")

    def _status(self, command: str, snapshot: Any) -> CommandResponse:
        campaigns = [campaign.to_dict() for campaign in snapshot.campaigns]
        blocked = sum(1 for campaign in snapshot.campaigns if campaign.health == "blocked")
        message = (
            f"{len(campaigns)} campaign(s); {blocked} blocked; "
            f"repository status is {snapshot.status}."
        )
        return CommandResponse(
            command=command,
            status=snapshot.status,
            message=message,
            data={
                "campaign_count": len(campaigns),
                "blocked_count": blocked,
                "campaigns": campaigns,
                "validation": snapshot.validation.to_dict(),
            },
        )

    def _health(self, snapshot: Any) -> CommandResponse:
        validation = snapshot.validation.to_dict()
        status = "blocked" if validation["errors"] else "healthy"
        message = (
            f"Validated {validation['objects_validated']} object(s): "
            f"{len(validation['errors'])} error(s), {len(validation['warnings'])} warning(s)."
        )
        return CommandResponse("health", status, message, {"validation": validation})

    def _clients(self, snapshot: Any) -> CommandResponse:
        clients: dict[str, dict[str, Any]] = {}
        for campaign in snapshot.campaigns:
            entry = clients.setdefault(
                campaign.client_id,
                {
                    "client_id": campaign.client_id,
                    "client_name": campaign.client_name,
                    "campaign_count": 0,
                    "blocked_campaigns": 0,
                },
            )
            entry["campaign_count"] += 1
            if campaign.health == "blocked":
                entry["blocked_campaigns"] += 1

        data = sorted(clients.values(), key=lambda item: (item["client_name"].lower(), item["client_id"]))
        return CommandResponse(
            "clients",
            "healthy" if not snapshot.validation.errors else "blocked",
            f"{len(data)} client(s) found.",
            {"clients": data},
        )

    def _client(self, query: str, snapshot: Any) -> CommandResponse:
        if not query:
            return self._error("client", "missing_argument", "Client name or id is required.")

        needle = query.casefold()
        matches = [
            campaign
            for campaign in snapshot.campaigns
            if needle in campaign.client_id.casefold() or needle in campaign.client_name.casefold()
        ]
        if not matches:
            return self._error("client", "client_not_found", f"No client matched: {query}")

        exact = [
            campaign
            for campaign in matches
            if needle in {campaign.client_id.casefold(), campaign.client_name.casefold()}
        ]
        selected = exact or matches
        if len({campaign.client_id for campaign in selected}) > 1:
            return self._error(
                "client",
                "ambiguous_client",
                f"Multiple clients matched: {query}",
                {"matches": sorted({campaign.client_name for campaign in selected})},
            )

        campaigns = sorted(selected, key=lambda item: item.campaign_name.casefold())
        blocked = any(campaign.health == "blocked" for campaign in campaigns)
        return CommandResponse(
            "client",
            "blocked" if blocked else "healthy",
            f"{campaigns[0].client_name}: {len(campaigns)} campaign(s).",
            {
                "client_id": campaigns[0].client_id,
                "client_name": campaigns[0].client_name,
                "campaigns": [campaign.to_dict() for campaign in campaigns],
            },
        )

    def _next(self, command: str, snapshot: Any) -> CommandResponse:
        if not snapshot.campaigns:
            return CommandResponse(
                command,
                "empty",
                "No active campaign state was found.",
                {"next_actions": []},
            )

        ordered = sorted(
            snapshot.campaigns,
            key=lambda campaign: (
                campaign.health != "blocked",
                campaign.completion_percent,
                campaign.client_name.casefold(),
                campaign.campaign_name.casefold(),
            ),
        )
        actions = [self._action_payload(campaign) for campaign in ordered]
        primary = actions[0]
        return CommandResponse(
            command,
            "blocked" if primary["health"] == "blocked" else "ready",
            f"Next: {primary['next_action']} for {primary['client_name']} / {primary['campaign_name']}.",
            {"primary": primary, "next_actions": actions},
        )

    @staticmethod
    def _action_payload(campaign: CampaignProgress) -> dict[str, Any]:
        return {
            "client_id": campaign.client_id,
            "client_name": campaign.client_name,
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "health": campaign.health,
            "current_stage": campaign.current_stage,
            "current_status": campaign.current_status,
            "next_action": campaign.next_action,
            "blocker_codes": list(campaign.blocker_codes),
        }

    @staticmethod
    def _error(
        command: str,
        code: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> CommandResponse:
        payload = {"error_code": code}
        if data:
            payload.update(data)
        return CommandResponse(command, "error", message, payload)
