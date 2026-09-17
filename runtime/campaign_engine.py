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
    PRODUCTION_PLAN_APPROVAL_REQUIRED = "production_plan_approval_required"
    PRODUCTION_READY = "production_ready"
    ASSET_PRODUCTION = "asset_production"
    ASSET_REVIEW = "asset_review"
    ASSET_SUITE_APPROVED = "asset_suite_approved"


class QualityVerdict(str, Enum):
    PASS = "pass"
    REVISE = "revise"
    BLOCK = "block"


class TonyDisposition(str, Enum):
    FORWARD = "forward"
    RETURN = "return"


class ProductionMethod(str, Enum):
    HUMAN_PRODUCTION = "human_production"
    AI_GENERATION = "ai_generation"
    AI_ASSISTED_PRODUCTION = "ai_assisted_production"
    TEMPLATE_RENDER = "template_render"
    ADAPTATION = "adaptation"
    LOCALISATION = "localisation"
    COMPOSITE = "composite"


class ProductionRouteStatus(str, Enum):
    PLANNED = "planned"


class AssetLifecycleStatus(str, Enum):
    PLANNED = "planned"
    QUEUED = "queued"
    IN_PRODUCTION = "in_production"
    GENERATED = "generated"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    DELIVERED = "delivered"
    SUPERSEDED = "superseded"
    BLOCKED = "blocked"


class AssetReviewDecision(str, Enum):
    APPROVE = "approve"
    CHANGES_REQUESTED = "changes_requested"


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
class ChannelAssetSpecification:
    specification_id: str
    channel: str
    placement: str
    market: str
    language: str
    asset_type: str
    file_format: str
    aspect_ratio: str
    source_bible_id: str
    source_bible_version: str
    source_bible_checksum: str
    platform_requirements_version: str
    width_px: int | None = None
    height_px: int | None = None
    duration_seconds: float | None = None
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = (
            self.specification_id,
            self.channel,
            self.placement,
            self.market,
            self.language,
            self.asset_type,
            self.file_format,
            self.aspect_ratio,
            self.source_bible_id,
            self.source_bible_version,
            self.source_bible_checksum,
            self.platform_requirements_version,
        )
        if any(not value.strip() for value in required):
            raise CampaignEngineError("channel asset specification fields must not be empty")
        if self.width_px is not None and self.width_px <= 0:
            raise CampaignEngineError("channel asset width must be positive")
        if self.height_px is not None and self.height_px <= 0:
            raise CampaignEngineError("channel asset height must be positive")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise CampaignEngineError("channel asset duration must be positive")


@dataclass(frozen=True, slots=True)
class ProductionJob:
    job_id: str
    specification_id: str
    production_method: ProductionMethod
    required_capability: str
    source_bible_checksum: str
    expected_variants: int = 1
    human_review_required: bool = True

    def __post_init__(self) -> None:
        required = (
            self.job_id,
            self.specification_id,
            self.required_capability,
            self.source_bible_checksum,
        )
        if any(not value.strip() for value in required):
            raise CampaignEngineError("production job fields must not be empty")
        if self.expected_variants < 1:
            raise CampaignEngineError("production job requires at least one expected variant")
        if not self.human_review_required:
            raise CampaignEngineError("production jobs must require human review")


@dataclass(frozen=True, slots=True)
class ProductionPlan:
    production_pack: VersionedArtifact
    source_bible_id: str
    source_bible_version: str
    source_bible_checksum: str
    channel_specifications: tuple[ChannelAssetSpecification, ...]
    jobs: tuple[ProductionJob, ...]
    publication_authorised: bool = False
    media_spend_authorised: bool = False

    def __post_init__(self) -> None:
        if self.production_pack.artifact_type != "production_pack":
            raise CampaignEngineError("production plan requires a Production Pack artefact")
        if not self.channel_specifications or not self.jobs:
            raise CampaignEngineError("production plan requires channel specifications and jobs")
        if self.publication_authorised or self.media_spend_authorised:
            raise CampaignEngineError("production plan cannot authorise publication or media spend")
        source = (self.source_bible_id, self.source_bible_version, self.source_bible_checksum)
        if any(not value.strip() for value in source):
            raise CampaignEngineError("production plan requires exact Creative Director's Bible lineage")
        specification_ids = [item.specification_id for item in self.channel_specifications]
        job_ids = [item.job_id for item in self.jobs]
        if len(specification_ids) != len(set(specification_ids)):
            raise CampaignEngineError("channel specification IDs must be unique")
        if len(job_ids) != len(set(job_ids)):
            raise CampaignEngineError("production job IDs must be unique")
        known_specifications = set(specification_ids)
        for specification in self.channel_specifications:
            specification_source = (
                specification.source_bible_id,
                specification.source_bible_version,
                specification.source_bible_checksum,
            )
            if specification_source != source:
                raise CampaignEngineError("channel specification lineage must match the approved Bible")
        for job in self.jobs:
            if job.specification_id not in known_specifications:
                raise CampaignEngineError("production job references an unknown channel specification")
            if job.source_bible_checksum != self.source_bible_checksum:
                raise CampaignEngineError("production job lineage must match the approved Bible")


@dataclass(frozen=True, slots=True)
class ProductionJobRoute:
    route_id: str
    job_id: str
    required_capability: str
    worker_id: str
    provider: str
    policy_id: str
    selection_reason: str
    source_production_pack_checksum: str
    side_effect_classification: str = "preparation"
    status: ProductionRouteStatus = ProductionRouteStatus.PLANNED
    external_action_taken: bool = False

    def __post_init__(self) -> None:
        required = (
            self.route_id,
            self.job_id,
            self.required_capability,
            self.worker_id,
            self.provider,
            self.policy_id,
            self.selection_reason,
            self.source_production_pack_checksum,
        )
        if any(not value.strip() for value in required):
            raise CampaignEngineError("production job route fields must not be empty")
        if self.provider.strip().casefold() == "unconfigured":
            raise CampaignEngineError("production route requires an available configured provider")
        if self.side_effect_classification != "preparation":
            raise CampaignEngineError("production routing may authorise preparation only")
        if self.status is not ProductionRouteStatus.PLANNED:
            raise CampaignEngineError("new production routes must begin as planned")
        if self.external_action_taken:
            raise CampaignEngineError("production routing cannot claim an external action")


