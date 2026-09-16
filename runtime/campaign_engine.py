from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class CampaignEngineError(ValueError):
    """Raised when a campaign transition would violate the delivery contract."""


class CampaignEngineStoreError(RuntimeError):
    """Raised when persisted campaign state cannot be trusted."""


class CampaignEngineStage(str, Enum):
    STRATEGY_APPROVED = "strategy_approved"
    CAMPAIGN_WORLDS_IN_DEVELOPMENT = "campaign_worlds_in_development"
    CAMPAIGN_WORLDS_IN_QUALITY_REVIEW = "campaign_worlds_in_quality_review"
    CAMPAIGN_WORLD_SELECTION_REQUIRED = "campaign_world_selection_required"
    CREATIVE_BIBLE_IN_DEVELOPMENT = "creative_bible_in_development"
    CREATIVE_BIBLE_IN_QUALITY_REVIEW = "creative_bible_in_quality_review"
    CREATIVE_BIBLE_APPROVAL_REQUIRED = "creative_bible_approval_required"
    PRODUCTION_PLANNING = "production_planning"


class QualityVerdict(str, Enum):
    PASS = "pass"
    REVISE = "revise"
    BLOCK = "block"


class TonyDisposition(str, Enum):
    FORWARD = "forward"
    RETURN = "return"


