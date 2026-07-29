from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage


LifecycleLoader = Callable[[], Iterable[ClientLifecycleRecord]]
LifecycleSaver = Callable[[ClientLifecycleRecord], None]


@dataclass(frozen=True, slots=True)
class ClientLifecycleCommandResult:
    status: str
    message: str
    record: ClientLifecycleRecord | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "record": self.record.to_dict() if self.record else None,
        }


class ClientLifecycleCommandService:
    """Deterministic read/advance commands for Tony's client lifecycle."""

    def __init__(self, loader: LifecycleLoader, saver: LifecycleSaver | None = None) -> None:
        self.loader = loader
        self.saver = saver

    def status(self, client_id: str) -> ClientLifecycleCommandResult:
        record = self._find(client_id)
        value = f" worth £{record.value_gbp:,}" if record.value_gbp is not None else ""
        blocker = f" Blocker: {record.blocker}" if record.blocked and record.blocker else ""
        return ClientLifecycleCommandResult(
            status="blocked" if record.blocked else "healthy",
            message=(
                f"{record.client_name} is at {record.stage.value.replace('_', ' ')}{value}. "
                f"Next: {record.next_action}{blocker}"
            ),
            record=record,
        )

    def advance(
        self,
        client_id: str,
        next_stage: ClientLifecycleStage,
        *,
        next_action: str,
        evidence: str,
    ) -> ClientLifecycleCommandResult:
        if self.saver is None:
            raise RuntimeError("client lifecycle persistence is not configured")
        if not evidence.strip():
            raise ValueError("lifecycle advancement requires evidence")
        current = self._find(client_id)
        advanced = current.advance(next_stage, next_action=next_action)
        advanced = ClientLifecycleRecord(
            client_id=advanced.client_id,
            client_name=advanced.client_name,
            stage=advanced.stage,
            owner=advanced.owner,
            next_action=advanced.next_action,
            evidence=(*current.evidence, evidence.strip()),
            value_gbp=advanced.value_gbp,
        )
        self.saver(advanced)
        return ClientLifecycleCommandResult(
            status="healthy",
            message=(
                f"Advanced {advanced.client_name} to "
                f"{advanced.stage.value.replace('_', ' ')}. Next: {advanced.next_action}"
            ),
            record=advanced,
        )

    def _find(self, client_id: str) -> ClientLifecycleRecord:
        target = client_id.strip().casefold()
        for record in self.loader():
            if record.client_id.casefold() == target or record.client_name.casefold() == target:
                return record
        raise LookupError(f"client lifecycle record not found: {client_id}")