@dataclass(frozen=True, slots=True)
class PlannedAssetRecord:
    asset_id: str
    asset_key: str
    production_job_id: str
    specification_id: str
    channel: str
    placement: str
    market: str
    language: str
    asset_type: str
    source_production_pack_id: str
    source_production_pack_version: str
    source_production_pack_checksum: str
    source_bible_checksum: str
    version_number: int = 1
    status: AssetLifecycleStatus = AssetLifecycleStatus.PLANNED
    file_checksum: str | None = None
    working_uri: str | None = None
    review_uri: str | None = None
    approved_uri: str | None = None
    delivered_uri: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.asset_id,
            self.asset_key,
            self.production_job_id,
            self.specification_id,
            self.channel,
            self.placement,
            self.market,
            self.language,
            self.asset_type,
            self.source_production_pack_id,
            self.source_production_pack_version,
            self.source_production_pack_checksum,
            self.source_bible_checksum,
        )
        if any(not value.strip() for value in required):
            raise CampaignEngineError("planned asset fields must not be empty")
        if self.version_number != 1:
            raise CampaignEngineError("planned assets must begin at version 1")
        if self.status is not AssetLifecycleStatus.PLANNED:
            raise CampaignEngineError("new Asset Manifest records must begin as planned")
        if any(
            value
            for value in (
                self.file_checksum,
                self.working_uri,
                self.review_uri,
                self.approved_uri,
                self.delivered_uri,
            )
        ):
            raise CampaignEngineError("planned assets cannot claim generated, approved or delivered files")


