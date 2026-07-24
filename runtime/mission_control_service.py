from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.executive_message import (
    ExecutiveConfidence,
    ExecutiveMessage,
    ExecutiveUrgency,
    build_executive_message,
)
from runtime.mission_control import MissionControlSnapshot


@dataclass(frozen=True)
class MissionControlResponse:
    """Channel-neutral response for Mission Control consumers."""

    status: str
    message: str
    data: dict[str, Any]
    executive: ExecutiveMessage

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": "mission_control",
            "status": self.status,
            "message": self.message,
            "data": self.data,
            "executive": self.executive.to_dict(),
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
        github = snapshot.github_work
        github_approvals = (
            len(github.matt_approval_required) if github is not None else 0
        )

        message = (
            f"Mission Control is {snapshot.status}: "
            f"{len(active)} active workstream(s), {len(blocked)} blocked, "
            f"{len(snapshot.approvals_required)} operational approval(s), "
            f"{github_approvals} Matt GitHub review(s) required."
        )
        executive = self._executive_message(
            snapshot,
            active=active,
            blocked=blocked,
            disconnected=disconnected,
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
                "github_work": github.to_dict() if github is not None else None,
                "summary": {
                    "active_workstreams": len(active),
                    "blocked_workstreams": len(blocked),
                    "connection_issues": len(disconnected),
                    "approvals_required": len(snapshot.approvals_required),
                    "open_pull_requests": (
                        len(github.open_pull_requests) if github is not None else 0
                    ),
                    "active_issues": (
                        len(github.active_issues) if github is not None else 0
                    ),
                    "matt_github_reviews": github_approvals,
                },
            },
            executive=executive,
        )

    def telegram_reply(self, snapshot: MissionControlSnapshot) -> str:
        response = self.respond(snapshot)
        lines = [response.executive.render_compact()]

        if snapshot.blockers:
            lines.append("Blockers:")
            lines.extend(f"- {item}" for item in snapshot.blockers[:5])

        if snapshot.approvals_required:
            lines.append("Approvals:")
            lines.extend(f"- {item}" for item in snapshot.approvals_required[:5])

        if snapshot.github_work is not None:
            github = snapshot.github_work
            if github.matt_approval_required:
                lines.append("Matt GitHub reviews:")
                lines.extend(
                    f"- #{item.number} {item.title} — {item.url}"
                    for item in github.matt_approval_required[:5]
                )

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

    @staticmethod
    def _executive_message(
        snapshot: MissionControlSnapshot,
        *,
        active: list[dict[str, Any]],
        blocked: list[dict[str, Any]],
        disconnected: list[dict[str, Any]],
    ) -> ExecutiveMessage:
        evidence: list[str] = []
        for item in snapshot.workstreams:
            evidence.extend(item.evidence)
        for item in snapshot.connections:
            if item.evidence:
                evidence.append(item.evidence)
        if snapshot.github_work is not None:
            evidence.extend(
                item.evidence for item in snapshot.github_work.all_open_items
            )
        if not evidence:
            evidence.append(f"mission-control:{snapshot.generated_at}")

        if snapshot.blockers:
            observation = f"Narratiive OS has {len(snapshot.blockers)} recorded blocker(s)."
            implication = "Progress is constrained until the highest-priority recorded blocker is removed."
            recommendation = f"Resolve {snapshot.blockers[0]} before expanding the active backlog."
            human_effort = (
                "Review the named blocker only if it requires a credential, live-service action, "
                "or irreversible decision."
            )
            confidence = ExecutiveConfidence.HIGH
            urgency = ExecutiveUrgency.TODAY
        elif snapshot.approvals_required:
            observation = (
                f"Narratiive OS is operational with {len(snapshot.approvals_required)} recorded approval(s) waiting."
            )
            implication = "Approved work cannot advance to its next state until the decision is recorded."
            recommendation = f"Review the first approval: {snapshot.approvals_required[0]}."
            human_effort = "Make the approval decision; Tony should handle the downstream state change."
            confidence = ExecutiveConfidence.HIGH
            urgency = ExecutiveUrgency.TODAY
        elif (
            snapshot.github_work is not None
            and snapshot.github_work.matt_approval_required
        ):
            review = snapshot.github_work.matt_approval_required[0]
            observation = (
                "GitHub records "
                f"{len(snapshot.github_work.matt_approval_required)} pull request(s) "
                "with an outstanding review request for Matt."
            )
            implication = "The requested repository review is waiting for Matt's judgement."
            recommendation = f"Review GitHub pull request #{review.number}: {review.title}."
            human_effort = "Review the requested pull request; Tony must not approve or merge it."
            confidence = ExecutiveConfidence.HIGH
            urgency = ExecutiveUrgency.TODAY
        elif disconnected:
            observation = f"Mission Control records {len(disconnected)} connection issue(s)."
            implication = "Affected capabilities must remain unavailable rather than being represented as functional."
            recommendation = f"Keep {disconnected[0]['name']} fail-closed and continue work that does not depend on it."
            human_effort = "No action unless the connection requires credentials or a live account change."
            confidence = ExecutiveConfidence.HIGH
            urgency = ExecutiveUrgency.ROUTINE
        elif active:
            first = active[0]
            observation = f"Narratiive OS has {len(active)} active workstream(s) and no recorded blocker."
            implication = "The system can continue progressing through the existing backlog safely."
            recommendation = f"Continue {first['title']}: {first['next_action']}."
            human_effort = "No action unless Tony reports a genuine external dependency."
            confidence = ExecutiveConfidence.HIGH
            urgency = ExecutiveUrgency.ROUTINE
        else:
            observation = "Mission Control has no active workstream or recorded blocker."
            implication = "There is no evidence-backed next task in the current snapshot."
            recommendation = "Refresh repository state before assigning new work."
            human_effort = "No action required."
            confidence = ExecutiveConfidence.MEDIUM
            urgency = ExecutiveUrgency.ROUTINE

        return build_executive_message(
            observation=observation,
            implication=implication,
            recommendation=recommendation,
            human_effort=human_effort,
            evidence=tuple(dict.fromkeys(evidence)),
            confidence=confidence,
            urgency=urgency,
            interruption_eligible=False,
        )