@dataclass(frozen=True, slots=True)
class CampaignIdentity:
    workspace_id: str
    client_id: str
    brand_id: str
    market_ids: tuple[str, ...]
    product_ids: tuple[str, ...]
    campaign_id: str

    def __post_init__(self) -> None:
        required = {
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "brand_id": self.brand_id,
            "campaign_id": self.campaign_id,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise CampaignEngineError(f"campaign identity is missing: {', '.join(missing)}")
        if not self.market_ids or any(not value.strip() for value in self.market_ids):
            raise CampaignEngineError("campaign identity requires at least one market_id")
        if not self.product_ids or any(not value.strip() for value in self.product_ids):
            raise CampaignEngineError("campaign identity requires at least one product_id")
        if len(self.market_ids) != len(set(self.market_ids)):
            raise CampaignEngineError("market_ids must be unique")
        if len(self.product_ids) != len(set(self.product_ids)):
            raise CampaignEngineError("product_ids must be unique")


@dataclass(frozen=True, slots=True)
class VersionedArtifact:
    artifact_id: str
    artifact_type: str
    version: str
    checksum: str
    location: str

    def __post_init__(self) -> None:
        values = (
            self.artifact_id,
            self.artifact_type,
            self.version,
            self.checksum,
            self.location,
        )
        if any(not value.strip() for value in values):
            raise CampaignEngineError("versioned artefact fields must not be empty")


@dataclass(frozen=True, slots=True)
class QualityReview:
    verdict: QualityVerdict
    reviewer: str
    rationale: str
    reviewed_artifact_checksum: str

    def __post_init__(self) -> None:
        if not self.reviewer.strip() or not self.rationale.strip():
            raise CampaignEngineError("quality review requires reviewer and rationale")
        if not self.reviewed_artifact_checksum.strip():
            raise CampaignEngineError("quality review must bind to an artefact checksum")


@dataclass(frozen=True, slots=True)
class TonyTasteReview:
    disposition: TonyDisposition
    rationale: str
    reviewed_artifact_checksum: str

    def __post_init__(self) -> None:
        if not self.rationale.strip() or not self.reviewed_artifact_checksum.strip():
            raise CampaignEngineError("Tony's review requires rationale and artefact checksum")


@dataclass(frozen=True, slots=True)
class HumanApproval:
    approver: str
    rationale: str
    artifact_id: str
    artifact_version: str
    artifact_checksum: str

    def __post_init__(self) -> None:
        values = (
            self.approver,
            self.rationale,
            self.artifact_id,
            self.artifact_version,
            self.artifact_checksum,
        )
        if any(not value.strip() for value in values):
            raise CampaignEngineError("human approval must bind an approver and exact artefact version")


@dataclass(frozen=True, slots=True)
class CampaignWorldCandidate:
    candidate_id: str
    artifact: VersionedArtifact
    quality_review: QualityReview | None = None
    tony_review: TonyTasteReview | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise CampaignEngineError("campaign-world candidate_id must not be empty")
        if self.artifact.artifact_type != "campaign_world":
            raise CampaignEngineError("campaign-world candidates must reference campaign_world artefacts")

    @property
    def ready_for_matt(self) -> bool:
        return bool(
            self.quality_review
            and self.quality_review.verdict is QualityVerdict.PASS
            and self.tony_review
            and self.tony_review.disposition is TonyDisposition.FORWARD
        )


@dataclass(frozen=True, slots=True)
class CampaignEngineState:
    identity: CampaignIdentity
    approved_blueprint: VersionedArtifact
    blueprint_approval: HumanApproval
    stage: CampaignEngineStage = CampaignEngineStage.STRATEGY_APPROVED
    campaign_world_candidates: tuple[CampaignWorldCandidate, ...] = ()
    selected_campaign_world: VersionedArtifact | None = None
    campaign_world_approval: HumanApproval | None = None
    creative_bible: VersionedArtifact | None = None
    creative_bible_quality_review: QualityReview | None = None
    creative_bible_tony_review: TonyTasteReview | None = None
    creative_bible_approval: HumanApproval | None = None
    publication_authorised: bool = False
    media_spend_authorised: bool = False

    def __post_init__(self) -> None:
        if self.approved_blueprint.artifact_type != "growth_blueprint":
            raise CampaignEngineError("campaign engine requires an approved Growth Blueprint")
        _require_approval_matches(self.approved_blueprint, self.blueprint_approval)
        if self.publication_authorised or self.media_spend_authorised:
            raise CampaignEngineError(
                "campaign preparation state cannot authorise publication or media spend"
            )
        candidate_ids = [candidate.candidate_id for candidate in self.campaign_world_candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise CampaignEngineError("campaign state contains duplicate candidate IDs")
        world_stages = {
            CampaignEngineStage.CAMPAIGN_WORLDS_IN_QUALITY_REVIEW,
            CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED,
            CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT,
            CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW,
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_PLANNING,
        }
        if self.stage in world_stages and len(self.campaign_world_candidates) < 2:
            raise CampaignEngineError("campaign state requires multiple Campaign World candidates")
        if (
            self.stage is CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED
            and not any(candidate.ready_for_matt for candidate in self.campaign_world_candidates)
        ):
            raise CampaignEngineError("selection gate requires a quality-passed candidate forwarded by Tony")
        bible_stages = {
            CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT,
            CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW,
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_PLANNING,
        }
        if self.stage in bible_stages:
            if self.selected_campaign_world is None or self.campaign_world_approval is None:
                raise CampaignEngineError("Creative Bible stages require an approved Campaign World")
            _require_approval_matches(self.selected_campaign_world, self.campaign_world_approval)
        if self.stage in {
            CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW,
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_PLANNING,
        } and self.creative_bible is None:
            raise CampaignEngineError("Creative Bible review stages require a Creative Director's Bible")
        if self.stage in {
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_PLANNING,
        }:
            if not (
                self.creative_bible_quality_review
                and self.creative_bible_quality_review.verdict is QualityVerdict.PASS
                and self.creative_bible_tony_review
                and self.creative_bible_tony_review.disposition is TonyDisposition.FORWARD
            ):
                raise CampaignEngineError("Creative Bible approval gate requires quality and Tony clearance")
        if self.stage is CampaignEngineStage.PRODUCTION_PLANNING:
            if self.creative_bible is None or self.creative_bible_approval is None:
                raise CampaignEngineError("production planning requires an approved Creative Director's Bible")
            _require_approval_matches(self.creative_bible, self.creative_bible_approval)

    @property
    def requires_matt(self) -> bool:
        return self.stage in {
            CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED,
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED,
        }

    @property
    def next_action(self) -> str:
        actions = {
            CampaignEngineStage.STRATEGY_APPROVED: "commission multiple Campaign World candidates",
            CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT: "complete Campaign World candidates",
            CampaignEngineStage.CAMPAIGN_WORLDS_IN_QUALITY_REVIEW: "quality-review and Tony-review every candidate",
            CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED: "Matt selects one exact Campaign World version",
            CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT: "prepare the Creative Director's Bible",
            CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW: (
                "quality-review and Tony-review the Creative Director's Bible"
            ),
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED: (
                "Matt approves the exact Creative Director's Bible version"
            ),
            CampaignEngineStage.PRODUCTION_PLANNING: "prepare channel specifications and Production Pack jobs",
        }
        return actions[self.stage]

    def to_dict(self) -> dict[str, Any]:
        return _to_primitive(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CampaignEngineState":
        try:
            identity_value = value["identity"]
            identity = CampaignIdentity(
                workspace_id=identity_value["workspace_id"],
                client_id=identity_value["client_id"],
                brand_id=identity_value["brand_id"],
                market_ids=tuple(identity_value["market_ids"]),
                product_ids=tuple(identity_value["product_ids"]),
                campaign_id=identity_value["campaign_id"],
            )
            blueprint = VersionedArtifact(**value["approved_blueprint"])
            candidates = tuple(
                CampaignWorldCandidate(
                    candidate_id=item["candidate_id"],
                    artifact=VersionedArtifact(**item["artifact"]),
                    quality_review=_quality_from_dict(item.get("quality_review")),
                    tony_review=_tony_from_dict(item.get("tony_review")),
                )
                for item in value.get("campaign_world_candidates", [])
            )
            return cls(
                identity=identity,
                approved_blueprint=blueprint,
                blueprint_approval=HumanApproval(**value["blueprint_approval"]),
                stage=CampaignEngineStage(value.get("stage", CampaignEngineStage.STRATEGY_APPROVED.value)),
                campaign_world_candidates=candidates,
                selected_campaign_world=_artifact_from_dict(value.get("selected_campaign_world")),
                campaign_world_approval=_approval_from_dict(value.get("campaign_world_approval")),
                creative_bible=_artifact_from_dict(value.get("creative_bible")),
                creative_bible_quality_review=_quality_from_dict(value.get("creative_bible_quality_review")),
                creative_bible_tony_review=_tony_from_dict(value.get("creative_bible_tony_review")),
                creative_bible_approval=_approval_from_dict(value.get("creative_bible_approval")),
                publication_authorised=bool(value.get("publication_authorised", False)),
                media_spend_authorised=bool(value.get("media_spend_authorised", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CampaignEngineStoreError(f"invalid campaign-engine state: {exc}") from exc


@dataclass(frozen=True, slots=True)
class CampaignPortfolioItem:
    client_id: str
    brand_id: str
    campaign_id: str
    stage: str
    next_action: str
    requires_matt: bool


@dataclass(frozen=True, slots=True)
class CampaignPortfolioSnapshot:
    campaigns: tuple[CampaignPortfolioItem, ...]

    @property
    def human_gate_count(self) -> int:
        return sum(1 for campaign in self.campaigns if campaign.requires_matt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_count": len(self.campaigns),
            "human_gate_count": self.human_gate_count,
            "campaigns": [asdict(campaign) for campaign in self.campaigns],
        }


class CampaignPortfolio:
    """Project multi-client campaign state into Tony's operational view."""

    @staticmethod
    def build(states: Iterable[CampaignEngineState]) -> CampaignPortfolioSnapshot:
        items = tuple(
            CampaignPortfolioItem(
                client_id=state.identity.client_id,
                brand_id=state.identity.brand_id,
                campaign_id=state.identity.campaign_id,
                stage=state.stage.value,
                next_action=state.next_action,
                requires_matt=state.requires_matt,
            )
            for state in sorted(
                states,
                key=lambda item: (
                    not item.requires_matt,
                    item.identity.client_id,
                    item.identity.campaign_id,
                ),
            )
        )
        return CampaignPortfolioSnapshot(items)


class FileCampaignEngineRepository:
    """Append-only, hash-chained campaign state scoped to one workspace."""

    def __init__(self, root: str | Path, *, workspace_id: str) -> None:
        if not _safe_identifier(workspace_id):
            raise CampaignEngineStoreError("workspace_id must be a safe identifier")
        self.root = Path(root) / workspace_id
        self.workspace_id = workspace_id

    def save(self, state: CampaignEngineState, *, transition_id: str) -> CampaignEngineState:
        if state.identity.workspace_id != self.workspace_id:
            raise CampaignEngineStoreError("campaign belongs to a different workspace")
        if not _safe_identifier(transition_id):
            raise CampaignEngineStoreError("transition_id must be a safe identifier")
        path = self._path(state.identity.client_id, state.identity.campaign_id)
        with self._file_lock(path, exclusive=True):
            records = self._read_records(path)
            payload = state.to_dict()
            state_hash = _canonical_hash(payload)
            existing = next((record for record in records if record["transition_id"] == transition_id), None)
            if existing:
                if existing["state_hash"] != state_hash:
                    raise CampaignEngineStoreError("transition_id replay conflicts with persisted state")
                return CampaignEngineState.from_dict(existing["state"])
            previous_hash = records[-1]["record_hash"] if records else ""
            record = {
                "sequence": len(records) + 1,
                "transition_id": transition_id,
                "workspace_id": self.workspace_id,
                "client_id": state.identity.client_id,
                "campaign_id": state.identity.campaign_id,
                "state_hash": state_hash,
                "previous_hash": previous_hash,
                "state": payload,
            }
            record["record_hash"] = _canonical_hash(record)
            self._append(path, record)
        return state

    def load(self, client_id: str, campaign_id: str) -> CampaignEngineState:
        path = self._path(client_id, campaign_id)
        with self._file_lock(path, exclusive=False):
            records = self._read_records(path)
        if not records:
            raise CampaignEngineStoreError(f"campaign state not found: {client_id}/{campaign_id}")
        state = CampaignEngineState.from_dict(records[-1]["state"])
        if state.identity.client_id != client_id or state.identity.campaign_id != campaign_id:
            raise CampaignEngineStoreError("campaign state identity does not match its repository path")
        return state

    def exists(self, client_id: str, campaign_id: str) -> bool:
        path = self._path(client_id, campaign_id)
        with self._file_lock(path, exclusive=False):
            return bool(self._read_records(path))

    def list_states(self) -> tuple[CampaignEngineState, ...]:
        states = []
        if not self.root.exists():
            return ()
        for path in sorted(self.root.glob("*/*.jsonl")):
            with self._file_lock(path, exclusive=False):
                records = self._read_records(path)
            if records:
                states.append(CampaignEngineState.from_dict(records[-1]["state"]))
        return tuple(states)

    def _path(self, client_id: str, campaign_id: str) -> Path:
        if not _safe_identifier(client_id) or not _safe_identifier(campaign_id):
            raise CampaignEngineStoreError("client_id and campaign_id must be safe identifiers")
        return self.root / client_id / f"{campaign_id}.jsonl"

    @staticmethod
    def _append(path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise CampaignEngineStoreError(f"could not append campaign state: {exc}") from exc

    def _read_records(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    raw = json.loads(line)
                    if not isinstance(raw, dict):
                        raise CampaignEngineStoreError(
                            f"campaign record at {path}:{line_number} must be an object"
                        )
                    expected_sequence = len(records) + 1
                    if raw.get("sequence") != expected_sequence:
                        raise CampaignEngineStoreError("campaign state sequence gap")
                    if raw.get("workspace_id") != self.workspace_id:
                        raise CampaignEngineStoreError("campaign record belongs to a different workspace")
                    expected_previous = records[-1]["record_hash"] if records else ""
                    if raw.get("previous_hash") != expected_previous:
                        raise CampaignEngineStoreError("campaign state hash chain is broken")
                    unsigned = {key: value for key, value in raw.items() if key != "record_hash"}
                    if raw.get("record_hash") != _canonical_hash(unsigned):
                        raise CampaignEngineStoreError("campaign state record hash mismatch")
                    if raw.get("state_hash") != _canonical_hash(raw.get("state")):
                        raise CampaignEngineStoreError("campaign state payload hash mismatch")
                    records.append(raw)
        except json.JSONDecodeError as exc:
            raise CampaignEngineStoreError(f"invalid campaign state JSON in {path}") from exc
        except OSError as exc:
            raise CampaignEngineStoreError(f"could not read campaign state: {exc}") from exc
        return records

    @contextmanager
    def _file_lock(self, path: Path, *, exclusive: bool):
        lock_path = path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                yield
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise CampaignEngineStoreError(f"campaign state lock failed closed: {exc}") from exc


class CampaignEngineApplicationService:
    """Create one campaign from an exact approved Growth Blueprint."""

    def __init__(self, repository: FileCampaignEngineRepository) -> None:
        self.repository = repository

    def start_campaign(
        self,
        *,
        identity: CampaignIdentity,
        approved_blueprint: VersionedArtifact,
        blueprint_approval: HumanApproval,
        transition_id: str,
    ) -> tuple[CampaignEngineState, bool]:
        proposed = CampaignEngineState(
            identity=identity,
            approved_blueprint=approved_blueprint,
            blueprint_approval=blueprint_approval,
        )
        if self.repository.exists(identity.client_id, identity.campaign_id):
            current = self.repository.load(identity.client_id, identity.campaign_id)
            if current == proposed:
                return current, True
            raise CampaignEngineStoreError(
                "campaign already exists with different identity or Blueprint evidence"
            )
        self.repository.save(proposed, transition_id=transition_id)
        return proposed, False


class CampaignEngine:
    """Pure transition engine for the approved-strategy-to-production boundary.

    Campaign World remains the canonical Narratiive object name. Multiple
    candidates provide the user-facing creative-world choice requested before
    one immutable Campaign World is selected.
    """

    def commission_campaign_worlds(self, state: CampaignEngineState) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.STRATEGY_APPROVED)
        return replace(state, stage=CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT)

    def submit_campaign_worlds(
        self,
        state: CampaignEngineState,
        candidates: tuple[CampaignWorldCandidate, ...],
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT)
        if len(candidates) < 2:
            raise CampaignEngineError("at least two Campaign World candidates are required")
        candidate_ids = [candidate.candidate_id for candidate in candidates]
        artifact_ids = [candidate.artifact.artifact_id for candidate in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise CampaignEngineError("Campaign World candidate IDs must be unique")
        if len(artifact_ids) != len(set(artifact_ids)):
            raise CampaignEngineError("Campaign World artefact IDs must be unique")
        return replace(
            state,
            stage=CampaignEngineStage.CAMPAIGN_WORLDS_IN_QUALITY_REVIEW,
            campaign_world_candidates=candidates,
        )

    def review_campaign_world(
        self,
        state: CampaignEngineState,
        candidate_id: str,
        *,
        quality_review: QualityReview,
        tony_review: TonyTasteReview,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.CAMPAIGN_WORLDS_IN_QUALITY_REVIEW)
        candidates = list(state.campaign_world_candidates)
        index = self._candidate_index(candidates, candidate_id)
        artifact = candidates[index].artifact
        self._require_review_binding(artifact, quality_review.reviewed_artifact_checksum)
        self._require_review_binding(artifact, tony_review.reviewed_artifact_checksum)
        if tony_review.disposition is TonyDisposition.FORWARD and quality_review.verdict is not QualityVerdict.PASS:
            raise CampaignEngineError("Tony cannot forward a candidate that failed independent quality review")
        candidates[index] = replace(
            candidates[index],
            quality_review=quality_review,
            tony_review=tony_review,
        )
        stage = CampaignEngineStage.CAMPAIGN_WORLDS_IN_QUALITY_REVIEW
        if all(candidate.quality_review and candidate.tony_review for candidate in candidates):
            stage = (
                CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED
                if any(candidate.ready_for_matt for candidate in candidates)
                else CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT
            )
        return replace(state, campaign_world_candidates=tuple(candidates), stage=stage)

    def select_campaign_world(
        self,
        state: CampaignEngineState,
        candidate_id: str,
        approval: HumanApproval,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED)
        candidate = state.campaign_world_candidates[
            self._candidate_index(list(state.campaign_world_candidates), candidate_id)
        ]
        if not candidate.ready_for_matt:
            raise CampaignEngineError("Matt may select only a quality-passed candidate forwarded by Tony")
        self._require_approval_binding(candidate.artifact, approval)
        return replace(
            state,
            stage=CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT,
            selected_campaign_world=candidate.artifact,
            campaign_world_approval=approval,
        )

    def submit_creative_bible(
        self,
        state: CampaignEngineState,
        creative_bible: VersionedArtifact,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT)
        if creative_bible.artifact_type != "creative_directors_bible":
            raise CampaignEngineError("expected a Creative Director's Bible artefact")
        return replace(
            state,
            stage=CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW,
            creative_bible=creative_bible,
        )

    def review_creative_bible(
        self,
        state: CampaignEngineState,
        *,
        quality_review: QualityReview,
        tony_review: TonyTasteReview,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW)
        if state.creative_bible is None:
            raise CampaignEngineError("Creative Director's Bible artefact is missing")
        self._require_review_binding(state.creative_bible, quality_review.reviewed_artifact_checksum)
        self._require_review_binding(state.creative_bible, tony_review.reviewed_artifact_checksum)
        if quality_review.verdict is QualityVerdict.PASS and tony_review.disposition is TonyDisposition.FORWARD:
            stage = CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED
        else:
            stage = CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT
        return replace(
            state,
            stage=stage,
            creative_bible_quality_review=quality_review,
            creative_bible_tony_review=tony_review,
        )

    def approve_creative_bible(
        self,
        state: CampaignEngineState,
        approval: HumanApproval,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED)
        if state.creative_bible is None:
            raise CampaignEngineError("Creative Director's Bible artefact is missing")
        self._require_approval_binding(state.creative_bible, approval)
        return replace(
            state,
            stage=CampaignEngineStage.PRODUCTION_PLANNING,
            creative_bible_approval=approval,
        )

    @staticmethod
    def _require_stage(state: CampaignEngineState, expected: CampaignEngineStage) -> None:
        if state.stage is not expected:
            raise CampaignEngineError(
                f"invalid campaign transition from {state.stage.value}; expected {expected.value}"
            )

    @staticmethod
    def _candidate_index(candidates: list[CampaignWorldCandidate], candidate_id: str) -> int:
        for index, candidate in enumerate(candidates):
            if candidate.candidate_id == candidate_id:
                return index
        raise CampaignEngineError(f"unknown Campaign World candidate: {candidate_id}")

    @staticmethod
    def _require_review_binding(artifact: VersionedArtifact, checksum: str) -> None:
        if artifact.checksum != checksum:
            raise CampaignEngineError("review does not match the current artefact checksum")

    @staticmethod
    def _require_approval_binding(artifact: VersionedArtifact, approval: HumanApproval) -> None:
        _require_approval_matches(artifact, approval)


def _to_primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [_to_primitive(item) for item in value]
    if isinstance(value, list):
        return [_to_primitive(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_primitive(item) for key, item in value.items()}
    return value


def _artifact_from_dict(value: Any) -> VersionedArtifact | None:
    return VersionedArtifact(**value) if isinstance(value, dict) else None


def _quality_from_dict(value: Any) -> QualityReview | None:
    if not isinstance(value, dict):
        return None
    return QualityReview(
        verdict=QualityVerdict(value["verdict"]),
        reviewer=value["reviewer"],
        rationale=value["rationale"],
        reviewed_artifact_checksum=value["reviewed_artifact_checksum"],
    )


def _tony_from_dict(value: Any) -> TonyTasteReview | None:
    if not isinstance(value, dict):
        return None
    return TonyTasteReview(
        disposition=TonyDisposition(value["disposition"]),
        rationale=value["rationale"],
        reviewed_artifact_checksum=value["reviewed_artifact_checksum"],
    )


def _approval_from_dict(value: Any) -> HumanApproval | None:
    return HumanApproval(**value) if isinstance(value, dict) else None


def _safe_identifier(value: str) -> bool:
    return bool(
        value
        and value not in {".", ".."}
        and Path(value).name == value
        and "/" not in value
        and "\\" not in value
    )


def _require_approval_matches(artifact: VersionedArtifact, approval: HumanApproval) -> None:
    if (
        approval.artifact_id != artifact.artifact_id
        or approval.artifact_version != artifact.version
        or approval.artifact_checksum != artifact.checksum
    ):
        raise CampaignEngineError("approval does not match the exact artefact version")


def _canonical_hash(value: Any) -> str:
    canonical = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