@dataclass(frozen=True, slots=True)
class PlannedAssetManifest:
    manifest_artifact: VersionedArtifact
    source_production_pack_id: str
    source_production_pack_version: str
    source_production_pack_checksum: str
    assets: tuple[PlannedAssetRecord, ...]
    publication_authorised: bool = False
    delivery_authorised: bool = False
    media_spend_authorised: bool = False

    def __post_init__(self) -> None:
        if self.manifest_artifact.artifact_type != "asset_manifest":
            raise CampaignEngineError("planned assets require an Asset Manifest artefact")
        if not self.assets:
            raise CampaignEngineError("Asset Manifest requires at least one planned asset")
        if self.publication_authorised or self.delivery_authorised or self.media_spend_authorised:
            raise CampaignEngineError("planned Asset Manifest cannot authorise delivery, publication or media spend")
        source = (
            self.source_production_pack_id,
            self.source_production_pack_version,
            self.source_production_pack_checksum,
        )
        if any(not value.strip() for value in source):
            raise CampaignEngineError("Asset Manifest requires exact Production Pack lineage")
        asset_ids = [asset.asset_id for asset in self.assets]
        asset_keys = [asset.asset_key for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise CampaignEngineError("Asset Manifest asset IDs must be unique")
        if len(asset_keys) != len(set(asset_keys)):
            raise CampaignEngineError("Asset Manifest asset keys must be unique")
        for asset in self.assets:
            asset_source = (
                asset.source_production_pack_id,
                asset.source_production_pack_version,
                asset.source_production_pack_checksum,
            )
            if asset_source != source:
                raise CampaignEngineError("planned asset lineage must match the Production Pack")


@dataclass(frozen=True, slots=True)
class ProducedAssetVersion:
    asset_version_id: str
    asset_id: str
    version_number: int
    file_checksum: str
    drive_uri: str
    producer: str
    production_job_id: str
    source_manifest_checksum: str
    status: AssetLifecycleStatus = AssetLifecycleStatus.GENERATED
    human_review_required: bool = True
    publication_authorised: bool = False
    delivery_authorised: bool = False

    def __post_init__(self) -> None:
        required = (
            self.asset_version_id,
            self.asset_id,
            self.file_checksum,
            self.drive_uri,
            self.producer,
            self.production_job_id,
            self.source_manifest_checksum,
        )
        if any(not value.strip() for value in required):
            raise CampaignEngineError("produced asset version fields must not be empty")
        if self.version_number < 1:
            raise CampaignEngineError("produced asset version number must be positive")
        if not (
            self.drive_uri.startswith("drive://")
            or self.drive_uri.startswith("https://drive.google.com/")
        ):
            raise CampaignEngineError("produced asset version must use the Drive repository")
        if self.status is not AssetLifecycleStatus.GENERATED:
            raise CampaignEngineError("new asset versions must begin as generated")
        if not self.human_review_required:
            raise CampaignEngineError("generated asset versions require human review")
        if self.publication_authorised or self.delivery_authorised:
            raise CampaignEngineError("generated asset versions cannot authorise publication or delivery")


@dataclass(frozen=True, slots=True)
class AssetFileProbe:
    asset_version_id: str
    file_checksum: str
    probe_receipt_id: str
    file_exists: bool
    file_readable: bool
    file_format: str
    width_px: int | None = None
    height_px: int | None = None
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        required = (
            self.asset_version_id,
            self.file_checksum,
            self.probe_receipt_id,
            self.file_format,
        )
        if any(not value.strip() for value in required):
            raise CampaignEngineError("asset file probe fields must not be empty")
        if self.width_px is not None and self.width_px <= 0:
            raise CampaignEngineError("probed asset width must be positive")
        if self.height_px is not None and self.height_px <= 0:
            raise CampaignEngineError("probed asset height must be positive")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise CampaignEngineError("probed asset duration must be positive")


@dataclass(frozen=True, slots=True)
class AssetTechnicalCheck:
    name: str
    passed: bool
    expected: str
    observed: str
    critical: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.expected.strip() or not self.observed.strip():
            raise CampaignEngineError("asset technical check fields must not be empty")


@dataclass(frozen=True, slots=True)
class AssetTechnicalValidation:
    validation_id: str
    asset_version_id: str
    file_checksum: str
    specification_id: str
    probe_receipt_id: str
    checks: tuple[AssetTechnicalCheck, ...]

    def __post_init__(self) -> None:
        required = (
            self.validation_id,
            self.asset_version_id,
            self.file_checksum,
            self.specification_id,
            self.probe_receipt_id,
        )
        if any(not value.strip() for value in required):
            raise CampaignEngineError("asset technical validation fields must not be empty")
        if not self.checks:
            raise CampaignEngineError("asset technical validation requires checks")
        names = [check.name for check in self.checks]
        if len(names) != len(set(names)):
            raise CampaignEngineError("asset technical validation check names must be unique")

    @property
    def passed(self) -> bool:
        return not any(check.critical and not check.passed for check in self.checks)


@dataclass(frozen=True, slots=True)
class AssetVersionReview:
    asset_version_id: str
    file_checksum: str
    reviewer: str
    decision: AssetReviewDecision
    rationale: str

    def __post_init__(self) -> None:
        required = (
            self.asset_version_id,
            self.file_checksum,
            self.reviewer,
            self.rationale,
        )
        if any(not value.strip() for value in required):
            raise CampaignEngineError("asset review fields must not be empty")


@dataclass(frozen=True, slots=True)
class AssetReviewCycle:
    cycle_id: str
    source_manifest_checksum: str
    asset_version_ids: tuple[str, ...]
    reviews: tuple[AssetVersionReview, ...] = ()

    def __post_init__(self) -> None:
        if not self.cycle_id.strip() or not self.source_manifest_checksum.strip():
            raise CampaignEngineError("asset review cycle requires an ID and Asset Manifest checksum")
        if not self.asset_version_ids:
            raise CampaignEngineError("asset review cycle requires asset versions")
        if len(self.asset_version_ids) != len(set(self.asset_version_ids)):
            raise CampaignEngineError("asset review cycle version IDs must be unique")
        reviewed_ids = [review.asset_version_id for review in self.reviews]
        if len(reviewed_ids) != len(set(reviewed_ids)):
            raise CampaignEngineError("an asset version can be reviewed only once per cycle")
        if not set(reviewed_ids).issubset(self.asset_version_ids):
            raise CampaignEngineError("asset review references a version outside its review cycle")


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
    creative_bible_source_world_id: str = ""
    creative_bible_source_world_version: str = ""
    creative_bible_source_world_checksum: str = ""
    production_plan: ProductionPlan | None = None
    production_plan_approval: HumanApproval | None = None
    asset_manifest: PlannedAssetManifest | None = None
    production_routes: tuple[ProductionJobRoute, ...] = ()
    asset_versions: tuple[ProducedAssetVersion, ...] = ()
    asset_validations: tuple[AssetTechnicalValidation, ...] = ()
    asset_review_cycles: tuple[AssetReviewCycle, ...] = ()
    publication_authorised: bool = False
    media_spend_authorised: bool = False

    def __post_init__(self) -> None:
        if self.approved_blueprint.artifact_type != "growth_blueprint":
            raise CampaignEngineError("campaign engine requires an approved Growth Blueprint")
        _require_approval_matches(self.approved_blueprint, self.blueprint_approval)
        _require_matt_approval(self.blueprint_approval, "Growth Blueprint")
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
            CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_READY,
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_REVIEW,
            CampaignEngineStage.ASSET_SUITE_APPROVED,
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
            CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_READY,
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_REVIEW,
            CampaignEngineStage.ASSET_SUITE_APPROVED,
        }
        if self.stage in bible_stages:
            if self.selected_campaign_world is None or self.campaign_world_approval is None:
                raise CampaignEngineError("Creative Bible stages require an approved Campaign World")
            _require_approval_matches(self.selected_campaign_world, self.campaign_world_approval)
        if self.stage in {
            CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW,
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_PLANNING,
            CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_READY,
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_REVIEW,
            CampaignEngineStage.ASSET_SUITE_APPROVED,
        } and self.creative_bible is None:
            raise CampaignEngineError("Creative Bible review stages require a Creative Director's Bible")
        if self.creative_bible is not None:
            if self.selected_campaign_world is None:
                raise CampaignEngineError("Creative Director's Bible requires a selected Campaign World")
            source = (
                self.creative_bible_source_world_id,
                self.creative_bible_source_world_version,
                self.creative_bible_source_world_checksum,
            )
            expected_source = (
                self.selected_campaign_world.artifact_id,
                self.selected_campaign_world.version,
                self.selected_campaign_world.checksum,
            )
            if source != expected_source:
                raise CampaignEngineError(
                    "Creative Director's Bible lineage must match the exact selected Campaign World"
                )
        if self.stage in {
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_PLANNING,
            CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_READY,
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_REVIEW,
            CampaignEngineStage.ASSET_SUITE_APPROVED,
        }:
            if not (
                self.creative_bible_quality_review
                and self.creative_bible_quality_review.verdict is QualityVerdict.PASS
                and self.creative_bible_tony_review
                and self.creative_bible_tony_review.disposition is TonyDisposition.FORWARD
            ):
                raise CampaignEngineError("Creative Bible approval gate requires quality and Tony clearance")
        if self.stage in {
            CampaignEngineStage.PRODUCTION_PLANNING,
            CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_READY,
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_REVIEW,
            CampaignEngineStage.ASSET_SUITE_APPROVED,
        }:
            if self.creative_bible is None or self.creative_bible_approval is None:
                raise CampaignEngineError("production planning requires an approved Creative Director's Bible")
            _require_approval_matches(self.creative_bible, self.creative_bible_approval)
        if self.stage in {
            CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_READY,
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_REVIEW,
            CampaignEngineStage.ASSET_SUITE_APPROVED,
        }:
            if self.production_plan is None or self.creative_bible is None:
                raise CampaignEngineError("production plan approval requires a Production Plan")
            plan_source = (
                self.production_plan.source_bible_id,
                self.production_plan.source_bible_version,
                self.production_plan.source_bible_checksum,
            )
            bible_source = (
                self.creative_bible.artifact_id,
                self.creative_bible.version,
                self.creative_bible.checksum,
            )
            if plan_source != bible_source:
                raise CampaignEngineError("Production Plan lineage must match the approved Bible")
        if self.stage in {
            CampaignEngineStage.PRODUCTION_READY,
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_REVIEW,
            CampaignEngineStage.ASSET_SUITE_APPROVED,
        }:
            if self.production_plan is None or self.production_plan_approval is None:
                raise CampaignEngineError("production readiness requires an approved Production Pack")
            _require_matt_approval(self.production_plan_approval, "Production Pack")
            _require_approval_matches(
                self.production_plan.production_pack,
                self.production_plan_approval,
            )
        if self.stage in {
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_REVIEW,
            CampaignEngineStage.ASSET_SUITE_APPROVED,
        }:
            if self.asset_manifest is None or self.production_plan is None:
                raise CampaignEngineError("asset production requires a planned Asset Manifest")
            manifest_source = (
                self.asset_manifest.source_production_pack_id,
                self.asset_manifest.source_production_pack_version,
                self.asset_manifest.source_production_pack_checksum,
            )
            pack = self.production_plan.production_pack
            if manifest_source != (pack.artifact_id, pack.version, pack.checksum):
                raise CampaignEngineError("Asset Manifest lineage must match the approved Production Pack")
            planned_assets = {asset.asset_id: asset for asset in self.asset_manifest.assets}
            jobs_by_id = {job.job_id: job for job in self.production_plan.jobs}
            route_ids: set[str] = set()
            routed_jobs: set[str] = set()
            for route in self.production_routes:
                if route.route_id in route_ids:
                    raise CampaignEngineError("production route IDs must be unique")
                route_ids.add(route.route_id)
                if route.job_id in routed_jobs:
                    raise CampaignEngineError("Production Pack jobs may have only one planned route")
                routed_jobs.add(route.job_id)
                job = jobs_by_id.get(route.job_id)
                if job is None:
                    raise CampaignEngineError("production route references an unknown job")
                if route.required_capability != job.required_capability:
                    raise CampaignEngineError("production route capability does not match its job")
                if route.source_production_pack_checksum != self.production_plan.production_pack.checksum:
                    raise CampaignEngineError("production route lineage must match the Production Pack")
            version_ids: set[str] = set()
            version_keys: set[tuple[str, int]] = set()
            for version in self.asset_versions:
                if version.asset_version_id in version_ids:
                    raise CampaignEngineError("asset version IDs must be unique")
                version_ids.add(version.asset_version_id)
                version_key = (version.asset_id, version.version_number)
                if version_key in version_keys:
                    raise CampaignEngineError("asset version number cannot be overwritten")
                version_keys.add(version_key)
                planned = planned_assets.get(version.asset_id)
                if planned is None:
                    raise CampaignEngineError("asset version references an unknown planned asset")
                if version.production_job_id != planned.production_job_id:
                    raise CampaignEngineError("asset version job does not match its planned asset")
                if version.production_job_id not in routed_jobs:
                    raise CampaignEngineError("asset version requires a planned production route")
                if version.source_manifest_checksum != self.asset_manifest.manifest_artifact.checksum:
                    raise CampaignEngineError("asset version lineage must match the Asset Manifest")
            cycle_ids: set[str] = set()
            versions_by_id = {version.asset_version_id: version for version in self.asset_versions}
            specifications = {
                item.specification_id: item
                for item in self.production_plan.channel_specifications
            }
            validation_ids: set[str] = set()
            for validation in self.asset_validations:
                if validation.validation_id in validation_ids:
                    raise CampaignEngineError("asset technical validation IDs must be unique")
                validation_ids.add(validation.validation_id)
                version = versions_by_id.get(validation.asset_version_id)
                if version is None:
                    raise CampaignEngineError("asset technical validation references an unknown version")
                if validation.file_checksum != version.file_checksum:
                    raise CampaignEngineError(
                        "asset technical validation does not match the exact file checksum"
                    )
                planned = planned_assets[version.asset_id]
                if validation.specification_id != planned.specification_id:
                    raise CampaignEngineError(
                        "asset technical validation does not match the planned specification"
                    )
                specification = specifications[planned.specification_id]
                required_checks = {
                    "file_exists",
                    "file_readable",
                    "expected_file_type",
                    "expected_dimensions",
                    "expected_aspect_ratio",
                    "checksum_recorded",
                    "production_pack_lineage_valid",
                }
                if specification.duration_seconds is not None:
                    required_checks.add("expected_duration")
                checks_by_name = {check.name: check for check in validation.checks}
                if not required_checks.issubset(checks_by_name) or any(
                    not checks_by_name[name].critical for name in required_checks
                ):
                    raise CampaignEngineError(
                        "asset technical validation is missing required critical checks"
                    )
            for cycle in self.asset_review_cycles:
                if cycle.cycle_id in cycle_ids:
                    raise CampaignEngineError("asset review cycle IDs must be unique")
                cycle_ids.add(cycle.cycle_id)
                if cycle.source_manifest_checksum != self.asset_manifest.manifest_artifact.checksum:
                    raise CampaignEngineError("asset review cycle lineage must match the Asset Manifest")
                reviewed_versions = {review.asset_version_id: review for review in cycle.reviews}
                for version_id in cycle.asset_version_ids:
                    if version_id not in versions_by_id:
                        raise CampaignEngineError("asset review cycle references an unknown asset version")
                for review in cycle.reviews:
                    version = versions_by_id[review.asset_version_id]
                    if review.file_checksum != version.file_checksum:
                        raise CampaignEngineError("asset review does not match the exact file checksum")
                    if review.reviewer.strip().casefold() != "matt":
                        raise CampaignEngineError("asset version approval requires Matt")
            if self.stage in {
                CampaignEngineStage.ASSET_REVIEW,
                CampaignEngineStage.ASSET_SUITE_APPROVED,
            }:
                if not self.asset_review_cycles:
                    raise CampaignEngineError("asset review stage requires a review cycle")
                active_cycle = self.asset_review_cycles[-1]
                selected_versions = [versions_by_id[item] for item in active_cycle.asset_version_ids]
                if len(selected_versions) != len(planned_assets):
                    raise CampaignEngineError("asset review requires one version for every planned asset")
                if {item.asset_id for item in selected_versions} != set(planned_assets):
                    raise CampaignEngineError("asset review does not cover every planned asset")
                latest_version_ids = {
                    max(
                        (
                            version
                            for version in self.asset_versions
                            if version.asset_id == asset_id
                        ),
                        key=lambda version: version.version_number,
                    ).asset_version_id
                    for asset_id in planned_assets
                }
                if set(active_cycle.asset_version_ids) != latest_version_ids:
                    raise CampaignEngineError("asset review must bind the latest exact version of every asset")
                for version_id in active_cycle.asset_version_ids:
                    validations = [
                        validation
                        for validation in self.asset_validations
                        if validation.asset_version_id == version_id
                    ]
                    if not validations or not validations[-1].passed:
                        raise CampaignEngineError(
                            "asset review requires a passing technical validation for every exact version"
                        )
                if self.stage is CampaignEngineStage.ASSET_SUITE_APPROVED:
                    if len(reviewed_versions) != len(active_cycle.asset_version_ids) or any(
                        review.decision is not AssetReviewDecision.APPROVE
                        for review in active_cycle.reviews
                    ):
                        raise CampaignEngineError("approved asset suite requires Matt's approval of every exact version")
        elif self.production_routes:
            raise CampaignEngineError("production routes require the asset-production stage")
        elif self.asset_versions:
            raise CampaignEngineError("asset versions require the asset-production stage")
        elif self.asset_validations:
            raise CampaignEngineError("asset technical validations require the asset-production stage")
        elif self.asset_review_cycles:
            raise CampaignEngineError("asset reviews require the asset-production stage")

    @property
    def requires_matt(self) -> bool:
        return self.stage in {
            CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED,
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED,
            CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED,
            CampaignEngineStage.ASSET_REVIEW,
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
            CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED: (
                "Matt approves the exact Production Pack version"
            ),
            CampaignEngineStage.PRODUCTION_READY: (
                "create the planned Asset Manifest from approved Production Pack jobs"
            ),
            CampaignEngineStage.ASSET_PRODUCTION: (
                "route approved jobs and register generated asset versions for human review"
            ),
            CampaignEngineStage.ASSET_REVIEW: "Matt reviews each exact asset version",
            CampaignEngineStage.ASSET_SUITE_APPROVED: (
                "prepare the approved asset suite for a separate delivery or deployment gate"
            ),
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
            selected_campaign_world = _artifact_from_dict(value.get("selected_campaign_world"))
            creative_bible = _artifact_from_dict(value.get("creative_bible"))
            return cls(
                identity=identity,
                approved_blueprint=blueprint,
                blueprint_approval=HumanApproval(**value["blueprint_approval"]),
                stage=CampaignEngineStage(value.get("stage", CampaignEngineStage.STRATEGY_APPROVED.value)),
                campaign_world_candidates=candidates,
                selected_campaign_world=selected_campaign_world,
                campaign_world_approval=_approval_from_dict(value.get("campaign_world_approval")),
                creative_bible=creative_bible,
                creative_bible_quality_review=_quality_from_dict(value.get("creative_bible_quality_review")),
                creative_bible_tony_review=_tony_from_dict(value.get("creative_bible_tony_review")),
                creative_bible_approval=_approval_from_dict(value.get("creative_bible_approval")),
                creative_bible_source_world_id=str(
                    value.get("creative_bible_source_world_id")
                    or (selected_campaign_world.artifact_id if creative_bible and selected_campaign_world else "")
                ),
                creative_bible_source_world_version=str(
                    value.get("creative_bible_source_world_version")
                    or (selected_campaign_world.version if creative_bible and selected_campaign_world else "")
                ),
                creative_bible_source_world_checksum=str(
                    value.get("creative_bible_source_world_checksum")
                    or (selected_campaign_world.checksum if creative_bible and selected_campaign_world else "")
                ),
                production_plan=_production_plan_from_dict(value.get("production_plan")),
                production_plan_approval=_approval_from_dict(value.get("production_plan_approval")),
                asset_manifest=_planned_asset_manifest_from_dict(value.get("asset_manifest")),
                production_routes=tuple(
                    _production_job_route_from_dict(item)
                    for item in value.get("production_routes", [])
                ),
                asset_versions=tuple(
                    _produced_asset_version_from_dict(item)
                    for item in value.get("asset_versions", [])
                ),
                asset_validations=tuple(
                    _asset_technical_validation_from_dict(item)
                    for item in value.get("asset_validations", [])
                ),
                asset_review_cycles=tuple(
                    _asset_review_cycle_from_dict(item)
                    for item in value.get("asset_review_cycles", [])
                ),
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


class CampaignWorldSelectionBrief:
    """Build Tony's evidence-bound comparison without selecting for Matt."""

    @staticmethod
    def build(state: CampaignEngineState) -> dict[str, Any]:
        candidates = []
        ready_candidate_ids = []
        revision_candidate_ids = []
        for candidate in state.campaign_world_candidates:
            quality_review = candidate.quality_review
            tony_review = candidate.tony_review
            review_complete = quality_review is not None and tony_review is not None
            if candidate.ready_for_matt:
                ready_candidate_ids.append(candidate.candidate_id)
            elif review_complete:
                revision_candidate_ids.append(candidate.candidate_id)
            candidates.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "artifact_id": candidate.artifact.artifact_id,
                    "artifact_version": candidate.artifact.version,
                    "artifact_checksum": candidate.artifact.checksum,
                    "artifact_location": candidate.artifact.location,
                    "quality_verdict": quality_review.verdict.value if quality_review else None,
                    "quality_rationale": quality_review.rationale if quality_review else None,
                    "tony_disposition": tony_review.disposition.value if tony_review else None,
                    "tony_rationale": tony_review.rationale if tony_review else None,
                    "review_complete": review_complete,
                    "ready_for_matt": candidate.ready_for_matt,
                }
            )
        return {
            "selection_required": state.stage is CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED,
            "human_selector": "matt",
            "auto_selection_authorised": False,
            "ready_candidate_ids": ready_candidate_ids,
            "revision_candidate_ids": revision_candidate_ids,
            "candidates": candidates,
        }


