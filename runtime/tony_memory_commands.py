from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from runtime.executive_memory import ExecutiveMemoryStore, MemoryKind, MemoryScope
from runtime.tony_command_service import CommandResponse


class TonyMemoryCommandService:
    """Bring durable executive continuity into Tony's live command surface."""

    RECALL_COMMANDS = {
        "mission",
        "mission_control",
        "brief",
        "client",
        "next",
        "what_next",
        "continue",
        "status",
        "progress",
        "progress_update",
    }
    KIND_ALIASES = {
        "decision": MemoryKind.DECISION,
        "commitment": MemoryKind.COMMITMENT,
        "approval": MemoryKind.APPROVAL,
        "context": MemoryKind.CONTEXT,
        "outcome": MemoryKind.OUTCOME,
        "evidence": MemoryKind.EVIDENCE,
        "assumption": MemoryKind.ASSUMPTION,
    }

    def __init__(
        self,
        command_service,
        store: ExecutiveMemoryStore,
        *,
        agency_id: str = "narratiive",
    ) -> None:
        self.command_service = command_service
        self.store = store
        self.agency_id = agency_id

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        parts = normalized.split(" ", 1) if normalized else [""]
        name = parts[0].lower().lstrip("/")
        argument = parts[1].strip() if len(parts) == 2 else ""

        if name in {"memory", "recall", "context"}:
            return self._recall(argument)
        if name == "remember":
            return self._remember(argument)

        response = self.command_service.execute(command, objects)
        if name not in self.RECALL_COMMANDS or response.status == "error":
            return response

        scope = self._scope(argument if name == "client" else "")
        records = self.store.select(
            scope=scope,
            kinds=(
                MemoryKind.DECISION,
                MemoryKind.COMMITMENT,
                MemoryKind.APPROVAL,
                MemoryKind.CONTEXT,
                MemoryKind.OUTCOME,
            ),
            minimum_importance=3,
            limit=3,
        )
        if not records:
            return response

        continuity = [f"{record.kind.value}: {record.summary}" for record in records]
        data = dict(response.data)
        data["executive_memory"] = continuity
        message = response.message + "\nContinuity: " + " | ".join(continuity)
        return replace(response, message=message, data=data)

    def _recall(self, argument: str) -> CommandResponse:
        records = self.store.select(
            scope=self._scope(argument),
            kinds=(
                MemoryKind.DECISION,
                MemoryKind.COMMITMENT,
                MemoryKind.APPROVAL,
                MemoryKind.CONTEXT,
                MemoryKind.OUTCOME,
            ),
            minimum_importance=2,
            limit=8,
        )
        if not records:
            return CommandResponse(
                command="memory",
                status="ok",
                message="No executive memory is recorded for this scope yet.",
                data={"records": []},
            )
        lines = [f"{record.kind.value}: {record.summary}" for record in records]
        return CommandResponse(
            command="memory",
            status="ok",
            message="Executive continuity:\n" + "\n".join(f"- {line}" for line in lines),
            data={"records": lines},
        )

    def _remember(self, argument: str) -> CommandResponse:
        kind_name, separator, summary = argument.partition(" ")
        kind = self.KIND_ALIASES.get(kind_name.casefold())
        if not separator or kind is None or not summary.strip():
            return CommandResponse(
                command="remember",
                status="error",
                message=(
                    "Use /remember <decision|commitment|approval|context|outcome|evidence|assumption> "
                    "<summary>."
                ),
                data={"error_code": "invalid_memory_command"},
            )
        requires_matt = kind is MemoryKind.APPROVAL
        record = self.store.append(
            kind=kind,
            summary=summary,
            scope=self._scope(""),
            source="telegram",
            importance=4,
            requires_matt=requires_matt,
        )
        return CommandResponse(
            command="remember",
            status="ok",
            message=f"Remembered {kind.value}: {record.summary}",
            data={"record_id": record.record_id, "kind": kind.value},
        )

    def _scope(self, client_id: str) -> MemoryScope:
        return MemoryScope(
            agency_id=self.agency_id,
            client_id=client_id.strip().casefold() or None,
        )
