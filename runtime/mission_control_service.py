from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.mission_control import MissionControlSnapshot


@dataclass(frozen=True)
class MissionControlResponse:
    """Channel-neutral response for Mission Control consumers."""

    status: str
    message: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": "mission_control",
            "status": self.status,
            "message": self.message,
            "data": self.data,
        }


class MissionControlService:
    """Turn a deterministic Mission Control snapshot into concise operator output."""

    TELEGRAM_LIMIT = 3500

    def respond(self, snapshot: MissionControlSnapshot) -> MissionControlResponse:
        workstreams = [item.to_dict() for item in snapshot.workstreams]
        connections = [item.to_dict() for item in snapshot.connections]
        active = [item for item in workstreams if item["state"] not in {"used", "unknown"}]
        blocked = [item for item in workstreams if item["state"] == "blocked"]
        disconnected = [
            item for item in connections if item["state"] in {"not_connected", "degraded"}
        ]

        message = (
            f"Mission Control is {snapshot.status}: "
            f"{len(active)} active workstream(s), {len(blocked)} blocked, "
            f"{len(snapshot.approvals_required)} approval(s) required."
        )
        return MissionControlResponse(
            status=snapshot.status,
            message=message,
            data={
                "generated_at": snapshot.generated_at,
                "progress": snapshot.progress,
                "workstreams": workstreams,
                "connections": connections,
                "approvals_required": list(snapshot.approvals_required),
                "blockers": list(snapshot.blockers),
                "summary": {
                    "active_workstreams": len(active),
                    "blocked_workstreams": len(blocked),
                    "connection_issues": len(disconnected),
                    "approvals_required": len(snapshot.approvals_required),
                },
            },
        )

    def telegram_reply(self, snapshot: MissionControlSnapshot) -> str:
        response = self.respond(snapshot)
        lines = [response.message]

        if snapshot.blockers:
            lines.append("Blockers:")
            lines.extend(f"- {item}" for item in snapshot.blockers[:5])

        if snapshot.approvals_required:
            lines.append("Approvals:")
            lines.extend(f"- {item}" for item in snapshot.approvals_required[:5])

        actionable = [
            item
            for item in snapshot.workstreams
            if item.state not in {"used", "unknown"}
        ]
        if actionable:
            lines.append("Next work:")
            for item in actionable[:5]:
                suffix = f" — BLOCKED: {item.blocker}" if item.blocker else ""
                lines.append(f"- {item.title}: {item.next_action}{suffix}")

        reply = "\n".join(lines)
        if len(reply) <= self.TELEGRAM_LIMIT:
            return reply
        return reply[: self.TELEGRAM_LIMIT - 1].rstrip() + "…"
