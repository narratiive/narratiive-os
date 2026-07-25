from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo


class ReviewRecordType(str, Enum):
    COMPLETED = "completed"
    APPROVAL = "approval"
    BLOCKED = "blocked"
    RETRIED = "retried"
    RELIABILITY = "reliability"
    HUMAN_INTERVENTION = "human_intervention"
    WIN = "win"
    THEME = "theme"


@dataclass(frozen=True)
class ReviewRecord:
    record_id: str
    occurred_at: str
    record_type: ReviewRecordType
    summary: str
    evidence: tuple[str, ...]
    workspace_id: str
    theme: str | None = None

    def __post_init__(self) -> None:
        for field in ("record_id", "occurred_at", "summary", "workspace_id"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"review record requires {field}")
        if not isinstance(self.record_type, ReviewRecordType):
            raise ValueError("review record requires a valid record_type")
        if not self.evidence or any(not str(item).strip() for item in self.evidence):
            raise ValueError("review record requires non-empty evidence")
        try:
            datetime.fromisoformat(self.occurred_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("review record occurred_at must be ISO-8601") from exc


@dataclass(frozen=True)
class PatternFinding:
    theme: str
    count: int
    confidence: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FridayExecutiveReview:
    workspace_id: str
    period_start: str
    period_end: str
    completed_outputs: tuple[str, ...]
    approvals: tuple[str, ...]
    blocked_and_retried: tuple[str, ...]
    workflow_reliability: tuple[str, ...]
    human_interventions: tuple[str, ...]
    significant_wins: tuple[str, ...]
    patterns: tuple[PatternFinding, ...]
    next_week_recommendation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "completed_outputs": list(self.completed_outputs),
            "approvals": list(self.approvals),
            "blocked_and_retried": list(self.blocked_and_retried),
            "workflow_reliability": list(self.workflow_reliability),
            "human_interventions": list(self.human_interventions),
            "significant_wins": list(self.significant_wins),
            "patterns": [
                {
                    "theme": item.theme,
                    "count": item.count,
                    "confidence": item.confidence,
                    "evidence": list(item.evidence),
                }
                for item in self.patterns
            ],
            "next_week_recommendation": self.next_week_recommendation,
        }

    def render_compact(self, limit: int = 3500) -> str:
        lines = [f"Friday executive review — {self.period_start} to {self.period_end}"]
        self._append(lines, "Completed", self.completed_outputs)
        self._append(lines, "Approvals", self.approvals)
        self._append(lines, "Blocked / retried", self.blocked_and_retried)
        self._append(lines, "Reliability", self.workflow_reliability)
        self._append(lines, "Human interventions", self.human_interventions)
        self._append(lines, "Wins", self.significant_wins)
        if self.patterns:
            lines.append("Patterns:")
            lines.extend(
                f"- {item.theme}: {item.count} records ({item.confidence})"
                for item in self.patterns
            )
        lines.append(f"Next week: {self.next_week_recommendation}")
        output = "\n".join(lines)
        return output if len(output) <= limit else output[: limit - 1].rstrip() + "…"

    @staticmethod
    def _append(lines: list[str], heading: str, values: tuple[str, ...]) -> None:
        if values:
            lines.append(f"{heading}:")
            lines.extend(f"- {value}" for value in values)


class FridayExecutiveReviewService:
    """Aggregate seven days of recorded, workspace-scoped evidence."""

    ITEM_LIMIT = 7
    PATTERN_THRESHOLD = 3

    def build(
        self,
        records: tuple[ReviewRecord, ...],
        *,
        workspace_id: str,
        period_end: datetime,
        timezone: str = "Europe/London",
    ) -> FridayExecutiveReview:
        if not workspace_id.strip():
            raise ValueError("Friday review requires workspace_id")
        zone = ZoneInfo(timezone)
        end = self._aware(period_end, zone)
        start = end - timedelta(days=7)
        selected = self._select(records, workspace_id, start, end, zone)

        grouped = {kind: [] for kind in ReviewRecordType}
        for record in selected:
            grouped[record.record_type].append(self._line(record))

        patterns = self._patterns(selected)
        recommendation = self._recommend(grouped, patterns)
        return FridayExecutiveReview(
            workspace_id=workspace_id,
            period_start=start.isoformat(),
            period_end=end.isoformat(),
            completed_outputs=tuple(grouped[ReviewRecordType.COMPLETED][: self.ITEM_LIMIT]),
            approvals=tuple(grouped[ReviewRecordType.APPROVAL][: self.ITEM_LIMIT]),
            blocked_and_retried=tuple(
                (grouped[ReviewRecordType.BLOCKED] + grouped[ReviewRecordType.RETRIED])[: self.ITEM_LIMIT]
            ),
            workflow_reliability=tuple(grouped[ReviewRecordType.RELIABILITY][: self.ITEM_LIMIT]),
            human_interventions=tuple(grouped[ReviewRecordType.HUMAN_INTERVENTION][: self.ITEM_LIMIT]),
            significant_wins=tuple(grouped[ReviewRecordType.WIN][: self.ITEM_LIMIT]),
            patterns=patterns,
            next_week_recommendation=recommendation,
        )

    @staticmethod
    def _aware(value: datetime, zone: ZoneInfo) -> datetime:
        return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)

    def _select(
        self,
        records: tuple[ReviewRecord, ...],
        workspace_id: str,
        start: datetime,
        end: datetime,
        zone: ZoneInfo,
    ) -> tuple[ReviewRecord, ...]:
        unique: dict[str, tuple[datetime, ReviewRecord]] = {}
        for record in records:
            if record.workspace_id != workspace_id or record.record_id in unique:
                continue
            occurred = datetime.fromisoformat(record.occurred_at.replace("Z", "+00:00"))
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=zone)
            else:
                occurred = occurred.astimezone(zone)
            if start <= occurred < end:
                unique[record.record_id] = (occurred, record)
        return tuple(
            item[1]
            for item in sorted(
                unique.values(), key=lambda item: (item[0], item[1].record_id)
            )
        )

    def _patterns(self, records: tuple[ReviewRecord, ...]) -> tuple[PatternFinding, ...]:
        themes: dict[str, list[ReviewRecord]] = {}
        for record in records:
            if record.theme:
                themes.setdefault(record.theme, []).append(record)
        findings = []
        for theme, matches in sorted(themes.items()):
            confidence = "established" if len(matches) >= self.PATTERN_THRESHOLD else "early_hypothesis"
            findings.append(
                PatternFinding(
                    theme=theme,
                    count=len(matches),
                    confidence=confidence,
                    evidence=tuple(
                        dict.fromkeys(
                            evidence
                            for item in matches
                            for evidence in item.evidence
                        )
                    ),
                )
            )
        return tuple(findings)

    @staticmethod
    def _line(record: ReviewRecord) -> str:
        return f"{record.summary} — {record.evidence[0]}"

    @staticmethod
    def _recommend(grouped: dict[ReviewRecordType, list[str]], patterns: tuple[PatternFinding, ...]) -> str:
        if grouped[ReviewRecordType.BLOCKED]:
            return "Resolve the oldest recorded blocker before starting additional work."
        established = next((item for item in patterns if item.confidence == "established"), None)
        if established:
            return f"Address the repeated '{established.theme}' pattern with one owned corrective action."
        if grouped[ReviewRecordType.APPROVAL]:
            return "Clear the recorded approval queue before adding new commitments."
        return "Continue the highest-priority recorded workstream and preserve evidence for the next review."
