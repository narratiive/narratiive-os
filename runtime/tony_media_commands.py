from __future__ import annotations

from typing import Any, Iterable

from runtime.media_control import CanonicalMediaSnapshot, MediaControlService
from runtime.tony_command_service import CommandResponse


class TonyMediaCommandService:
    """Read-only Tony media queries over canonical, audited media state."""

    _COMMANDS = {"media", "media-integrations", "media_integrations", "health"}
    _MODES = {"today", "7d", "creative", "pacing", "recommendations"}

    def __init__(self, command_service, media_control: MediaControlService) -> None:
        self.command_service = command_service
        self.media_control = media_control

    def __getattr__(self, name: str):
        return getattr(self.command_service, name)

    @classmethod
    def supports(cls, command: str) -> bool:
        normalized = " ".join(command.strip().split())
        name = normalized.split(" ", 1)[0].lower().lstrip("/") if normalized else ""
        return name in cls._COMMANDS

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        parts = normalized.split(" ") if normalized else []
        name = parts[0].lower().lstrip("/") if parts else ""
        if not self.supports(command):
            return self.command_service.execute(command, objects)
        if name == "health":
            base = self.command_service.execute(command, objects)
            return CommandResponse(
                command=base.command,
                status=base.status,
                message=base.message,
                data={**base.data, "media_integrations": self.media_control.diagnostics()},
            )
        if name in {"media-integrations", "media_integrations"}:
            diagnostics = self.media_control.diagnostics()
            unhealthy = [
                provider
                for provider in ("meta", "tiktok", "google")
                if diagnostics[provider]["health"] != "healthy"
            ]
            return CommandResponse(
                command="media-integrations",
                status="degraded" if unhealthy else "healthy",
                message=(
                    "Media integrations require attention: " + ", ".join(unhealthy)
                    if unhealthy
                    else "Meta, TikTok and Google read-only media integrations are healthy."
                ),
                data=diagnostics,
            )

        arguments = parts[1:]
        mode = next((item.casefold() for item in arguments if item.casefold() in self._MODES), "summary")
        query = " ".join(item for item in arguments if item.casefold() not in self._MODES).strip()
        snapshots = self.media_control.snapshots()
        if query:
            needle = query.casefold()
            snapshots = tuple(
                item
                for item in snapshots
                if needle in {
                    item.identity.client_id.casefold(),
                    item.identity.brand_id.casefold(),
                    item.identity.campaign_id.casefold(),
                }
            )
        if not snapshots:
            return CommandResponse(
                command="media",
                status="empty",
                message="No verified media snapshot matched the request.",
                data={"query": query, "mode": mode, "external_action_taken": False},
            )

        recommendations = self.media_control.analyse(snapshots)
        payload = self._payload(snapshots, recommendations, mode)
        critical = sum(1 for item in recommendations if item.severity == "critical")
        return CommandResponse(
            command="media",
            status="attention_required" if critical else "ready",
            message=(
                f"{len(snapshots)} verified provider snapshot(s); "
                f"{len(recommendations)} recommendation(s); {critical} critical. "
                "No media mutation or spend action was taken."
            ),
            data=payload,
        )

    @staticmethod
    def _payload(snapshots, recommendations, mode: str) -> dict[str, Any]:
        provider_rows = []
        currencies = set()
        total_spend = None
        for snapshot in snapshots:
            spend = snapshot.metric("spend")
            currencies.add(snapshot.currency)
            if spend and spend.value is not None:
                total_spend = (total_spend or 0) + spend.value
            row = {
                "provider": snapshot.provider.value,
                "campaign_id": snapshot.identity.campaign_id,
                "provider_campaign_id": snapshot.provider_mapping.campaign_id,
                "period": {"start": snapshot.period_start, "end": snapshot.period_end},
                "currency": snapshot.currency,
                "attribution_contexts": sorted({metric.attribution_context for metric in snapshot.metrics}),
                "campaign_status": snapshot.campaign_status,
                "review_status": snapshot.review_status,
                "tracking_status": snapshot.tracking_status,
                "metrics": {metric.name: metric.to_dict() for metric in snapshot.metrics},
            }
            if mode == "creative":
                row["creative_mappings"] = [
                    {
                        "narratiive_asset_id": item.narratiive_asset_id,
                        "campaign_world_id": item.campaign_world_id,
                        "creative_territory": item.creative_territory,
                        "format": item.format,
                        "hook": item.hook,
                        "message": item.message,
                        "audience": item.audience,
                        "placement": item.placement,
                        "provider_creative_ids": list(item.provider_creative_ids),
                        "provider_ad_ids": list(item.provider_ad_ids),
                    }
                    for item in snapshot.creative_mappings
                ]
            provider_rows.append(row)
        comparable_total = total_spend is not None and len(currencies) == 1
        return {
            "mode": mode,
            "providers": provider_rows,
            "total_spend": str(total_spend) if comparable_total else None,
            "total_spend_currency": next(iter(currencies)) if comparable_total else None,
            "cross_provider_total_available": comparable_total,
            "measurement_warning": (
                "Provider metrics retain provider-specific attribution and measurement definitions; "
                "they must not be treated as directly equivalent."
            ),
            "recommendations": [item.to_dict() for item in recommendations],
            "human_approval_required": any(item.human_approval_required for item in recommendations),
            "external_action_taken": False,
        }
