from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Literal

ClientHealth = Literal["healthy", "watch", "at_risk"]
CommitmentStatus = Literal["open", "completed", "blocked"]


@dataclass(frozen=True, slots=True)
class ClientCommitment:
    commitment_id: str
    description: str
    owner: str
    due_on: date | None = None
    status: CommitmentStatus = "open"
    blocker: str | None = None

    def __post_init__(self) -> None:
        if not self.commitment_id.strip():
            raise ValueError("commitment_id is required")
        if not self.description.strip():
            raise ValueError("description is required")
        if not self.owner.strip():
            raise ValueError("owner is required")
        if self.status == "blocked" and (self.blocker is None or not self.blocker.strip()):
            raise ValueError("blocked commitment requires blocker")
        if self.status != "blocked" and self.blocker is not None:
            raise ValueError("blocker is only valid for blocked commitments")

    def is_overdue(self, *, as_of: date) -> bool:
        return self.status == "open" and self.due_on is not None and self.due_on < as_of


@dataclass(frozen=True, slots=True)
class ClientRecord:
    client_id: str
    name: str
    last_contact_on: date
    revenue_value: Decimal = Decimal("0.00")
    next_action: str | None = None
    risk_note: str | None = None
    commitments: tuple[ClientCommitment, ...] = ()

    def __post_init__(self) -> None:
        if not self.client_id.strip():
            raise ValueError("client_id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if self.revenue_value < 0:
            raise ValueError("revenue_value must not be negative")
        if self.next_action is not None and not self.next_action.strip():
            raise ValueError("next_action must not be blank")
        if self.risk_note is not None and not self.risk_note.strip():
            raise ValueError("risk_note must not be blank")
        commitment_ids = [item.commitment_id for item in self.commitments]
        if len(commitment_ids) != len(set(commitment_ids)):
            raise ValueError("duplicate commitment_id")

    def contact_age_days(self, *, as_of: date) -> int:
        return max(0, (as_of - self.last_contact_on).days)


@dataclass(frozen=True, slots=True)
class ClientInsight:
    client_id: str
    name: str
    health: ClientHealth
    revenue_value: Decimal
    contact_age_days: int
    overdue_commitments: tuple[ClientCommitment, ...]
    blocked_commitments: tuple[ClientCommitment, ...]
    next_action: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClientPortfolioSnapshot:
    active_clients: int
    revenue_value: Decimal
    at_risk_clients: tuple[ClientInsight, ...]
    watch_clients: tuple[ClientInsight, ...]
    actions_required: tuple[str, ...]


class ClientIntelligenceEngine:
    def evaluate_client(
        self,
        client: ClientRecord,
        *,
        as_of: date,
        contact_watch_days: int = 14,
        contact_risk_days: int = 30,
    ) -> ClientInsight:
        if contact_watch_days < 1:
            raise ValueError("contact_watch_days must be positive")
        if contact_risk_days <= contact_watch_days:
            raise ValueError("contact_risk_days must be greater than contact_watch_days")

        age = client.contact_age_days(as_of=as_of)
        overdue = tuple(
            sorted(
                (item for item in client.commitments if item.is_overdue(as_of=as_of)),
                key=lambda item: (item.due_on or date.max, item.commitment_id),
            )
        )
        blocked = tuple(
            sorted(
                (item for item in client.commitments if item.status == "blocked"),
                key=lambda item: item.commitment_id,
            )
        )

        reasons: list[str] = []
        health: ClientHealth = "healthy"
        if client.risk_note is not None:
            health = "at_risk"
            reasons.append(client.risk_note)
        if blocked:
            health = "at_risk"
            reasons.append(f"{len(blocked)} blocked commitment(s)")
        if overdue:
            health = "at_risk"
            reasons.append(f"{len(overdue)} overdue commitment(s)")
        if age >= contact_risk_days:
            health = "at_risk"
            reasons.append(f"no contact for {age} days")
        elif age >= contact_watch_days and health == "healthy":
            health = "watch"
            reasons.append(f"no contact for {age} days")

        next_action = client.next_action
        if next_action is None:
            if blocked:
                next_action = f"Resolve blocker for {client.name}"
            elif overdue:
                next_action = f"Close overdue commitment for {client.name}"
            elif health in {"watch", "at_risk"}:
                next_action = f"Re-engage {client.name}"
            else:
                next_action = f"Maintain momentum with {client.name}"

        return ClientInsight(
            client_id=client.client_id,
            name=client.name,
            health=health,
            revenue_value=client.revenue_value,
            contact_age_days=age,
            overdue_commitments=overdue,
            blocked_commitments=blocked,
            next_action=next_action,
            reasons=tuple(reasons),
        )

    def evaluate_portfolio(
        self,
        clients: Iterable[ClientRecord],
        *,
        as_of: date,
        contact_watch_days: int = 14,
        contact_risk_days: int = 30,
    ) -> ClientPortfolioSnapshot:
        items = tuple(clients)
        ids = [item.client_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate client_id")

        insights = tuple(
            self.evaluate_client(
                item,
                as_of=as_of,
                contact_watch_days=contact_watch_days,
                contact_risk_days=contact_risk_days,
            )
            for item in items
        )
        at_risk = tuple(
            sorted(
                (item for item in insights if item.health == "at_risk"),
                key=lambda item: (-item.revenue_value, -item.contact_age_days, item.client_id),
            )
        )
        watch = tuple(
            sorted(
                (item for item in insights if item.health == "watch"),
                key=lambda item: (-item.revenue_value, -item.contact_age_days, item.client_id),
            )
        )
        actions = tuple(item.next_action for item in (*at_risk, *watch))
        return ClientPortfolioSnapshot(
            active_clients=len(items),
            revenue_value=sum((item.revenue_value for item in items), Decimal("0.00")),
            at_risk_clients=at_risk,
            watch_clients=watch,
            actions_required=actions,
        )