class FileCampaignEngineRepository:
    """Append-only, hash-chained campaign state scoped to one workspace."""

    _ALLOWED_STAGE_TRANSITIONS = {
        CampaignEngineStage.STRATEGY_APPROVED: {
            CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT,
        },
        CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT: {
            CampaignEngineStage.CAMPAIGN_WORLDS_IN_QUALITY_REVIEW,
        },
        CampaignEngineStage.CAMPAIGN_WORLDS_IN_QUALITY_REVIEW: {
            CampaignEngineStage.CAMPAIGN_WORLDS_IN_QUALITY_REVIEW,
            CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED,
            CampaignEngineStage.CAMPAIGN_WORLDS_IN_DEVELOPMENT,
        },
        CampaignEngineStage.CAMPAIGN_WORLD_SELECTION_REQUIRED: {
            CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT,
        },
        CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT: {
            CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW,
        },
        CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW: {
            CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED,
            CampaignEngineStage.CREATIVE_BIBLE_IN_DEVELOPMENT,
        },
        CampaignEngineStage.CREATIVE_BIBLE_APPROVAL_REQUIRED: {
            CampaignEngineStage.PRODUCTION_PLANNING,
        },
        CampaignEngineStage.PRODUCTION_PLANNING: {
            CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED,
        },
        CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED: {
            CampaignEngineStage.PRODUCTION_READY,
        },
        CampaignEngineStage.PRODUCTION_READY: {
            CampaignEngineStage.ASSET_PRODUCTION,
        },
        CampaignEngineStage.ASSET_PRODUCTION: {
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_REVIEW,
        },
        CampaignEngineStage.ASSET_REVIEW: {
            CampaignEngineStage.ASSET_REVIEW,
            CampaignEngineStage.ASSET_PRODUCTION,
            CampaignEngineStage.ASSET_SUITE_APPROVED,
        },
        CampaignEngineStage.ASSET_SUITE_APPROVED: set(),
    }

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

    def save_transition(
        self,
        expected: CampaignEngineState,
        proposed: CampaignEngineState,
        *,
        transition_id: str,
    ) -> CampaignEngineState:
        """Atomically append one legal transition from the exact current state."""
        if expected.identity != proposed.identity:
            raise CampaignEngineStoreError("campaign transition cannot change campaign identity")
        if (
            expected.approved_blueprint != proposed.approved_blueprint
            or expected.blueprint_approval != proposed.blueprint_approval
        ):
            raise CampaignEngineStoreError("campaign transition cannot replace approved Blueprint evidence")
        if proposed.identity.workspace_id != self.workspace_id:
            raise CampaignEngineStoreError("campaign belongs to a different workspace")
        if not _safe_identifier(transition_id):
            raise CampaignEngineStoreError("transition_id must be a safe identifier")
        allowed = self._ALLOWED_STAGE_TRANSITIONS.get(expected.stage, set())
        if proposed.stage not in allowed:
            raise CampaignEngineStoreError(
                f"illegal persisted campaign transition: {expected.stage.value} -> {proposed.stage.value}"
            )

        path = self._path(expected.identity.client_id, expected.identity.campaign_id)
        proposed_payload = proposed.to_dict()
        proposed_hash = _canonical_hash(proposed_payload)
        with self._file_lock(path, exclusive=True):
            records = self._read_records(path)
            existing = next((record for record in records if record["transition_id"] == transition_id), None)
            if existing:
                if existing["state_hash"] != proposed_hash:
                    raise CampaignEngineStoreError("transition_id replay conflicts with persisted state")
                return CampaignEngineState.from_dict(existing["state"])
            if not records:
                raise CampaignEngineStoreError("campaign transition requires persisted current state")
            persisted_current = CampaignEngineState.from_dict(records[-1]["state"])
            if persisted_current != expected:
                raise CampaignEngineStoreError("campaign transition expected state is stale")
            previous_hash = records[-1]["record_hash"]
            record = {
                "sequence": len(records) + 1,
                "transition_id": transition_id,
                "workspace_id": self.workspace_id,
                "client_id": proposed.identity.client_id,
                "campaign_id": proposed.identity.campaign_id,
                "state_hash": proposed_hash,
                "previous_hash": previous_hash,
                "state": proposed_payload,
            }
            record["record_hash"] = _canonical_hash(record)
            self._append(path, record)
        return proposed

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

    def persist_transition(
        self,
        expected: CampaignEngineState,
        proposed: CampaignEngineState,
        *,
        transition_id: str,
    ) -> CampaignEngineState:
        """Persist a pure-engine transition with stale-state protection."""
        return self.repository.save_transition(
            expected,
            proposed,
            transition_id=transition_id,
        )

    def select_campaign_world(
        self,
        expected: CampaignEngineState,
        candidate_id: str,
        approval: HumanApproval,
        *,
        transition_id: str,
    ) -> CampaignEngineState:
        """Persist Matt's exact-version Campaign World selection."""
        proposed = CampaignEngine().select_campaign_world(
            expected,
            candidate_id,
            approval,
        )
        return self.persist_transition(
            expected,
            proposed,
            transition_id=transition_id,
        )


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
        _require_matt_approval(approval, "Campaign World")
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
        if state.selected_campaign_world is None:
            raise CampaignEngineError("Creative Director's Bible requires a selected Campaign World")
        return replace(
            state,
            stage=CampaignEngineStage.CREATIVE_BIBLE_IN_QUALITY_REVIEW,
            creative_bible=creative_bible,
            creative_bible_quality_review=None,
            creative_bible_tony_review=None,
            creative_bible_approval=None,
            creative_bible_source_world_id=state.selected_campaign_world.artifact_id,
            creative_bible_source_world_version=state.selected_campaign_world.version,
            creative_bible_source_world_checksum=state.selected_campaign_world.checksum,
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
        _require_matt_approval(approval, "Creative Director's Bible")
        self._require_approval_binding(state.creative_bible, approval)
        return replace(
            state,
            stage=CampaignEngineStage.PRODUCTION_PLANNING,
            creative_bible_approval=approval,
        )

    def submit_production_plan(
        self,
        state: CampaignEngineState,
        production_plan: ProductionPlan,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.PRODUCTION_PLANNING)
        if state.creative_bible is None:
            raise CampaignEngineError("Production Plan requires an approved Creative Director's Bible")
        source = (
            production_plan.source_bible_id,
            production_plan.source_bible_version,
            production_plan.source_bible_checksum,
        )
        expected = (
            state.creative_bible.artifact_id,
            state.creative_bible.version,
            state.creative_bible.checksum,
        )
        if source != expected:
            raise CampaignEngineError("Production Plan lineage must match the approved Bible")
        return replace(
            state,
            stage=CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED,
            production_plan=production_plan,
            production_plan_approval=None,
        )

    def approve_production_plan(
        self,
        state: CampaignEngineState,
        approval: HumanApproval,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.PRODUCTION_PLAN_APPROVAL_REQUIRED)
        if state.production_plan is None:
            raise CampaignEngineError("Production Plan is missing")
        _require_matt_approval(approval, "Production Pack")
        self._require_approval_binding(state.production_plan.production_pack, approval)
        return replace(
            state,
            stage=CampaignEngineStage.PRODUCTION_READY,
            production_plan_approval=approval,
        )

    def start_asset_production(
        self,
        state: CampaignEngineState,
        asset_manifest: PlannedAssetManifest,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.PRODUCTION_READY)
        if state.production_plan is None:
            raise CampaignEngineError("asset production requires an approved Production Pack")
        pack = state.production_plan.production_pack
        source = (
            asset_manifest.source_production_pack_id,
            asset_manifest.source_production_pack_version,
            asset_manifest.source_production_pack_checksum,
        )
        if source != (pack.artifact_id, pack.version, pack.checksum):
            raise CampaignEngineError("Asset Manifest lineage must match the approved Production Pack")
        jobs = {job.job_id: job for job in state.production_plan.jobs}
        specifications = {
            item.specification_id: item
            for item in state.production_plan.channel_specifications
        }
        represented_jobs = [asset.production_job_id for asset in asset_manifest.assets]
        if set(represented_jobs) != set(jobs) or len(represented_jobs) != len(jobs):
            raise CampaignEngineError("Asset Manifest must contain exactly one planned asset per Production Pack job")
        for asset in asset_manifest.assets:
            job = jobs[asset.production_job_id]
            specification = specifications[job.specification_id]
            if asset.specification_id != job.specification_id:
                raise CampaignEngineError("planned asset specification does not match its Production Pack job")
            if (
                asset.channel,
                asset.placement,
                asset.market,
                asset.language,
                asset.asset_type,
            ) != (
                specification.channel,
                specification.placement,
                specification.market,
                specification.language,
                specification.asset_type,
            ):
                raise CampaignEngineError("planned asset channel fields do not match its specification")
            if asset.source_bible_checksum != state.production_plan.source_bible_checksum:
                raise CampaignEngineError("planned asset Bible lineage does not match the Production Plan")
        return replace(
            state,
            stage=CampaignEngineStage.ASSET_PRODUCTION,
            asset_manifest=asset_manifest,
            production_routes=(),
            asset_versions=(),
            asset_validations=(),
            asset_review_cycles=(),
        )

    def register_production_route(
        self,
        state: CampaignEngineState,
        route: ProductionJobRoute,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.ASSET_PRODUCTION)
        if state.production_plan is None:
            raise CampaignEngineError("production routing requires a Production Plan")
        if any(item.route_id == route.route_id for item in state.production_routes):
            raise CampaignEngineError("production route ID already exists")
        if any(item.job_id == route.job_id for item in state.production_routes):
            raise CampaignEngineError("Production Pack job already has a planned route")
        job = next(
            (item for item in state.production_plan.jobs if item.job_id == route.job_id),
            None,
        )
        if job is None:
            raise CampaignEngineError("production route references an unknown job")
        if route.required_capability != job.required_capability:
            raise CampaignEngineError("production route capability does not match its job")
        if route.source_production_pack_checksum != state.production_plan.production_pack.checksum:
            raise CampaignEngineError("production route lineage must match the Production Pack")
        return replace(state, production_routes=(*state.production_routes, route))

    def register_asset_version(
        self,
        state: CampaignEngineState,
        version: ProducedAssetVersion,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.ASSET_PRODUCTION)
        if state.asset_manifest is None:
            raise CampaignEngineError("asset version registration requires an Asset Manifest")
        planned = next(
            (asset for asset in state.asset_manifest.assets if asset.asset_id == version.asset_id),
            None,
        )
        if planned is None:
            raise CampaignEngineError("asset version references an unknown planned asset")
        if version.production_job_id != planned.production_job_id:
            raise CampaignEngineError("asset version job does not match its planned asset")
        if version.source_manifest_checksum != state.asset_manifest.manifest_artifact.checksum:
            raise CampaignEngineError("asset version lineage must match the Asset Manifest")
        if any(item.asset_version_id == version.asset_version_id for item in state.asset_versions):
            raise CampaignEngineError("asset version ID already exists")
        existing_numbers = [
            item.version_number
            for item in state.asset_versions
            if item.asset_id == version.asset_id
        ]
        expected_number = max(existing_numbers, default=0) + 1
        if version.version_number != expected_number:
            raise CampaignEngineError(
                f"asset version number must be the next append-only version: {expected_number}"
            )
        return replace(state, asset_versions=(*state.asset_versions, version))

    def validate_asset_version(
        self,
        state: CampaignEngineState,
        *,
        validation_id: str,
        probe: AssetFileProbe,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.ASSET_PRODUCTION)
        if state.asset_manifest is None or state.production_plan is None:
            raise CampaignEngineError("asset technical validation requires production state")
        if not validation_id.strip():
            raise CampaignEngineError("asset technical validation ID must not be empty")
        if any(item.validation_id == validation_id for item in state.asset_validations):
            raise CampaignEngineError("asset technical validation ID already exists")
        version = next(
            (
                item
                for item in state.asset_versions
                if item.asset_version_id == probe.asset_version_id
            ),
            None,
        )
        if version is None:
            raise CampaignEngineError("asset technical validation references an unknown version")
        if probe.file_checksum != version.file_checksum:
            raise CampaignEngineError(
                "asset file probe does not match the exact file checksum"
            )
        planned = next(
            item for item in state.asset_manifest.assets if item.asset_id == version.asset_id
        )
        specification = next(
            item
            for item in state.production_plan.channel_specifications
            if item.specification_id == planned.specification_id
        )
        expected_dimensions = f"{specification.width_px or '*'}x{specification.height_px or '*'}"
        observed_dimensions = f"{probe.width_px or '*'}x{probe.height_px or '*'}"
        dimensions_passed = (
            (specification.width_px is None or probe.width_px == specification.width_px)
            and (specification.height_px is None or probe.height_px == specification.height_px)
        )
        checks = [
            AssetTechnicalCheck(
                name="file_exists",
                passed=probe.file_exists,
                expected="true",
                observed=str(probe.file_exists).lower(),
            ),
            AssetTechnicalCheck(
                name="file_readable",
                passed=probe.file_readable,
                expected="true",
                observed=str(probe.file_readable).lower(),
            ),
            AssetTechnicalCheck(
                name="expected_file_type",
                passed=_normalise_file_format(probe.file_format)
                == _normalise_file_format(specification.file_format),
                expected=specification.file_format,
                observed=probe.file_format,
            ),
            AssetTechnicalCheck(
                name="expected_dimensions",
                passed=dimensions_passed,
                expected=expected_dimensions,
                observed=observed_dimensions,
            ),
            AssetTechnicalCheck(
                name="expected_aspect_ratio",
                passed=_aspect_ratio_matches(
                    specification.aspect_ratio,
                    probe.width_px,
                    probe.height_px,
                ),
                expected=specification.aspect_ratio,
                observed=(
                    f"{probe.width_px}:{probe.height_px}"
                    if probe.width_px is not None and probe.height_px is not None
                    else "unavailable"
                ),
            ),
            AssetTechnicalCheck(
                name="checksum_recorded",
                passed=probe.file_checksum == version.file_checksum,
                expected=version.file_checksum,
                observed=probe.file_checksum,
            ),
            AssetTechnicalCheck(
                name="production_pack_lineage_valid",
                passed=True,
                expected=planned.specification_id,
                observed=specification.specification_id,
            ),
        ]
        if specification.duration_seconds is not None:
            checks.append(
                AssetTechnicalCheck(
                    name="expected_duration",
                    passed=(
                        probe.duration_seconds is not None
                        and abs(probe.duration_seconds - specification.duration_seconds) <= 0.05
                    ),
                    expected=f"{specification.duration_seconds:g}",
                    observed=(
                        f"{probe.duration_seconds:g}"
                        if probe.duration_seconds is not None
                        else "unavailable"
                    ),
                )
            )
        validation = AssetTechnicalValidation(
            validation_id=validation_id,
            asset_version_id=version.asset_version_id,
            file_checksum=version.file_checksum,
            specification_id=specification.specification_id,
            probe_receipt_id=probe.probe_receipt_id,
            checks=tuple(checks),
        )
        return replace(
            state,
            asset_validations=(*state.asset_validations, validation),
        )

    def submit_asset_suite_for_review(
        self,
        state: CampaignEngineState,
        *,
        cycle_id: str,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.ASSET_PRODUCTION)
        if state.asset_manifest is None:
            raise CampaignEngineError("asset review requires an Asset Manifest")
        if not cycle_id.strip():
            raise CampaignEngineError("asset review cycle ID must not be empty")
        if any(cycle.cycle_id == cycle_id for cycle in state.asset_review_cycles):
            raise CampaignEngineError("asset review cycle ID already exists")
        selected_ids: list[str] = []
        for planned in state.asset_manifest.assets:
            versions = [
                version
                for version in state.asset_versions
                if version.asset_id == planned.asset_id
            ]
            if not versions:
                raise CampaignEngineError(
                    "asset review requires a generated version for every planned asset"
                )
            latest = max(versions, key=lambda version: version.version_number)
            validations = [
                validation
                for validation in state.asset_validations
                if validation.asset_version_id == latest.asset_version_id
            ]
            if not validations or not validations[-1].passed:
                raise CampaignEngineError(
                    "asset review requires a passing technical validation for every exact version"
                )
            selected_ids.append(latest.asset_version_id)
        cycle = AssetReviewCycle(
            cycle_id=cycle_id,
            source_manifest_checksum=state.asset_manifest.manifest_artifact.checksum,
            asset_version_ids=tuple(selected_ids),
        )
        return replace(
            state,
            stage=CampaignEngineStage.ASSET_REVIEW,
            asset_review_cycles=(*state.asset_review_cycles, cycle),
        )

    def review_asset_version(
        self,
        state: CampaignEngineState,
        review: AssetVersionReview,
    ) -> CampaignEngineState:
        self._require_stage(state, CampaignEngineStage.ASSET_REVIEW)
        if review.reviewer.strip().casefold() != "matt":
            raise CampaignEngineError("asset version approval requires Matt")
        active_cycle = state.asset_review_cycles[-1]
        if review.asset_version_id not in active_cycle.asset_version_ids:
            raise CampaignEngineError("asset version is not part of the active review cycle")
        if any(item.asset_version_id == review.asset_version_id for item in active_cycle.reviews):
            raise CampaignEngineError("asset version has already been reviewed in this cycle")
        version = next(
            item for item in state.asset_versions if item.asset_version_id == review.asset_version_id
        )
        if review.file_checksum != version.file_checksum:
            raise CampaignEngineError("asset review does not match the exact file checksum")
        updated_cycle = replace(active_cycle, reviews=(*active_cycle.reviews, review))
        cycles = (*state.asset_review_cycles[:-1], updated_cycle)
        if len(updated_cycle.reviews) < len(updated_cycle.asset_version_ids):
            return replace(state, asset_review_cycles=cycles)
        stage = (
            CampaignEngineStage.ASSET_SUITE_APPROVED
            if all(
                item.decision is AssetReviewDecision.APPROVE
                for item in updated_cycle.reviews
            )
            else CampaignEngineStage.ASSET_PRODUCTION
        )
        return replace(state, stage=stage, asset_review_cycles=cycles)

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


def _production_plan_from_dict(value: Any) -> ProductionPlan | None:
    if not isinstance(value, dict):
        return None
    return ProductionPlan(
        production_pack=VersionedArtifact(**value["production_pack"]),
        source_bible_id=value["source_bible_id"],
        source_bible_version=value["source_bible_version"],
        source_bible_checksum=value["source_bible_checksum"],
        channel_specifications=tuple(
            ChannelAssetSpecification(
                **{
                    **item,
                    "constraints": tuple(item.get("constraints", ())),
                }
            )
            for item in value.get("channel_specifications", [])
        ),
        jobs=tuple(
            ProductionJob(
                **{
                    **item,
                    "production_method": ProductionMethod(item["production_method"]),
                }
            )
            for item in value.get("jobs", [])
        ),
        publication_authorised=bool(value.get("publication_authorised", False)),
        media_spend_authorised=bool(value.get("media_spend_authorised", False)),
    )


def _planned_asset_manifest_from_dict(value: Any) -> PlannedAssetManifest | None:
    if not isinstance(value, dict):
        return None
    return PlannedAssetManifest(
        manifest_artifact=VersionedArtifact(**value["manifest_artifact"]),
        source_production_pack_id=value["source_production_pack_id"],
        source_production_pack_version=value["source_production_pack_version"],
        source_production_pack_checksum=value["source_production_pack_checksum"],
        assets=tuple(
            PlannedAssetRecord(
                **{
                    **item,
                    "status": AssetLifecycleStatus(item.get("status", "planned")),
                }
            )
            for item in value.get("assets", [])
        ),
        publication_authorised=bool(value.get("publication_authorised", False)),
        delivery_authorised=bool(value.get("delivery_authorised", False)),
        media_spend_authorised=bool(value.get("media_spend_authorised", False)),
    )


def _production_job_route_from_dict(value: Any) -> ProductionJobRoute:
    if not isinstance(value, dict):
        raise CampaignEngineStoreError("production job route must be an object")
    return ProductionJobRoute(
        **{
            **value,
            "status": ProductionRouteStatus(value.get("status", "planned")),
        }
    )


def _produced_asset_version_from_dict(value: Any) -> ProducedAssetVersion:
    if not isinstance(value, dict):
        raise CampaignEngineStoreError("asset version must be an object")
    return ProducedAssetVersion(
        **{
            **value,
            "status": AssetLifecycleStatus(value.get("status", "generated")),
        }
    )


def _asset_technical_validation_from_dict(value: Any) -> AssetTechnicalValidation:
    if not isinstance(value, dict):
        raise CampaignEngineStoreError("asset technical validation must be an object")
    return AssetTechnicalValidation(
        validation_id=value["validation_id"],
        asset_version_id=value["asset_version_id"],
        file_checksum=value["file_checksum"],
        specification_id=value["specification_id"],
        probe_receipt_id=value["probe_receipt_id"],
        checks=tuple(
            AssetTechnicalCheck(
                name=check["name"],
                passed=bool(check["passed"]),
                expected=check["expected"],
                observed=check["observed"],
                critical=bool(check.get("critical", True)),
            )
            for check in value.get("checks", ())
        ),
    )


def _asset_review_cycle_from_dict(value: Any) -> AssetReviewCycle:
    if not isinstance(value, dict):
        raise CampaignEngineStoreError("asset review cycle must be an object")
    return AssetReviewCycle(
        cycle_id=value["cycle_id"],
        source_manifest_checksum=value["source_manifest_checksum"],
        asset_version_ids=tuple(value.get("asset_version_ids", ())),
        reviews=tuple(
            AssetVersionReview(
                asset_version_id=review["asset_version_id"],
                file_checksum=review["file_checksum"],
                reviewer=review["reviewer"],
                decision=AssetReviewDecision(review["decision"]),
                rationale=review["rationale"],
            )
            for review in value.get("reviews", ())
        ),
    )


def _normalise_file_format(value: str) -> str:
    return value.strip().casefold().removeprefix(".")


def _aspect_ratio_matches(
    expected: str,
    width_px: int | None,
    height_px: int | None,
) -> bool:
    if width_px is None or height_px is None:
        return False
    parts = expected.replace("/", ":").split(":")
    if len(parts) != 2:
        return False
    try:
        expected_width = float(parts[0].strip())
        expected_height = float(parts[1].strip())
    except ValueError:
        return False
    if expected_width <= 0 or expected_height <= 0:
        return False
    return abs((width_px / height_px) - (expected_width / expected_height)) <= 0.001


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


def _require_matt_approval(approval: HumanApproval, artifact_name: str) -> None:
    if approval.approver.strip().casefold() != "matt":
        raise CampaignEngineError(f"{artifact_name} approval requires Matt")


def _canonical_hash(value: Any) -> str:
    canonical = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
