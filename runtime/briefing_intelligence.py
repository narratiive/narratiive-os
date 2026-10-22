from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from runtime.agency_state import AgencyItem, AgencyState


class BriefingDecisionType(StrEnum):
    SUPPRESS = "suppress"
    SPAM = "spam"
    INTERNAL = "internal"
    TEST = "test"
    DUPLICATE = "duplicate"
    DEFER = "defer"
    ARCHIVE = "archive"
    RECLASSIFY = "reclassify"
    RESTORE = "restore"


HIDDEN_DECISIONS = frozenset(
    {
        BriefingDecisionType.SUPPRESS,
        BriefingDecisionType.SPAM,
        BriefingDecisionType.INTERNAL,
        BriefingDecisionType.TEST,
        BriefingDecisionType.DUPLICATE,
        BriefingDecisionType.DEFER,
        BriefingDecisionType.ARCHIVE,
    }
)


@dataclass(frozen=True, slots=True)
class BriefingDecision:
    decision_id: str
    entity_id: str
    aliases: tuple[str, ...]
    decision_type: BriefingDecisionType
    classification: str
    reporting_status: str
    reason: str
    timestamp: str
    source: str
    reconsideration_conditions: str

    @classmethod
    def create(
        cls,
        *,
        entity_id: str,
        aliases: Iterable[str] = (),
        decision_type: BriefingDecisionType,
        classification: str = "",
        reason: str = "",
        source: str = "openclaw",
        reconsideration_conditions: str = "Material new evidence or explicit founder restoration.",
        timestamp: str | None = None,
    ) -> "BriefingDecision":
        canonical = entity_id.strip()
        if not canonical:
            raise ValueError("decision entity_id is required")
        reporting_status = (
            "active" if decision_type in {BriefingDecisionType.RESTORE, BriefingDecisionType.RECLASSIFY}
            else "deferred" if decision_type is BriefingDecisionType.DEFER
            else "suppressed"
        )
        return cls(
            decision_id=str(uuid4()),
            entity_id=canonical,
            aliases=tuple(dict.fromkeys(value.strip() for value in aliases if value.strip())),
            decision_type=decision_type,
            classification=classification.strip(),
            reporting_status=reporting_status,
            reason=reason.strip(),
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            source=source.strip() or "runtime",
            reconsideration_conditions=reconsideration_conditions.strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["decision_type"] = self.decision_type.value
        value["aliases"] = list(self.aliases)
        return value


class FileBriefingDecisionRegister:
    """Append-only founder decisions used only for briefing eligibility."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def append(self, decision: BriefingDecision) -> BriefingDecision:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision.to_dict(), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return decision

    def read(self) -> tuple[BriefingDecision, ...]:
        if not self.path.exists():
            return ()
        records: list[BriefingDecision] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            value["decision_type"] = BriefingDecisionType(value["decision_type"])
            value["aliases"] = tuple(value.get("aliases", ()))
            records.append(BriefingDecision(**value))
        return tuple(records)

    def latest(self) -> dict[str, BriefingDecision]:
        latest: dict[str, BriefingDecision] = {}
        for record in self.read():
            for identity in (record.entity_id, *record.aliases):
                key = self._key(identity)
                if key:
                    latest[key] = record
        return latest

    @staticmethod
    def _key(value: str) -> str:
        return " ".join(str(value).casefold().split())


class FileBriefingBaselineStore:
    """Current snapshot of the last successfully delivered executive brief."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("briefing baseline must be an object")
        return value

    def store(self, snapshot: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
        descriptor, temporary = tempfile.mkstemp(prefix=".briefing-baseline.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class ExecutiveBriefingPipeline:
    """Decision-aware, change-sensitive executive attention pipeline."""

    PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
    GENERIC_RECOMMENDATIONS = {
        "review and decide this item",
        "review the lead and decide the next commercial action",
        "continue the current authorised internal workflow step",
    }

    def __init__(
        self,
        *,
        decision_register: FileBriefingDecisionRegister | None = None,
        baseline_store: FileBriefingBaselineStore | None = None,
    ) -> None:
        self.decision_register = decision_register
        self.baseline_store = baseline_store

    def refine(self, state: AgencyState) -> AgencyState:
        decisions = self.decision_register.latest() if self.decision_register else {}
        prior = self.baseline_store.read().get("items", {}) if self.baseline_store else {}
        selected: dict[str, AgencyItem] = {}
        for item in state.items:
            identity = self._identity(item)
            decision = self._decision_for(item, decisions)
            if decision and decision.decision_type in HIDDEN_DECISIONS and item.significance != "P0":
                continue
            candidate = item
            if decision and decision.decision_type is BriefingDecisionType.RECLASSIFY and decision.classification:
                significance = (
                    "P2" if decision.classification == "verified_commercial_opportunity"
                    else "P4" if decision.classification in {"spam", "internal", "test", "duplicate", "historical", "routine"}
                    else item.significance
                )
                candidate = replace(
                    item,
                    classification=decision.classification,
                    significance=significance,
                )
                if significance == "P4":
                    continue
            if candidate.significance == "P4":
                continue
            signature = self._signature(candidate)
            unchanged = prior.get(identity, {}).get("signature") == signature
            if (
                unchanged
                and candidate.significance != "P0"
                and not candidate.requires_matt
                and not (decision and decision.decision_type in {BriefingDecisionType.RESTORE, BriefingDecisionType.RECLASSIFY})
            ):
                continue
            current = selected.get(identity)
            if current is None or self._rank(candidate) < self._rank(current):
                selected[identity] = candidate
        ordered = sorted(selected.values(), key=lambda item: (self._rank(item), item.title.casefold()))
        return AgencyState.from_items(state.generated_at, ordered)

    def validate(self, state: AgencyState) -> None:
        for item in state.executive_items:
            recommendation = " ".join(item.next_action.casefold().split()).rstrip(".!?")
            if item.requires_matt and recommendation in self.GENERIC_RECOMMENDATIONS:
                raise ValueError(f"generic founder recommendation is not allowed: {item.item_id}")
            if item.requires_matt and (not item.evidence or not item.why_matters.strip()):
                raise ValueError(f"founder decision lacks evidence or business significance: {item.item_id}")

    def snapshot(self, state: AgencyState, *, period: str) -> dict[str, Any]:
        return {
            "period": period,
            "delivered_at": datetime.now(timezone.utc).isoformat(),
            "items": {
                self._identity(item): {
                    "signature": self._signature(item),
                    "significance": item.significance,
                    "status": item.status,
                }
                for item in state.items
            },
        }

    def record_delivered(self, snapshot: dict[str, Any]) -> None:
        if self.baseline_store:
            self.baseline_store.store(snapshot)

    @classmethod
    def _rank(cls, item: AgencyItem) -> tuple[int, int, int]:
        return (
            cls.PRIORITY.get(item.significance, 4),
            0 if item.requires_matt else 1,
            0 if item.blocked else 1,
        )

    @staticmethod
    def _identity(item: AgencyItem) -> str:
        value = item.entity_id or item.item_id
        return " ".join(value.casefold().split())

    @classmethod
    def _decision_for(
        cls, item: AgencyItem, decisions: dict[str, BriefingDecision]
    ) -> BriefingDecision | None:
        for value in (item.entity_id, item.item_id, *item.aliases):
            key = " ".join(str(value).casefold().split())
            if key in decisions:
                return decisions[key]
        return None

    @staticmethod
    def _signature(item: AgencyItem) -> str:
        payload = {
            "status": item.status,
            "title": item.title,
            "next_action": item.next_action,
            "blocked": item.blocked,
            "requires_matt": item.requires_matt,
            "evidence": item.evidence,
            "significance": item.significance,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
