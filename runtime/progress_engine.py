from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from runtime.repository_validator import GrowthObjectValidator, ValidationReport


CANONICAL_SEQUENCE = (
    "growth_specification",
    "growth_blueprint",
    "campaign_world",
    "creative_directors_bible",
    "production_pack",
    "asset_manifest",
    "performance_feedback",
)

_COMPLETE_STATUSES = {"approved", "active", "superseded", "archived"}
_IN_FLIGHT_STATUSES = {"draft", "in_review"}


@dataclass(frozen=True)
class CampaignProgress:
    client_id: str
    client_name: str
    campaign_id: str
    campaign_name: str
    health: str
    completion_percent: int
    current_stage: str
    current_status: str
    next_action: str
    blocker_codes: tuple[str, ...]
    objects_present: tuple[str, ...]
    objects_complete: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgressSnapshot:
    status: str
    campaigns: tuple[CampaignProgress, ...]
    validation: ValidationReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "campaigns": [campaign.to_dict() for campaign in self.campaigns],
            "validation": self.validation.to_dict(),
        }


class RepositoryProgressEngine:
    """Derive Tony progress updates directly from canonical repository objects."""

    def __init__(self, validator: GrowthObjectValidator) -> None:
        self.validator = validator

    def build_snapshot(self, objects: Iterable[dict[str, Any]]) -> ProgressSnapshot:
        records = list(objects)
        validation = self.validator.validate(records)
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}

        for record in records:
            client_id = record.get("client_id")
            campaign_id = record.get("campaign_id")
            if isinstance(client_id, str) and isinstance(campaign_id, str):
                grouped.setdefault((client_id, campaign_id), []).append(record)

        campaigns = tuple(
            self._campaign_progress(group_records, validation)
            for _, group_records in sorted(grouped.items())
        )
        snapshot_status = "blocked" if validation.errors else "healthy"
        if not campaigns and not validation.errors:
            snapshot_status = "empty"
        return ProgressSnapshot(snapshot_status, campaigns, validation)

    def _campaign_progress(
        self,
        records: list[dict[str, Any]],
        validation: ValidationReport,
    ) -> CampaignProgress:
        representative = records[0]
        by_type = {
            record.get("object_type"): record
            for record in records
            if record.get("object_type") in CANONICAL_SEQUENCE
        }
        present = tuple(stage for stage in CANONICAL_SEQUENCE if stage in by_type)
        complete = tuple(
            stage
            for stage in CANONICAL_SEQUENCE
            if stage in by_type and by_type[stage].get("status") in _COMPLETE_STATUSES
        )

        current_stage, current_status, next_action = self._derive_next_step(by_type)
        campaign_ids = {record.get("id") for record in records}
        blocker_codes = tuple(
            sorted(
                {
                    finding.code
                    for finding in validation.errors
                    if finding.object_id in campaign_ids
                }
            )
        )
        health = "blocked" if blocker_codes else "on_track"
        completion_percent = round((len(complete) / len(CANONICAL_SEQUENCE)) * 100)

        return CampaignProgress(
            client_id=str(representative.get("client_id", "")),
            client_name=str(representative.get("client_name", "")),
            campaign_id=str(representative.get("campaign_id", "")),
            campaign_name=str(representative.get("campaign_name", "")),
            health=health,
            completion_percent=completion_percent,
            current_stage=current_stage,
            current_status=current_status,
            next_action=next_action,
            blocker_codes=blocker_codes,
            objects_present=present,
            objects_complete=complete,
        )

    @staticmethod
    def _derive_next_step(by_type: dict[str, dict[str, Any]]) -> tuple[str, str, str]:
        for stage in CANONICAL_SEQUENCE:
            record = by_type.get(stage)
            if record is None:
                return stage, "missing", f"create {stage}"

            status = record.get("status")
            if status == "draft":
                return stage, status, f"complete and submit {stage} for review"
            if status == "in_review":
                return stage, status, f"review and approve {stage}"
            if status not in _COMPLETE_STATUSES:
                return stage, str(status), f"resolve invalid lifecycle status for {stage}"

        final_stage = CANONICAL_SEQUENCE[-1]
        final_status = str(by_type[final_stage].get("status"))
        return final_stage, final_status, "start the next Growth Specification cycle"
