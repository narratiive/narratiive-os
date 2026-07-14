from __future__ import annotations

import json
import re
import tempfile
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence, runtime_checkable
from urllib.parse import urlparse, urlunparse

from .artifact_catalog import ArtifactRecord, FileArtifactCatalog
from .blueprint_orchestrator import EvidenceReference, SourceNote
from .execution_package import ExecutionPackage
from .prompt_registry import FilePromptRegistry, PromptVersion
from .provider import ProviderClient, ProviderResponse
from .research_engine import (
    DEFAULT_ALLOWED_SCHEMES,
    DEFAULT_MAX_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    EvidenceBatch,
    EvidencePack,
    EvidencePackStore,
    EvidenceSource,
    EvidenceSourcePolicy,
    MaterialClaim,
    LocalDocumentIngestionAdapter,
    ResearchEngine,
    ResearchJob,
    ResearchRun,
    WebRetrievalAdapter,
    normalise_text,
    sha256_hex,
    slugify,
    truncate_text,
    utc_now,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_ID = "narratiive-opportunity-card"
DEFAULT_STAGE_ID = "opportunity_card"
DEFAULT_AGENT_ID = "opportunity_card_orchestrator"
DEFAULT_RAW_ARTIFACT_TYPE = "opportunity_card_raw_response"
DEFAULT_STRUCTURED_ARTIFACT_TYPE = "opportunity_card_structured"
DEFAULT_RESEARCH_ARTIFACT_TYPE = "prospect_research_pack"
DEFAULT_CREATIVE_ARTIFACT_TYPE = "opportunity_card_creative_treatment"
DEFAULT_ASSET_BRIEF_ARTIFACT_TYPE = "opportunity_card_speculative_asset_briefs"
DEFAULT_ASSET_METADATA_ARTIFACT_TYPE = "opportunity_card_generated_asset_metadata"
DEFAULT_SELECTED_ASSET_ARTIFACT_TYPE = "opportunity_card_selected_asset_set"
DEFAULT_OUTREACH_ARTIFACT_TYPE = "opportunity_card_outreach_draft"
DEFAULT_REVIEW_ARTIFACT_TYPE = "opportunity_card_review_summary"
DEFAULT_PROMPT_SOURCE_PATH = REPO_ROOT / "prompts" / "narratiive-opportunity-card.md"
DEFAULT_STRATEGIC_PRINCIPLES_PATH = REPO_ROOT / "knowledge" / "blueprint" / "founder-grade-rules.md"
OPPORTUNITY_CARD_STATUSES = (
    "draft",
    "research_complete",
    "card_ready",
    "assets_pending",
    "ready_for_review",
    "blocked",
    "approved",
    "revision_requested",
    "rejected",
    "outreach_ready",
    "sent",
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            import os

            os.fsync(handle.fileno())
        import os

        os.replace(temporary, path)
    finally:
        import os

        if os.path.exists(temporary):
            os.unlink(temporary)


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return tuple(values)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", str(text or "")))


def _safe_identifier(value: str, field_name: str) -> str:
    safe = str(value or "").strip()
    if not safe or safe in {".", ".."} or Path(safe).name != safe or "/" in safe or "\\" in safe:
        raise ValueError(f"{field_name} must be a safe identifier")
    return safe


def _extract_domain(company_url: str) -> str:
    parsed = urlparse(_normalise_url(company_url))
    if not parsed.netloc:
        raise ValueError("company_url must include a hostname")
    return parsed.netloc.split("@")[-1].split(":")[0].lower()


def _normalise_url(company_url: str) -> str:
    value = str(company_url or "").strip()
    if not value:
        raise ValueError("company_url is required")
    parsed = urlparse(value if "://" in value else f"https://{value}")
    if parsed.scheme not in DEFAULT_ALLOWED_SCHEMES:
        parsed = parsed._replace(scheme="https")
    if not parsed.netloc:
        raise ValueError("company_url must include a hostname")
    return urlunparse(parsed._replace(path=parsed.path or "/", params="", query="", fragment=""))


def _slug_from_url(company_url: str) -> str:
    domain = _extract_domain(company_url)
    return slugify(domain.split(".")[0])


def _claim_has_support(evidence_ids: Sequence[str], is_hypothesis: bool) -> bool:
    return bool(evidence_ids) or is_hypothesis


def _dedupe_findings(findings: Sequence["OpportunityCardValidationFinding"]) -> tuple["OpportunityCardValidationFinding", ...]:
    unique: list[OpportunityCardValidationFinding] = []
    seen: set[tuple[Any, ...]] = set()
    for finding in findings:
        key = (
            finding.code,
            finding.severity,
            finding.message,
            finding.location,
            finding.evidence_ids,
            _stable_json(finding.details),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return tuple(unique)


@dataclass(frozen=True, slots=True)
class OpportunityCardValidationFinding:
    code: str
    severity: str
    message: str
    location: str = ""
    evidence_ids: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        severity = str(self.severity).strip().lower()
        if severity not in {"info", "warning", "error", "blocking"}:
            raise ValueError("severity must be info, warning, error, or blocking")
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "evidence_ids", _unique(self.evidence_ids))
        object.__setattr__(self, "details", dict(self.details or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "evidence_ids": list(self.evidence_ids),
            "details": dict(self.details),
        }

    @property
    def is_blocking(self) -> bool:
        return self.severity == "blocking"


@dataclass(frozen=True, slots=True)
class CommercialDiagnosis:
    statement: str
    growth_constraint: str
    evidence_ids: tuple[str, ...] = ()
    source_notes: tuple[SourceNote, ...] = ()
    is_hypothesis: bool = False
    confidence: float = 1.0
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", str(self.statement).strip())
        object.__setattr__(self, "growth_constraint", str(self.growth_constraint).strip())
        object.__setattr__(self, "evidence_ids", _unique(self.evidence_ids))
        object.__setattr__(self, "source_notes", tuple(self.source_notes))
        object.__setattr__(self, "is_hypothesis", bool(self.is_hypothesis))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "growth_constraint": self.growth_constraint,
            "evidence_ids": list(self.evidence_ids),
            "source_notes": [note.to_dict() for note in self.source_notes],
            "is_hypothesis": self.is_hypothesis,
            "confidence": self.confidence,
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class GrowthOpportunity:
    statement: str
    evidence_ids: tuple[str, ...] = ()
    source_notes: tuple[SourceNote, ...] = ()
    is_hypothesis: bool = False
    confidence: float = 1.0
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", str(self.statement).strip())
        object.__setattr__(self, "evidence_ids", _unique(self.evidence_ids))
        object.__setattr__(self, "source_notes", tuple(self.source_notes))
        object.__setattr__(self, "is_hypothesis", bool(self.is_hypothesis))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "evidence_ids": list(self.evidence_ids),
            "source_notes": [note.to_dict() for note in self.source_notes],
            "is_hypothesis": self.is_hypothesis,
            "confidence": self.confidence,
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class NarrativeDirection:
    statement: str
    strategic_shift: str
    evidence_ids: tuple[str, ...] = ()
    source_notes: tuple[SourceNote, ...] = ()
    is_hypothesis: bool = False
    confidence: float = 1.0
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", str(self.statement).strip())
        object.__setattr__(self, "strategic_shift", str(self.strategic_shift).strip())
        object.__setattr__(self, "evidence_ids", _unique(self.evidence_ids))
        object.__setattr__(self, "source_notes", tuple(self.source_notes))
        object.__setattr__(self, "is_hypothesis", bool(self.is_hypothesis))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "strategic_shift": self.strategic_shift,
            "evidence_ids": list(self.evidence_ids),
            "source_notes": [note.to_dict() for note in self.source_notes],
            "is_hypothesis": self.is_hypothesis,
            "confidence": self.confidence,
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class SpeculativeAssetBrief:
    asset_type: str
    brief: str
    output_specification: str
    evidence_ids: tuple[str, ...] = ()
    source_notes: tuple[SourceNote, ...] = ()
    is_hypothesis: bool = True
    status: str = "draft"
    confidence: float = 1.0
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_type", str(self.asset_type).strip())
        object.__setattr__(self, "brief", str(self.brief).strip())
        object.__setattr__(self, "output_specification", str(self.output_specification).strip())
        object.__setattr__(self, "evidence_ids", _unique(self.evidence_ids))
        object.__setattr__(self, "source_notes", tuple(self.source_notes))
        object.__setattr__(self, "is_hypothesis", bool(self.is_hypothesis))
        object.__setattr__(self, "status", str(self.status).strip().lower() or "draft")
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_type": self.asset_type,
            "brief": self.brief,
            "output_specification": self.output_specification,
            "evidence_ids": list(self.evidence_ids),
            "source_notes": [note.to_dict() for note in self.source_notes],
            "is_hypothesis": self.is_hypothesis,
            "status": self.status,
            "confidence": self.confidence,
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class CreativeTreatment:
    creative_territory: str
    treatment: str
    asset_briefs: tuple[SpeculativeAssetBrief, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    source_notes: tuple[SourceNote, ...] = ()
    is_hypothesis: bool = True
    confidence: float = 1.0
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "creative_territory", str(self.creative_territory).strip())
        object.__setattr__(self, "treatment", str(self.treatment).strip())
        object.__setattr__(self, "asset_briefs", tuple(self.asset_briefs))
        object.__setattr__(self, "evidence_ids", _unique(self.evidence_ids))
        object.__setattr__(self, "source_notes", tuple(self.source_notes))
        object.__setattr__(self, "is_hypothesis", bool(self.is_hypothesis))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "creative_territory": self.creative_territory,
            "treatment": self.treatment,
            "asset_briefs": [brief.to_dict() for brief in self.asset_briefs],
            "evidence_ids": list(self.evidence_ids),
            "source_notes": [note.to_dict() for note in self.source_notes],
            "is_hypothesis": self.is_hypothesis,
            "confidence": self.confidence,
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class OutreachDraft:
    subject: str
    body: str
    call_to_action: str
    evidence_ids: tuple[str, ...] = ()
    source_notes: tuple[SourceNote, ...] = ()
    is_hypothesis: bool = False
    confidence: float = 1.0
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject", str(self.subject).strip())
        object.__setattr__(self, "body", str(self.body).strip())
        object.__setattr__(self, "call_to_action", str(self.call_to_action).strip())
        object.__setattr__(self, "evidence_ids", _unique(self.evidence_ids))
        object.__setattr__(self, "source_notes", tuple(self.source_notes))
        object.__setattr__(self, "is_hypothesis", bool(self.is_hypothesis))
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "body": self.body,
            "call_to_action": self.call_to_action,
            "evidence_ids": list(self.evidence_ids),
            "source_notes": [note.to_dict() for note in self.source_notes],
            "is_hypothesis": self.is_hypothesis,
            "confidence": self.confidence,
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class OpportunityCardLineage:
    research_pack_id: str
    research_pack_checksum: str
    research_pack_path: str
    prompt_id: str
    prompt_version: int
    prompt_checksum: str
    provider_id: str
    model_id: str
    requested_provider_id: str
    requested_model_id: str
    routing_policy_id: str
    routing_policy_version: str
    raw_response_artifact: ArtifactRecord
    structured_artifact: ArtifactRecord | None = None
    research_pack_artifact: ArtifactRecord | None = None
    creative_treatment_artifact: ArtifactRecord | None = None
    speculative_asset_briefs_artifact: ArtifactRecord | None = None
    generated_asset_metadata_artifact: ArtifactRecord | None = None
    selected_asset_set_artifact: ArtifactRecord | None = None
    outreach_draft_artifact: ArtifactRecord | None = None
    review_summary_artifact: ArtifactRecord | None = None
    evidence_pack_ids: tuple[str, ...] = ()
    artifact_lineage: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "research_pack_id", str(self.research_pack_id).strip())
        object.__setattr__(self, "research_pack_checksum", str(self.research_pack_checksum).strip())
        object.__setattr__(self, "research_pack_path", str(self.research_pack_path).strip())
        object.__setattr__(self, "prompt_id", str(self.prompt_id).strip())
        object.__setattr__(self, "prompt_version", int(self.prompt_version))
        object.__setattr__(self, "prompt_checksum", str(self.prompt_checksum).strip())
        object.__setattr__(self, "provider_id", str(self.provider_id).strip())
        object.__setattr__(self, "model_id", str(self.model_id).strip())
        object.__setattr__(self, "requested_provider_id", str(self.requested_provider_id).strip())
        object.__setattr__(self, "requested_model_id", str(self.requested_model_id).strip())
        object.__setattr__(self, "routing_policy_id", str(self.routing_policy_id).strip())
        object.__setattr__(self, "routing_policy_version", str(self.routing_policy_version).strip())
        object.__setattr__(self, "evidence_pack_ids", _unique(self.evidence_pack_ids))
        object.__setattr__(self, "artifact_lineage", tuple(dict.fromkeys(str(item).strip() for item in self.artifact_lineage if str(item).strip())))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        data = {
            "research_pack_id": self.research_pack_id,
            "research_pack_checksum": self.research_pack_checksum,
            "research_pack_path": self.research_pack_path,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_checksum": self.prompt_checksum,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "requested_provider_id": self.requested_provider_id,
            "requested_model_id": self.requested_model_id,
            "routing_policy_id": self.routing_policy_id,
            "routing_policy_version": self.routing_policy_version,
            "raw_response_artifact": self.raw_response_artifact.to_dict(),
            "evidence_pack_ids": list(self.evidence_pack_ids),
            "artifact_lineage": list(self.artifact_lineage),
            "extensions": dict(self.extensions),
        }
        if self.structured_artifact is not None:
            data["structured_artifact"] = self.structured_artifact.to_dict()
        if self.research_pack_artifact is not None:
            data["research_pack_artifact"] = self.research_pack_artifact.to_dict()
        if self.creative_treatment_artifact is not None:
            data["creative_treatment_artifact"] = self.creative_treatment_artifact.to_dict()
        if self.speculative_asset_briefs_artifact is not None:
            data["speculative_asset_briefs_artifact"] = self.speculative_asset_briefs_artifact.to_dict()
        if self.generated_asset_metadata_artifact is not None:
            data["generated_asset_metadata_artifact"] = self.generated_asset_metadata_artifact.to_dict()
        if self.selected_asset_set_artifact is not None:
            data["selected_asset_set_artifact"] = self.selected_asset_set_artifact.to_dict()
        if self.outreach_draft_artifact is not None:
            data["outreach_draft_artifact"] = self.outreach_draft_artifact.to_dict()
        if self.review_summary_artifact is not None:
            data["review_summary_artifact"] = self.review_summary_artifact.to_dict()
        return data


@dataclass(frozen=True, slots=True)
class OpportunityCard:
    card_id: str
    workspace_id: str
    client_id: str
    company_name: str
    company_url: str
    market_category_context: str
    commercial_diagnosis: CommercialDiagnosis
    growth_opportunity: GrowthOpportunity
    narrative_direction: NarrativeDirection
    creative_treatment: CreativeTreatment
    speculative_asset_briefs: tuple[SpeculativeAssetBrief, ...]
    outreach_draft: OutreachDraft
    source_notes: tuple[SourceNote, ...]
    evidence_references: tuple[EvidenceReference, ...]
    recommended_next_conversation: str
    disclaimer: str
    confidence: float
    status: str
    validation_findings: tuple[OpportunityCardValidationFinding, ...]
    lineage: OpportunityCardLineage
    created_at: str = field(default_factory=utc_now)
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _safe_identifier(self.card_id, "card_id")
        _safe_identifier(self.workspace_id, "workspace_id")
        _safe_identifier(self.client_id, "client_id")
        object.__setattr__(self, "company_name", str(self.company_name).strip())
        object.__setattr__(self, "company_url", str(self.company_url).strip())
        object.__setattr__(self, "market_category_context", str(self.market_category_context).strip())
        object.__setattr__(self, "speculative_asset_briefs", tuple(self.speculative_asset_briefs))
        object.__setattr__(self, "source_notes", tuple(self.source_notes))
        object.__setattr__(self, "evidence_references", tuple(self.evidence_references))
        object.__setattr__(self, "recommended_next_conversation", str(self.recommended_next_conversation).strip())
        object.__setattr__(self, "disclaimer", str(self.disclaimer).strip())
        object.__setattr__(self, "confidence", float(self.confidence))
        status = str(self.status).strip().lower()
        if status and status not in OPPORTUNITY_CARD_STATUSES:
            raise ValueError(f"unsupported opportunity card status: {status}")
        object.__setattr__(self, "status", status or "draft")
        object.__setattr__(self, "validation_findings", tuple(self.validation_findings))
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    @property
    def sections(self) -> tuple[CommercialDiagnosis, GrowthOpportunity, NarrativeDirection, CreativeTreatment, OutreachDraft]:
        return (
            self.commercial_diagnosis,
            self.growth_opportunity,
            self.narrative_direction,
            self.creative_treatment,
            self.outreach_draft,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "company_name": self.company_name,
            "company_url": self.company_url,
            "market_category_context": self.market_category_context,
            "commercial_diagnosis": self.commercial_diagnosis.to_dict(),
            "growth_opportunity": self.growth_opportunity.to_dict(),
            "narrative_direction": self.narrative_direction.to_dict(),
            "creative_treatment": self.creative_treatment.to_dict(),
            "speculative_asset_briefs": [brief.to_dict() for brief in self.speculative_asset_briefs],
            "outreach_draft": self.outreach_draft.to_dict(),
            "source_notes": [note.to_dict() for note in self.source_notes],
            "evidence_references": [reference.to_dict() for reference in self.evidence_references],
            "recommended_next_conversation": self.recommended_next_conversation,
            "disclaimer": self.disclaimer,
            "confidence": self.confidence,
            "status": self.status,
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "lineage": self.lineage.to_dict(),
            "created_at": self.created_at,
            "extensions": dict(self.extensions),
        }


@dataclass(frozen=True, slots=True)
class OpportunityCardChangeSummary:
    field: str
    before: Any
    after: Any
    reason: str = ""

    def __post_init__(self) -> None:
        _safe_identifier(self.field, "field")

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class OpportunityCardRequest:
    job_id: str
    workspace_id: str
    client_id: str
    company_url: str
    company_name: str = ""
    requested_by: str = "runtime"
    draft_mode: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _safe_identifier(self.job_id, "job_id")
        _safe_identifier(self.workspace_id, "workspace_id")
        _safe_identifier(self.client_id, "client_id")
        object.__setattr__(self, "company_url", _normalise_url(self.company_url))
        object.__setattr__(self, "company_name", str(self.company_name).strip())
        object.__setattr__(self, "requested_by", str(self.requested_by).strip() or "runtime")
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @property
    def company_domain(self) -> str:
        return _extract_domain(self.company_url)

    @classmethod
    def from_company_url(
        cls,
        company_url: str,
        *,
        company_name: str | None = None,
        requested_by: str = "runtime",
        workspace_id: str | None = None,
        client_id: str | None = None,
        draft_mode: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> "OpportunityCardRequest":
        normalised_url = _normalise_url(company_url)
        derived_name = (company_name or _extract_domain(normalised_url)).strip()
        safe_workspace = slugify(workspace_id or derived_name or _slug_from_url(normalised_url))
        safe_client = slugify(client_id or safe_workspace)
        job_id = f"opportunity-{safe_workspace}-{sha256_hex(normalised_url)[:10]}"
        return cls(
            job_id=job_id,
            workspace_id=safe_workspace,
            client_id=safe_client,
            company_url=normalised_url,
            company_name=derived_name,
            requested_by=requested_by,
            draft_mode=draft_mode,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "company_url": self.company_url,
            "company_name": self.company_name,
            "requested_by": self.requested_by,
            "draft_mode": self.draft_mode,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "request_checksum": self.request_checksum(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OpportunityCardRequest":
        company_url = str(data.get("company_url") or data.get("url") or "").strip()
        if not company_url:
            raise ValueError("company_url is required")
        return cls(
            job_id=str(data.get("job_id") or data.get("request_id") or "").strip()
            or f"opportunity-{slugify(str(data.get('workspace_id') or data.get('client_id') or _slug_from_url(company_url)))}-{sha256_hex(_normalise_url(company_url))[:10]}",
            workspace_id=str(data.get("workspace_id") or data.get("client_id") or slugify(data.get("company_name") or _extract_domain(company_url))).strip() or slugify(_extract_domain(company_url)),
            client_id=str(data.get("client_id") or data.get("workspace_id") or slugify(data.get("company_name") or _extract_domain(company_url))).strip() or slugify(_extract_domain(company_url)),
            company_url=company_url,
            company_name=str(data.get("company_name") or "").strip(),
            requested_by=str(data.get("requested_by") or "runtime").strip() or "runtime",
            draft_mode=bool(data.get("draft_mode", True)),
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at") or utc_now()),
        )

    def request_checksum(self) -> str:
        payload = {
            "job_id": self.job_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "company_url": self.company_url,
            "company_name": self.company_name,
            "requested_by": self.requested_by,
            "draft_mode": self.draft_mode,
            "metadata": self.metadata,
        }
        return sha256_hex(_stable_json(payload))


@dataclass(frozen=True, slots=True)
class OpportunityCardEngineResponse:
    raw_response: str
    provider_id: str
    model_id: str
    prompt_id: str
    prompt_version: int
    prompt_checksum: str
    requested_provider_id: str = ""
    requested_model_id: str = ""
    routing_policy_id: str = ""
    routing_policy_version: str = ""
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", str(self.provider_id).strip())
        object.__setattr__(self, "model_id", str(self.model_id).strip())
        object.__setattr__(self, "prompt_id", str(self.prompt_id).strip())
        object.__setattr__(self, "provider_metadata", dict(self.provider_metadata or {}))


@runtime_checkable
class OpportunityCardEngine(Protocol):
    name: str

    def generate(
        self,
        request: OpportunityCardRequest,
        prompt: PromptVersion,
        research_pack: EvidencePack,
        research_pack_artifact: ArtifactRecord,
    ) -> OpportunityCardEngineResponse:
        ...


@dataclass(frozen=True, slots=True)
class AssetGenerationPolicy:
    max_attempts: int = 6
    max_selected_outputs: int = 3
    revision_rounds: int = 1
    hard_budget_units: int = 1
    hard_budget_currency: str = "credits"
    external_use_requires_approval: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.max_selected_outputs <= 0:
            raise ValueError("max_selected_outputs must be positive")
        if self.revision_rounds < 0:
            raise ValueError("revision_rounds must not be negative")
        if self.hard_budget_units <= 0:
            raise ValueError("hard_budget_units must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SpeculativeAssetRequest:
    job_id: str
    workspace_id: str
    client_id: str
    card_id: str
    creative_territory: str
    asset_type: str
    prompt: str
    output_specification: str
    attempt_no: int
    revision_round: int = 0
    requested_by: str = "runtime"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _safe_identifier(self.job_id, "job_id")
        _safe_identifier(self.workspace_id, "workspace_id")
        _safe_identifier(self.client_id, "client_id")
        _safe_identifier(self.card_id, "card_id")
        object.__setattr__(self, "creative_territory", str(self.creative_territory).strip())
        object.__setattr__(self, "asset_type", str(self.asset_type).strip())
        object.__setattr__(self, "prompt", str(self.prompt).strip())
        object.__setattr__(self, "output_specification", str(self.output_specification).strip())
        object.__setattr__(self, "attempt_no", int(self.attempt_no))
        object.__setattr__(self, "revision_round", int(self.revision_round))
        object.__setattr__(self, "requested_by", str(self.requested_by).strip() or "runtime")
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SpeculativeAssetResult:
    provider_name: str
    provider_job_id: str
    job_id: str
    workspace_id: str
    client_id: str
    card_id: str
    creative_territory: str
    asset_type: str
    status: str
    raw_response: str
    prompt_id: str = ""
    prompt_version: int = 0
    prompt_checksum: str = ""
    model_id: str = ""
    cost_units: int = 0
    cost_currency: str = "credits"
    selected: bool = False
    rejection_reason: str = ""
    output_artifact: ArtifactRecord | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_name", str(self.provider_name).strip())
        object.__setattr__(self, "provider_job_id", str(self.provider_job_id).strip())
        object.__setattr__(self, "job_id", str(self.job_id).strip())
        object.__setattr__(self, "workspace_id", str(self.workspace_id).strip())
        object.__setattr__(self, "client_id", str(self.client_id).strip())
        object.__setattr__(self, "card_id", str(self.card_id).strip())
        object.__setattr__(self, "creative_territory", str(self.creative_territory).strip())
        object.__setattr__(self, "asset_type", str(self.asset_type).strip())
        object.__setattr__(self, "status", str(self.status).strip().lower())
        object.__setattr__(self, "prompt_id", str(self.prompt_id).strip())
        object.__setattr__(self, "prompt_checksum", str(self.prompt_checksum).strip())
        object.__setattr__(self, "model_id", str(self.model_id).strip())
        object.__setattr__(self, "cost_units", int(self.cost_units))
        object.__setattr__(self, "cost_currency", str(self.cost_currency).strip() or "credits")
        object.__setattr__(self, "selected", bool(self.selected))
        object.__setattr__(self, "rejection_reason", str(self.rejection_reason).strip())
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.output_artifact is not None:
            data["output_artifact"] = self.output_artifact.to_dict()
        return data


@dataclass(frozen=True, slots=True)
class SpeculativeAssetSet:
    job_id: str
    workspace_id: str
    client_id: str
    card_id: str
    policy: AssetGenerationPolicy
    candidate_results: tuple[SpeculativeAssetResult, ...]
    selected_results: tuple[SpeculativeAssetResult, ...]
    rejected_results: tuple[SpeculativeAssetResult, ...]
    approval_required: bool
    status: str
    created_at: str = field(default_factory=utc_now)
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _safe_identifier(self.job_id, "job_id")
        _safe_identifier(self.workspace_id, "workspace_id")
        _safe_identifier(self.client_id, "client_id")
        _safe_identifier(self.card_id, "card_id")
        object.__setattr__(self, "candidate_results", tuple(self.candidate_results))
        object.__setattr__(self, "selected_results", tuple(self.selected_results))
        object.__setattr__(self, "rejected_results", tuple(self.rejected_results))
        object.__setattr__(self, "approval_required", bool(self.approval_required))
        object.__setattr__(self, "status", str(self.status).strip().lower())
        object.__setattr__(self, "extensions", dict(self.extensions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "card_id": self.card_id,
            "policy": self.policy.to_dict(),
            "candidate_results": [result.to_dict() for result in self.candidate_results],
            "selected_results": [result.to_dict() for result in self.selected_results],
            "rejected_results": [result.to_dict() for result in self.rejected_results],
            "approval_required": self.approval_required,
            "status": self.status,
            "created_at": self.created_at,
            "extensions": dict(self.extensions),
        }


@runtime_checkable
class SpeculativeAssetProvider(Protocol):
    name: str

    def submit(self, request: SpeculativeAssetRequest) -> SpeculativeAssetResult:
        ...

    def status(self, provider_job_id: str) -> SpeculativeAssetResult:
        ...

    def retrieve(self, provider_job_id: str) -> SpeculativeAssetResult:
        ...


@dataclass(frozen=True, slots=True)
class HiggsfieldConfiguration:
    api_key_env: str = "HIGGSFIELD_API_KEY"
    base_url_env: str = "HIGGSFIELD_API_BASE_URL"
    model_env: str = "HIGGSFIELD_MODEL"
    timeout_seconds: int = 300
    retry_limit: int = 2

    def from_env(self) -> dict[str, Any]:
        import os

        api_key = os.environ.get(self.api_key_env, "").strip()
        base_url = os.environ.get(self.base_url_env, "").strip()
        model = os.environ.get(self.model_env, "").strip()
        configured = bool(api_key and base_url and model)
        reason = "configured" if configured else "not_configured"
        return {
            "configured": configured,
            "reason": reason,
            "api_key_env": self.api_key_env,
            "base_url_env": self.base_url_env,
            "model_env": self.model_env,
            "timeout_seconds": self.timeout_seconds,
            "retry_limit": self.retry_limit,
            "model": model,
            "base_url": base_url,
        }


class HiggsfieldNotConfiguredError(RuntimeError):
    pass


class HiggsfieldSpeculativeAssetProvider:
    name = "higgsfield"

    def __init__(self, config: HiggsfieldConfiguration | None = None) -> None:
        self.config = config or HiggsfieldConfiguration()

    def submit(self, request: SpeculativeAssetRequest) -> SpeculativeAssetResult:
        health = self.config.from_env()
        if not health["configured"]:
            return SpeculativeAssetResult(
                provider_name=self.name,
                provider_job_id=f"unsupported-{request.job_id}-{request.attempt_no}",
                job_id=request.job_id,
                workspace_id=request.workspace_id,
                client_id=request.client_id,
                card_id=request.card_id,
                creative_territory=request.creative_territory,
                asset_type=request.asset_type,
                status="not_configured",
                raw_response=json.dumps(
                    {
                        "status": "not_configured",
                        "reason": "Higgsfield credentials or endpoint are unavailable.",
                        "health": health,
                    },
                    sort_keys=True,
                ),
                model_id=health.get("model", ""),
                metadata={"health": health, "request": request.to_dict()},
            )
        raise HiggsfieldNotConfiguredError(
            "Live Higgsfield adapter is not implemented in this repository snapshot."
        )

    def status(self, provider_job_id: str) -> SpeculativeAssetResult:
        health = self.config.from_env()
        return SpeculativeAssetResult(
            provider_name=self.name,
            provider_job_id=provider_job_id,
            job_id=provider_job_id,
            workspace_id="legacy",
            client_id="legacy",
            card_id="legacy",
            creative_territory="",
            asset_type="",
            status="not_configured" if not health["configured"] else "unsupported",
            raw_response=json.dumps({"health": health}, sort_keys=True),
            model_id=health.get("model", ""),
            metadata={"health": health},
        )

    def retrieve(self, provider_job_id: str) -> SpeculativeAssetResult:
        return self.status(provider_job_id)


class FakeSpeculativeAssetProvider:
    name = "fake_speculative_asset_provider"

    def __init__(
        self,
        *,
        result_factory: Callable[[SpeculativeAssetRequest], SpeculativeAssetResult] | None = None,
    ) -> None:
        self.result_factory = result_factory
        self._results: dict[str, SpeculativeAssetResult] = {}

    def submit(self, request: SpeculativeAssetRequest) -> SpeculativeAssetResult:
        if self.result_factory is not None:
            result = self.result_factory(request)
        else:
            result = SpeculativeAssetResult(
                provider_name=self.name,
                provider_job_id=f"fake-{sha256_hex(_stable_json(request.to_dict()))[:12]}",
                job_id=request.job_id,
                workspace_id=request.workspace_id,
                client_id=request.client_id,
                card_id=request.card_id,
                creative_territory=request.creative_territory,
                asset_type=request.asset_type,
                status="generated",
                raw_response=json.dumps(
                    {
                        "asset_type": request.asset_type,
                        "creative_territory": request.creative_territory,
                        "prompt": request.prompt,
                        "output_specification": request.output_specification,
                        "attempt_no": request.attempt_no,
                        "revision_round": request.revision_round,
                    },
                    sort_keys=True,
                ),
                cost_units=1,
                selected=False,
                metadata={"request": request.to_dict()},
            )
        self._results[result.provider_job_id] = result
        return result

    def status(self, provider_job_id: str) -> SpeculativeAssetResult:
        return self._results[provider_job_id]

    def retrieve(self, provider_job_id: str) -> SpeculativeAssetResult:
        return self._results[provider_job_id]


class OpportunityCardError(RuntimeError):
    pass


class OpportunityCardValidationError(OpportunityCardError):
    pass


class OpportunityCardBlockedError(OpportunityCardError):
    pass


class FileOpportunityCardStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _directory(self, workspace_id: str, client_id: str, job_id: str) -> Path:
        return (
            self.root
            / "workspaces"
            / slugify(workspace_id)
            / "clients"
            / slugify(client_id)
            / slugify(job_id)
            / "versions"
        )

    def history(self, workspace_id: str, client_id: str, job_id: str) -> list["OpportunityCardVersionRecord"]:
        directory = self._directory(workspace_id, client_id, job_id)
        if not directory.exists():
            return []
        records = []
        for path in sorted(directory.glob("v*.json")):
            records.append(OpportunityCardVersionRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return sorted(records, key=lambda item: item.version)

    def latest(self, workspace_id: str, client_id: str, job_id: str) -> "OpportunityCardVersionRecord" | None:
        history = self.history(workspace_id, client_id, job_id)
        return history[-1] if history else None

    def history_by_job(self, job_id: str) -> list["OpportunityCardVersionRecord"]:
        job_slug = slugify(job_id)
        records: list[OpportunityCardVersionRecord] = []
        for path in sorted(self.root.glob(f"workspaces/*/clients/*/{job_slug}/versions/v*.json")):
            records.append(OpportunityCardVersionRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return sorted(records, key=lambda item: item.version)

    def latest_by_job(self, job_id: str) -> "OpportunityCardVersionRecord" | None:
        history = self.history_by_job(job_id)
        return history[-1] if history else None

    def get(
        self,
        workspace_id: str,
        client_id: str,
        job_id: str,
        version: int,
    ) -> "OpportunityCardVersionRecord":
        path = self._directory(workspace_id, client_id, job_id) / f"v{version}.json"
        if not path.exists():
            raise KeyError(f"opportunity card version not found: {workspace_id}/{client_id}/{job_id}@{version}")
        return OpportunityCardVersionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def get_by_job(self, job_id: str, version: int) -> "OpportunityCardVersionRecord":
        job_slug = slugify(job_id)
        matches = sorted(self.root.glob(f"workspaces/*/clients/*/{job_slug}/versions/v{version}.json"))
        if not matches:
            raise KeyError(f"opportunity card version not found: {job_id}@{version}")
        return OpportunityCardVersionRecord.from_dict(json.loads(matches[-1].read_text(encoding="utf-8")))

    def save(self, record: "OpportunityCardVersionRecord") -> Path:
        directory = self._directory(record.workspace_id, record.client_id, record.job_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"v{record.version}.json"
        if path.exists():
            raise ValueError(f"opportunity card version already exists: {path.name}")
        _atomic_write_text(path, json.dumps(record.to_dict(), indent=2, sort_keys=True, default=str) + "\n")
        return path


@dataclass(frozen=True, slots=True)
class OpportunityCardVersionRecord:
    job_id: str
    workspace_id: str
    client_id: str
    version: int
    request: OpportunityCardRequest
    research_pack_id: str
    input_checksum: str
    prompt_id: str
    prompt_version: int
    prompt_checksum: str
    provider_id: str
    model_id: str
    requested_provider_id: str
    requested_model_id: str
    routing_policy_id: str
    routing_policy_version: str
    opportunity_card: OpportunityCard
    research_pack_artifact: ArtifactRecord
    raw_response_artifact: ArtifactRecord
    structured_artifact: ArtifactRecord
    creative_treatment_artifact: ArtifactRecord
    speculative_asset_briefs_artifact: ArtifactRecord
    generated_asset_metadata_artifact: ArtifactRecord
    selected_asset_set_artifact: ArtifactRecord
    outreach_draft_artifact: ArtifactRecord
    review_summary_artifact: ArtifactRecord
    validation_findings: tuple[OpportunityCardValidationFinding, ...]
    change_summary: tuple[OpportunityCardChangeSummary, ...]
    previous_version: int | None
    artifact_lineage: tuple[str, ...]
    approval_history: tuple[dict[str, Any], ...] = ()
    status: str = "draft"
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _safe_identifier(self.job_id, "job_id")
        _safe_identifier(self.workspace_id, "workspace_id")
        _safe_identifier(self.client_id, "client_id")
        object.__setattr__(self, "validation_findings", tuple(self.validation_findings))
        object.__setattr__(self, "change_summary", tuple(self.change_summary))
        object.__setattr__(self, "artifact_lineage", tuple(dict.fromkeys(str(item).strip() for item in self.artifact_lineage if str(item).strip())))
        object.__setattr__(self, "approval_history", tuple(dict(item) for item in self.approval_history))
        object.__setattr__(self, "status", str(self.status).strip().lower())

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "version": self.version,
            "request": self.request.to_dict(),
            "research_pack_id": self.research_pack_id,
            "input_checksum": self.input_checksum,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_checksum": self.prompt_checksum,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "requested_provider_id": self.requested_provider_id,
            "requested_model_id": self.requested_model_id,
            "routing_policy_id": self.routing_policy_id,
            "routing_policy_version": self.routing_policy_version,
            "opportunity_card": self.opportunity_card.to_dict(),
            "research_pack_artifact": self.research_pack_artifact.to_dict(),
            "raw_response_artifact": self.raw_response_artifact.to_dict(),
            "structured_artifact": self.structured_artifact.to_dict(),
            "creative_treatment_artifact": self.creative_treatment_artifact.to_dict(),
            "speculative_asset_briefs_artifact": self.speculative_asset_briefs_artifact.to_dict(),
            "generated_asset_metadata_artifact": self.generated_asset_metadata_artifact.to_dict(),
            "selected_asset_set_artifact": self.selected_asset_set_artifact.to_dict(),
            "outreach_draft_artifact": self.outreach_draft_artifact.to_dict(),
            "review_summary_artifact": self.review_summary_artifact.to_dict(),
            "validation_findings": [finding.to_dict() for finding in self.validation_findings],
            "change_summary": [summary.to_dict() for summary in self.change_summary],
            "previous_version": self.previous_version,
            "artifact_lineage": list(self.artifact_lineage),
            "approval_history": [dict(item) for item in self.approval_history],
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OpportunityCardVersionRecord":
        card = _load_opportunity_card(data.get("opportunity_card") or {})
        return cls(
            job_id=str(data["job_id"]),
            workspace_id=str(data["workspace_id"]),
            client_id=str(data["client_id"]),
            version=int(data["version"]),
            request=OpportunityCardRequest.from_dict(data["request"]),
            research_pack_id=str(data["research_pack_id"]),
            input_checksum=str(data["input_checksum"]),
            prompt_id=str(data["prompt_id"]),
            prompt_version=int(data["prompt_version"]),
            prompt_checksum=str(data["prompt_checksum"]),
            provider_id=str(data["provider_id"]),
            model_id=str(data["model_id"]),
            requested_provider_id=str(data.get("requested_provider_id", data["provider_id"])),
            requested_model_id=str(data.get("requested_model_id", data["model_id"])),
            routing_policy_id=str(data.get("routing_policy_id", "")),
            routing_policy_version=str(data.get("routing_policy_version", "")),
            opportunity_card=card,
            research_pack_artifact=ArtifactRecord.from_dict(data["research_pack_artifact"]),
            raw_response_artifact=ArtifactRecord.from_dict(data["raw_response_artifact"]),
            structured_artifact=ArtifactRecord.from_dict(data["structured_artifact"]),
            creative_treatment_artifact=ArtifactRecord.from_dict(data["creative_treatment_artifact"]),
            speculative_asset_briefs_artifact=ArtifactRecord.from_dict(data["speculative_asset_briefs_artifact"]),
            generated_asset_metadata_artifact=ArtifactRecord.from_dict(data["generated_asset_metadata_artifact"]),
            selected_asset_set_artifact=ArtifactRecord.from_dict(data["selected_asset_set_artifact"]),
            outreach_draft_artifact=ArtifactRecord.from_dict(data["outreach_draft_artifact"]),
            review_summary_artifact=ArtifactRecord.from_dict(data["review_summary_artifact"]),
            validation_findings=_load_validation_findings(data.get("validation_findings") or []),
            change_summary=tuple(
                OpportunityCardChangeSummary(
                    field=str(item["field"]),
                    before=item.get("before"),
                    after=item.get("after"),
                    reason=str(item.get("reason", "")),
                )
                for item in data.get("change_summary") or []
            ),
            previous_version=int(data["previous_version"]) if data.get("previous_version") is not None else None,
            artifact_lineage=tuple(data.get("artifact_lineage") or ()),
            approval_history=tuple(data.get("approval_history") or ()),
            status=str(data.get("status", "draft")),
            created_at=str(data.get("created_at", utc_now())),
        )


@dataclass(frozen=True, slots=True)
class OpportunityCardEnginePayload:
    raw_response: str
    provider_id: str
    model_id: str
    prompt_id: str
    prompt_version: int
    prompt_checksum: str
    requested_provider_id: str = ""
    requested_model_id: str = ""
    routing_policy_id: str = ""
    routing_policy_version: str = ""
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_metadata", dict(self.provider_metadata or {}))


def _load_validation_findings(items: Sequence[Mapping[str, Any]]) -> tuple[OpportunityCardValidationFinding, ...]:
    return tuple(
        OpportunityCardValidationFinding(
            code=str(item.get("code", "")),
            severity=str(item.get("severity", "info")),
            message=str(item.get("message", "")),
            location=str(item.get("location", "")),
            evidence_ids=tuple(item.get("evidence_ids") or ()),
            details=dict(item.get("details") or {}),
        )
        for item in items
    )


def _load_source_notes(items: Sequence[Mapping[str, Any] | str]) -> tuple[SourceNote, ...]:
    notes: list[SourceNote] = []
    for item in items:
        if isinstance(item, str):
            text = item.strip()
            evidence_ids = _evidence_ids(text)
            notes.append(
                SourceNote(
                    text=text,
                    evidence_ids=evidence_ids,
                    evidence_references=tuple(
                        EvidenceReference(
                            evidence_id=evidence_id,
                            source_note=text,
                        )
                        for evidence_id in evidence_ids
                    ),
                )
            )
            continue
        text = str(item.get("text") or item.get("note") or item.get("body") or "").strip()
        evidence_ids = tuple(item.get("evidence_ids") or _evidence_ids(text))
        extensions = _merged_extensions(item, {"text", "note", "body", "evidence_ids", "evidence_references", "extensions"})
        notes.append(
            SourceNote(
                text=text,
                evidence_ids=evidence_ids,
                evidence_references=tuple(
                    EvidenceReference(
                        evidence_id=str(reference.get("evidence_id", "")).strip(),
                        source_note=str(reference.get("source_note", text)).strip(),
                        claim=str(reference.get("claim", "")).strip(),
                        confidence=float(reference.get("confidence", 1.0)),
                        extensions=_merged_extensions(reference, {"evidence_id", "source_note", "slide_no", "slide_name", "claim", "confidence", "extensions"}),
                    )
                    for reference in item.get("evidence_references") or []
                ),
                extensions=extensions,
            )
        )
    return tuple(notes)


def _load_evidence_references(items: Sequence[Mapping[str, Any]]) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            evidence_id=str(item.get("evidence_id", "")).strip(),
            source_note=str(item.get("source_note", "")).strip(),
            slide_no=(int(item["slide_no"]) if item.get("slide_no") is not None else None),
            slide_name=str(item.get("slide_name", "")).strip(),
            claim=str(item.get("claim", "")).strip(),
            confidence=float(item.get("confidence", 1.0)),
            extensions=_merged_extensions(item, {"evidence_id", "source_note", "slide_no", "slide_name", "claim", "confidence", "extensions"}),
        )
        for item in items
    )


def _load_asset_briefs(items: Sequence[Mapping[str, Any]]) -> tuple[SpeculativeAssetBrief, ...]:
    briefs: list[SpeculativeAssetBrief] = []
    for item in items:
        briefs.append(
            SpeculativeAssetBrief(
                asset_type=str(item.get("asset_type", "")).strip(),
                brief=str(item.get("brief", "")).strip(),
                output_specification=str(item.get("output_specification", item.get("specification", ""))).strip(),
                evidence_ids=tuple(item.get("evidence_ids") or ()),
                source_notes=_load_source_notes(item.get("source_notes") or []),
                is_hypothesis=bool(item.get("is_hypothesis", True)),
                status=str(item.get("status", "draft")),
                confidence=float(item.get("confidence", 1.0)),
                extensions=_merged_extensions(
                    item,
                    {
                        "asset_type",
                        "brief",
                        "output_specification",
                        "specification",
                        "evidence_ids",
                        "source_notes",
                        "is_hypothesis",
                        "status",
                        "confidence",
                        "extensions",
                    },
                ),
            )
        )
    return tuple(briefs)


def _load_opportunity_card(data: Mapping[str, Any]) -> OpportunityCard:
    return OpportunityCard(
        card_id=str(data.get("card_id") or data.get("job_id") or "").strip(),
        workspace_id=str(data.get("workspace_id", "")).strip(),
        client_id=str(data.get("client_id", "")).strip(),
        company_name=str(data.get("company_name", "")).strip(),
        company_url=str(data.get("company_url", "")).strip(),
        market_category_context=str(data.get("market_category_context", "")).strip(),
        commercial_diagnosis=_load_commercial_diagnosis(data.get("commercial_diagnosis") or {}),
        growth_opportunity=_load_growth_opportunity(data.get("growth_opportunity") or {}),
        narrative_direction=_load_narrative_direction(data.get("narrative_direction") or {}),
        creative_treatment=_load_creative_treatment(data.get("creative_treatment") or {}),
        speculative_asset_briefs=_load_asset_briefs(data.get("speculative_asset_briefs") or []),
        outreach_draft=_load_outreach_draft(data.get("outreach_draft") or {}),
        source_notes=_load_source_notes(data.get("source_notes") or []),
        evidence_references=_load_evidence_references(data.get("evidence_references") or []),
        recommended_next_conversation=str(data.get("recommended_next_conversation", "")).strip(),
        disclaimer=str(data.get("disclaimer", "")).strip(),
        confidence=float(data.get("confidence", 1.0)),
        status=str(data.get("status", "draft")),
        validation_findings=_load_validation_findings(data.get("validation_findings") or []),
        lineage=_load_lineage(data.get("lineage") or {}),
        created_at=str(data.get("created_at", utc_now())),
        extensions=_merged_extensions(
            data,
            {
                "card_id",
                "workspace_id",
                "client_id",
                "company_name",
                "company_url",
                "market_category_context",
                "commercial_diagnosis",
                "growth_opportunity",
                "narrative_direction",
                "creative_treatment",
                "speculative_asset_briefs",
                "outreach_draft",
                "source_notes",
                "evidence_references",
                "recommended_next_conversation",
                "disclaimer",
                "confidence",
                "status",
                "validation_findings",
                "lineage",
                "created_at",
                "extensions",
            },
        ),
    )


def _load_commercial_diagnosis(data: Mapping[str, Any]) -> CommercialDiagnosis:
    return CommercialDiagnosis(
        statement=str(data.get("statement", "")).strip(),
        growth_constraint=str(data.get("growth_constraint", "")).strip(),
        evidence_ids=tuple(data.get("evidence_ids") or ()),
        source_notes=_load_source_notes(data.get("source_notes") or []),
        is_hypothesis=bool(data.get("is_hypothesis", False)),
        confidence=float(data.get("confidence", 1.0)),
        extensions=_merged_extensions(
            data,
            {"statement", "growth_constraint", "evidence_ids", "source_notes", "is_hypothesis", "confidence", "extensions"},
        ),
    )


def _load_growth_opportunity(data: Mapping[str, Any]) -> GrowthOpportunity:
    return GrowthOpportunity(
        statement=str(data.get("statement", "")).strip(),
        evidence_ids=tuple(data.get("evidence_ids") or ()),
        source_notes=_load_source_notes(data.get("source_notes") or []),
        is_hypothesis=bool(data.get("is_hypothesis", False)),
        confidence=float(data.get("confidence", 1.0)),
        extensions=_merged_extensions(
            data,
            {"statement", "evidence_ids", "source_notes", "is_hypothesis", "confidence", "extensions"},
        ),
    )


def _load_narrative_direction(data: Mapping[str, Any]) -> NarrativeDirection:
    return NarrativeDirection(
        statement=str(data.get("statement", "")).strip(),
        strategic_shift=str(data.get("strategic_shift", data.get("shift", ""))).strip(),
        evidence_ids=tuple(data.get("evidence_ids") or ()),
        source_notes=_load_source_notes(data.get("source_notes") or []),
        is_hypothesis=bool(data.get("is_hypothesis", False)),
        confidence=float(data.get("confidence", 1.0)),
        extensions=_merged_extensions(
            data,
            {"statement", "strategic_shift", "shift", "evidence_ids", "source_notes", "is_hypothesis", "confidence", "extensions"},
        ),
    )


def _load_creative_treatment(data: Mapping[str, Any]) -> CreativeTreatment:
    asset_briefs = data.get("asset_briefs") or data.get("briefs") or []
    return CreativeTreatment(
        creative_territory=str(data.get("creative_territory", data.get("territory", ""))).strip(),
        treatment=str(data.get("treatment", data.get("statement", ""))).strip(),
        asset_briefs=_load_asset_briefs(asset_briefs),
        evidence_ids=tuple(data.get("evidence_ids") or ()),
        source_notes=_load_source_notes(data.get("source_notes") or []),
        is_hypothesis=bool(data.get("is_hypothesis", True)),
        confidence=float(data.get("confidence", 1.0)),
        extensions=_merged_extensions(
            data,
            {
                "creative_territory",
                "territory",
                "treatment",
                "statement",
                "asset_briefs",
                "briefs",
                "evidence_ids",
                "source_notes",
                "is_hypothesis",
                "confidence",
                "extensions",
            },
        ),
    )


def _load_outreach_draft(data: Mapping[str, Any]) -> OutreachDraft:
    return OutreachDraft(
        subject=str(data.get("subject", "")).strip(),
        body=str(data.get("body", "")).strip(),
        call_to_action=str(data.get("call_to_action", data.get("cta", ""))).strip(),
        evidence_ids=tuple(data.get("evidence_ids") or ()),
        source_notes=_load_source_notes(data.get("source_notes") or []),
        is_hypothesis=bool(data.get("is_hypothesis", False)),
        confidence=float(data.get("confidence", 1.0)),
        extensions=_merged_extensions(
            data,
            {"subject", "body", "call_to_action", "cta", "evidence_ids", "source_notes", "is_hypothesis", "confidence", "extensions"},
        ),
    )


def _load_lineage(data: Mapping[str, Any]) -> OpportunityCardLineage:
    research_pack_artifact = data.get("research_pack_artifact")
    raw_response_artifact = data.get("raw_response_artifact")
    structured_artifact = data.get("structured_artifact")
    creative_treatment_artifact = data.get("creative_treatment_artifact")
    asset_briefs_artifact = data.get("speculative_asset_briefs_artifact")
    generated_asset_metadata_artifact = data.get("generated_asset_metadata_artifact")
    selected_asset_set_artifact = data.get("selected_asset_set_artifact")
    outreach_draft_artifact = data.get("outreach_draft_artifact")
    review_summary_artifact = data.get("review_summary_artifact")
    if raw_response_artifact is None:
        raise ValueError("opportunity lineage must contain a raw response artifact")
    return OpportunityCardLineage(
        research_pack_id=str(data.get("research_pack_id", "")),
        research_pack_checksum=str(data.get("research_pack_checksum", "")),
        research_pack_path=str(data.get("research_pack_path", "")),
        prompt_id=str(data.get("prompt_id", "")),
        prompt_version=int(data.get("prompt_version", 1)),
        prompt_checksum=str(data.get("prompt_checksum", "")),
        provider_id=str(data.get("provider_id", "")),
        model_id=str(data.get("model_id", "")),
        requested_provider_id=str(data.get("requested_provider_id", data.get("provider_id", ""))),
        requested_model_id=str(data.get("requested_model_id", data.get("model_id", ""))),
        routing_policy_id=str(data.get("routing_policy_id", "")),
        routing_policy_version=str(data.get("routing_policy_version", "")),
        raw_response_artifact=ArtifactRecord.from_dict(dict(raw_response_artifact)),
        structured_artifact=ArtifactRecord.from_dict(dict(structured_artifact)) if structured_artifact else None,
        research_pack_artifact=ArtifactRecord.from_dict(dict(research_pack_artifact)) if research_pack_artifact else None,
        creative_treatment_artifact=ArtifactRecord.from_dict(dict(creative_treatment_artifact)) if creative_treatment_artifact else None,
        speculative_asset_briefs_artifact=ArtifactRecord.from_dict(dict(asset_briefs_artifact)) if asset_briefs_artifact else None,
        generated_asset_metadata_artifact=ArtifactRecord.from_dict(dict(generated_asset_metadata_artifact)) if generated_asset_metadata_artifact else None,
        selected_asset_set_artifact=ArtifactRecord.from_dict(dict(selected_asset_set_artifact)) if selected_asset_set_artifact else None,
        outreach_draft_artifact=ArtifactRecord.from_dict(dict(outreach_draft_artifact)) if outreach_draft_artifact else None,
        review_summary_artifact=ArtifactRecord.from_dict(dict(review_summary_artifact)) if review_summary_artifact else None,
        evidence_pack_ids=tuple(data.get("evidence_pack_ids") or ()),
        artifact_lineage=tuple(data.get("artifact_lineage") or ()),
        extensions=_merged_extensions(
            data,
            {
                "research_pack_id",
                "research_pack_checksum",
                "research_pack_path",
                "prompt_id",
                "prompt_version",
                "prompt_checksum",
                "provider_id",
                "model_id",
                "requested_provider_id",
                "requested_model_id",
                "routing_policy_id",
                "routing_policy_version",
                "raw_response_artifact",
                "structured_artifact",
                "research_pack_artifact",
                "creative_treatment_artifact",
                "speculative_asset_briefs_artifact",
                "generated_asset_metadata_artifact",
                "selected_asset_set_artifact",
                "outreach_draft_artifact",
                "review_summary_artifact",
                "evidence_pack_ids",
                "artifact_lineage",
                "extensions",
            },
        ),
    )


def _research_job_from_request(request: OpportunityCardRequest) -> tuple[ResearchJob, EvidenceSource]:
    source = EvidenceSource(
        source_id=f"{request.job_id}--website",
        workspace_id=request.workspace_id,
        source_type="web",
        uri=request.company_url,
        title=request.company_name or request.company_domain,
        policy=EvidenceSourcePolicy(
            approved=True,
            allowed_domains=(request.company_domain,),
            allowed_schemes=("https",),
            max_bytes=DEFAULT_MAX_BYTES,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        ),
        metadata={
            "company_name": request.company_name,
            "company_url": request.company_url,
            "requested_by": request.requested_by,
            "purpose": "opportunity_card_lightweight_research",
        },
    )
    claims = (
        MaterialClaim(
            claim_id=f"{request.job_id}--lightweight-research",
            statement="Capture public website evidence, category context, proof points and obvious growth friction.",
            importance="contextual",
            metadata={
                "requested_by": request.requested_by,
                "purpose": "opportunity_card_lightweight_research",
            },
        ),
    )
    job = ResearchJob(
        job_id=f"{request.job_id}--research",
        workspace_id=request.workspace_id,
        query=f"{request.company_name or request.company_domain} lightweight prospect research",
        sources=(source,),
        claims=claims,
        missing_inputs=(),
        lineage=(request.job_id,),
    )
    return job, source


def _claim_supporting_notes(notes: Sequence[SourceNote], evidence_ids: Sequence[str]) -> tuple[SourceNote, ...]:
    if notes:
        return tuple(notes)
    if not evidence_ids:
        return ()
    return tuple(
        SourceNote(
            text=f"Evidence-backed claim supported by {evidence_id}.",
            evidence_ids=(evidence_id,),
            evidence_references=(EvidenceReference(evidence_id=evidence_id, source_note=f"Evidence-backed claim supported by {evidence_id}."),),
        )
        for evidence_id in evidence_ids
    )


def _merged_extensions(data: Mapping[str, Any], known_fields: Iterable[str]) -> dict[str, Any]:
    extensions = dict(data.get("extensions") or {})
    known = {str(field) for field in known_fields}
    for key, value in data.items():
        if key not in known:
            extensions[key] = value
    return extensions


def _evidence_ids(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    matches = re.findall(r"\bev_[A-Za-z0-9][A-Za-z0-9_-]*\b", str(text))
    return tuple(dict.fromkeys(match.strip() for match in matches if match.strip()))


def _confidence_from_findings(findings: Sequence[OpportunityCardValidationFinding]) -> float:
    score = 1.0
    for finding in findings:
        if finding.severity == "info":
            continue
        if finding.severity == "warning":
            score -= 0.02
        elif finding.severity == "error":
            score -= 0.12
        elif finding.severity == "blocking":
            score -= 0.3
    return max(0.0, round(score, 3))


def _extract_json_candidate(raw_response: str) -> str:
    text = str(raw_response or "").strip()
    if not text:
        raise ValueError("raw response is empty")
    if text.startswith("```"):
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            text = fence.group(1).strip()
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidate = text[start : end + 1].strip()
            json.loads(candidate)
            return candidate
        raise


@dataclass(frozen=True, slots=True)
class OpportunityCardPromptPackage:
    schema_version: int
    job_id: str
    run_id: str
    stage_id: str
    instructions: str
    input_artifacts: tuple[dict[str, Any], ...]
    memory_records: tuple[dict[str, Any], ...]
    confidence_scorecard: dict[str, Any] | None
    context: Mapping[str, Any]
    expected_output_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FakeOpportunityCardEngine:
    name = "fake_opportunity_card_engine"

    def __init__(
        self,
        *,
        response_factory: Callable[
            [OpportunityCardRequest, PromptVersion, EvidencePack, ArtifactRecord],
            Mapping[str, Any] | str | OpportunityCardEngineResponse,
        ]
        | None = None,
        provider_id: str = "fake_opportunity_card_provider",
        model_id: str = "fake-opportunity-card-v1",
        routing_policy_id: str = "opportunity_card_fallback",
        routing_policy_version: str = "1",
    ) -> None:
        self.response_factory = response_factory
        self.provider_id = provider_id
        self.model_id = model_id
        self.routing_policy_id = routing_policy_id
        self.routing_policy_version = routing_policy_version

    def generate(
        self,
        request: OpportunityCardRequest,
        prompt: PromptVersion,
        research_pack: EvidencePack,
        research_pack_artifact: ArtifactRecord,
    ) -> OpportunityCardEngineResponse:
        result = self.response_factory(request, prompt, research_pack, research_pack_artifact) if self.response_factory else self._default_payload(request, prompt, research_pack)
        if isinstance(result, OpportunityCardEngineResponse):
            return result
        if isinstance(result, Mapping):
            raw_response = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        else:
            raw_response = str(result)
        return OpportunityCardEngineResponse(
            raw_response=raw_response,
            provider_id=self.provider_id,
            model_id=self.model_id,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_checksum=prompt.checksum,
            requested_provider_id=self.provider_id,
            requested_model_id=self.model_id,
            routing_policy_id=self.routing_policy_id,
            routing_policy_version=self.routing_policy_version,
            provider_metadata={
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "routing_policy_id": self.routing_policy_id,
                "routing_policy_version": self.routing_policy_version,
            },
        )

    def _default_payload(
        self,
        request: OpportunityCardRequest,
        prompt: PromptVersion,
        research_pack: EvidencePack,
    ) -> Mapping[str, Any]:
        evidence_ids = [
            str(record.get("evidence_id", "")).strip()
            for record in research_pack.records
            if str(record.get("evidence_id", "")).strip()
        ]
        primary = evidence_ids[:2] or [f"ev_{sha256_hex(request.company_url)[:12]}"]
        secondary = evidence_ids[2:4] or primary[:1]
        tertiary = evidence_ids[4:6] or primary[:1]
        market_category_context = f"Public evidence suggests {request.company_name or request.company_domain} operates in a crowded, trust-sensitive category."
        diagnosis = {
            "statement": f"{request.company_name or request.company_domain} appears to be competing on familiarity rather than a sharper commercial promise.",
            "growth_constraint": "The offer is not yet framed around a clear conversion reason that a buyer can repeat.",
            "evidence_ids": primary,
            "source_notes": [
                {
                    "text": f"{request.company_name or request.company_domain} homepage evidence supports the category read.",
                    "evidence_ids": primary,
                    "evidence_references": [
                        {
                            "evidence_id": primary[0],
                            "source_note": f"{request.company_name or request.company_domain} homepage evidence supports the category read.",
                            "claim": "The public website establishes the current proposition.",
                            "confidence": 0.92,
                        }
                    ],
                }
            ],
            "is_hypothesis": False,
            "confidence": 0.84,
        }
        opportunity = {
            "statement": "Sharpen the promise around one commercially legible problem and one repeatable proof point.",
            "evidence_ids": secondary,
            "source_notes": [
                {
                    "text": "Observed proof points can be translated into a narrower, more memorable value proposition.",
                    "evidence_ids": secondary,
                }
            ],
            "is_hypothesis": False,
            "confidence": 0.8,
        }
        narrative_direction = {
            "statement": "Move from descriptive category language to a focused, outcome-led story that a buyer can repeat.",
            "strategic_shift": "From generic category description to a single memorable commercial reason to engage.",
            "evidence_ids": tertiary,
            "source_notes": [
                {
                    "text": "The research pack indicates room for a tighter story architecture.",
                    "evidence_ids": tertiary,
                }
            ],
            "is_hypothesis": False,
            "confidence": 0.78,
        }
        creative_treatment = {
            "creative_territory": f"{request.company_name or request.company_domain} as the brand that turns routine into a more deliberate choice.",
            "treatment": "Translate the strategy into a clean, premium treatment with one hero idea, one repeated proof shape, and one crisp conversion path.",
            "asset_briefs": [
                {
                    "asset_type": "hero_campaign_image",
                    "brief": "Create a premium hero visual that frames the single commercial promise.",
                    "output_specification": "Editorial hero image with one focal message and one proof cue.",
                    "evidence_ids": primary,
                    "is_hypothesis": True,
                },
                {
                    "asset_type": "short_video_concept",
                    "brief": "Create a short social-video concept that repeats the promise and proof.",
                    "output_specification": "6-10 second concept with one message arc and a clear ending CTA.",
                    "evidence_ids": secondary,
                    "is_hypothesis": True,
                },
                {
                    "asset_type": "social_asset_concept",
                    "brief": "Create a social concept that can travel with the same promise across channels.",
                    "output_specification": "Square or portrait social concept with concise copy and proof-led framing.",
                    "evidence_ids": tertiary,
                    "is_hypothesis": True,
                },
            ],
            "evidence_ids": primary,
            "source_notes": [
                {
                    "text": "Creative direction should remain speculative until Matt approves outreach use.",
                    "evidence_ids": primary,
                }
            ],
            "is_hypothesis": True,
            "confidence": 0.73,
        }
        briefs = creative_treatment["asset_briefs"]
        outreach = {
            "subject": f"An idea for {request.company_name or request.company_domain}",
            "body": f"I’ve mapped a sharper commercial angle for {request.company_name or request.company_domain} and a speculative creative direction worth discussing.",
            "call_to_action": "Would you like to review the Opportunity Card?",
            "evidence_ids": primary,
            "source_notes": [
                {
                    "text": "Outreach should invite a conversation rather than overclaim certainty.",
                    "evidence_ids": primary,
                }
            ],
            "is_hypothesis": False,
            "confidence": 0.76,
        }
        return {
            "company_name": request.company_name or request.company_domain,
            "company_url": request.company_url,
            "market_category_context": market_category_context,
            "commercial_diagnosis": diagnosis,
            "growth_opportunity": opportunity,
            "narrative_direction": narrative_direction,
            "creative_treatment": creative_treatment,
            "speculative_asset_briefs": briefs,
            "outreach_draft": outreach,
            "source_notes": [
                {
                    "text": f"{request.company_name or request.company_domain} is the prospect being reviewed.",
                    "evidence_ids": primary,
                },
                {
                    "text": "The opportunity is speculative and uncommissioned until Matt approves it.",
                    "evidence_ids": secondary,
                },
            ],
            "evidence_references": [
                {
                    "evidence_id": primary[0],
                    "source_note": f"{request.company_name or request.company_domain} homepage evidence supports the category read.",
                    "claim": "Website evidence anchors the diagnosis.",
                    "confidence": 0.91,
                }
            ],
            "recommended_next_conversation": "Ask Matt whether this should become a client conversation or a revised prospecting angle.",
            "disclaimer": "This work is speculative and uncommissioned.",
            "confidence": 0.82,
            "extensions": {
                "research_pack_id": research_pack.pack_id,
                "research_pack_lineage": list(research_pack.lineage),
                "prompt_id": prompt.prompt_id,
                "prompt_checksum": prompt.checksum,
            },
        }


class ClaudeOpportunityCardEngine:
    name = "claude_opportunity_card_engine"

    def __init__(
        self,
        provider: Any,
        *,
        provider_id: str = "claude",
        model_id: str = "claude-sonnet-4-5",
        routing_policy_id: str = "claude_opportunity_card",
        routing_policy_version: str = "1",
    ) -> None:
        self.provider = provider
        self.provider_id = provider_id
        self.model_id = model_id
        self.routing_policy_id = routing_policy_id
        self.routing_policy_version = routing_policy_version

    def generate(
        self,
        request: OpportunityCardRequest,
        prompt: PromptVersion,
        research_pack: EvidencePack,
        research_pack_artifact: ArtifactRecord,
    ) -> OpportunityCardEngineResponse:
        package = OpportunityCardPromptPackage(
            schema_version=1,
            job_id=request.job_id,
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            instructions="\n\n".join(
                [
                    prompt.content,
                    "Use the approved research pack and produce the Opportunity Card JSON object.",
                ]
            ),
            input_artifacts=(research_pack_artifact.to_dict(),),
            memory_records=(),
            confidence_scorecard=None,
            context={
                "request": request.to_dict(),
                "research_pack": research_pack.as_dict(),
                "strategic_principles": self._strategic_principles(),
            },
            expected_output_type=DEFAULT_STRUCTURED_ARTIFACT_TYPE,
        )
        response = self.provider.generate(package)
        raw_response = getattr(response, "content", "")
        metadata = dict(getattr(response, "metadata", None) or {})
        actual_provider = str(metadata.get("provider_id") or self.provider_id).strip()
        actual_model = str(metadata.get("model_id") or self.model_id).strip()
        if not raw_response.strip():
            raise OpportunityCardBlockedError("Claude returned an empty Opportunity Card response.")
        return OpportunityCardEngineResponse(
            raw_response=raw_response,
            provider_id=actual_provider,
            model_id=actual_model,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_checksum=prompt.checksum,
            requested_provider_id=self.provider_id,
            requested_model_id=self.model_id,
            routing_policy_id=self.routing_policy_id,
            routing_policy_version=self.routing_policy_version,
            provider_metadata=metadata,
        )

    def _strategic_principles(self) -> dict[str, Any]:
        if not DEFAULT_STRATEGIC_PRINCIPLES_PATH.is_file():
            return {}
        content = DEFAULT_STRATEGIC_PRINCIPLES_PATH.read_text(encoding="utf-8")
        return {
            "source_path": str(DEFAULT_STRATEGIC_PRINCIPLES_PATH),
            "checksum": sha256_hex(content),
            "content": content,
        }


class OpportunityCardService:
    def __init__(
        self,
        *,
        artifact_catalog: FileArtifactCatalog,
        prompt_registry: FilePromptRegistry,
        research_engine: ResearchEngine | None = None,
        engine: OpportunityCardEngine | None = None,
        asset_provider: SpeculativeAssetProvider | None = None,
        store: FileOpportunityCardStore | None = None,
        prompt_id: str = DEFAULT_PROMPT_ID,
        prompt_source_path: Path = DEFAULT_PROMPT_SOURCE_PATH,
    ) -> None:
        self.artifact_catalog = artifact_catalog
        self.prompt_registry = prompt_registry
        self.research_engine = research_engine or ResearchEngine(Path(artifact_catalog.root).parent)
        self.engine = engine or FakeOpportunityCardEngine()
        self.asset_provider = asset_provider or FakeSpeculativeAssetProvider()
        self.store = store or FileOpportunityCardStore(Path(self.artifact_catalog.root).parent / "opportunity_cards")
        self.prompt_id = prompt_id
        self.prompt_source_path = Path(prompt_source_path)

    def for_runtime(self, runtime: Any) -> "OpportunityCardService":
        return OpportunityCardService(
            artifact_catalog=runtime.artifact_catalog,
            prompt_registry=runtime.prompt_registry,
            research_engine=self.research_engine,
            engine=self.engine,
            asset_provider=self.asset_provider,
            store=FileOpportunityCardStore(Path(runtime.artifact_catalog.root).parent / "opportunity_cards"),
            prompt_id=self.prompt_id,
            prompt_source_path=self.prompt_source_path,
        )

    def generate(self, request: OpportunityCardRequest) -> OpportunityCardVersionRecord:
        research_job, source = _research_job_from_request(request)
        try:
            research_run = self.research_engine.run(research_job)
        except Exception as exc:  # noqa: BLE001
            raise OpportunityCardBlockedError(
                f"Opportunity Card research could not be completed: {exc}"
            ) from exc
        if research_run.status == "blocked" or not research_run.evidence_pack.records:
            raise OpportunityCardBlockedError(
                "Opportunity Card research could not be completed for the supplied company URL."
            )

        prompt = self._load_prompt_version()
        research_pack_artifact = self.artifact_catalog.register(
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_RESEARCH_ARTIFACT_TYPE,
            content=json.dumps(research_run.evidence_pack.as_dict(), indent=2, sort_keys=True, default=str) + "\n",
            parent_artifact_ids=(),
            producer="research_engine@1",
            metadata={
                "request": request.to_dict(),
                "source": asdict(source),
                "research_pack_id": research_run.evidence_pack.pack_id,
                "research_pack_checksum": sha256_hex(_stable_json(research_run.evidence_pack.as_dict())),
                "pack_path": research_run.pack_path,
                "job_status": research_run.status,
            },
        )
        try:
            response = self.engine.generate(request, prompt, research_run.evidence_pack, research_pack_artifact)
        except Exception as exc:  # noqa: BLE001
            raise OpportunityCardBlockedError(f"Opportunity Card engine failed: {exc}") from exc
        raw_response_artifact = self.artifact_catalog.register(
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_RAW_ARTIFACT_TYPE,
            content=response.raw_response,
            parent_artifact_ids=(research_pack_artifact.artifact.artifact_id,),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata=self._response_metadata(
                request=request,
                prompt=prompt,
                response=response,
                research_run=research_run,
                research_pack_artifact=research_pack_artifact,
            ),
        )
        preliminary_card, parse_findings = self._parse_response(
            request=request,
            prompt=prompt,
            response=response,
            research_run=research_run,
            research_pack_artifact=research_pack_artifact,
            raw_response_artifact=raw_response_artifact,
        )
        asset_set = self._generate_speculative_assets(
            request=request,
            card=preliminary_card,
            research_run=research_run,
            prompt=prompt,
        )
        validation_findings = tuple(parse_findings) + self._validate_card(preliminary_card, research_run, asset_set)
        status = self._card_status(validation_findings, asset_set)
        card = replace(
            preliminary_card,
            status=status,
            validation_findings=validation_findings,
            confidence=_confidence_from_findings(validation_findings),
        )
        creative_treatment_artifact = self.artifact_catalog.register(
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_CREATIVE_ARTIFACT_TYPE,
            content=json.dumps(card.creative_treatment.to_dict(), indent=2, sort_keys=True, default=str) + "\n",
            parent_artifact_ids=(raw_response_artifact.artifact.artifact_id,),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata=self._response_metadata(
                request=request,
                prompt=prompt,
                response=response,
                research_run=research_run,
                research_pack_artifact=research_pack_artifact,
            ),
        )
        speculative_asset_briefs_artifact = self.artifact_catalog.register(
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_ASSET_BRIEF_ARTIFACT_TYPE,
            content=json.dumps([brief.to_dict() for brief in card.speculative_asset_briefs], indent=2, sort_keys=True, default=str) + "\n",
            parent_artifact_ids=(creative_treatment_artifact.artifact.artifact_id,),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata=self._response_metadata(
                request=request,
                prompt=prompt,
                response=response,
                research_run=research_run,
                research_pack_artifact=research_pack_artifact,
            ),
        )
        generated_asset_metadata_artifact = self.artifact_catalog.register(
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_ASSET_METADATA_ARTIFACT_TYPE,
            content=json.dumps(asset_set.to_dict(), indent=2, sort_keys=True, default=str) + "\n",
            parent_artifact_ids=(speculative_asset_briefs_artifact.artifact.artifact_id,),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata=self._response_metadata(
                request=request,
                prompt=prompt,
                response=response,
                research_run=research_run,
                research_pack_artifact=research_pack_artifact,
            ),
        )
        selected_asset_set_artifact = self.artifact_catalog.register(
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_SELECTED_ASSET_ARTIFACT_TYPE,
            content=json.dumps(
                {
                    "selected_results": [result.to_dict() for result in asset_set.selected_results],
                    "approval_required": asset_set.approval_required,
                    "status": asset_set.status,
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
            + "\n",
            parent_artifact_ids=(generated_asset_metadata_artifact.artifact.artifact_id,),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata=self._response_metadata(
                request=request,
                prompt=prompt,
                response=response,
                research_run=research_run,
                research_pack_artifact=research_pack_artifact,
            ),
        )
        outreach_draft_artifact = self.artifact_catalog.register(
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_OUTREACH_ARTIFACT_TYPE,
            content=json.dumps(card.outreach_draft.to_dict(), indent=2, sort_keys=True, default=str) + "\n",
            parent_artifact_ids=(selected_asset_set_artifact.artifact.artifact_id,),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata=self._response_metadata(
                request=request,
                prompt=prompt,
                response=response,
                research_run=research_run,
                research_pack_artifact=research_pack_artifact,
            ),
        )
        review_summary_artifact = self.artifact_catalog.register(
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_REVIEW_ARTIFACT_TYPE,
            content=self._render_review_summary(card, research_run, asset_set) + "\n",
            parent_artifact_ids=(outreach_draft_artifact.artifact.artifact_id,),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata=self._response_metadata(
                request=request,
                prompt=prompt,
                response=response,
                research_run=research_run,
                research_pack_artifact=research_pack_artifact,
            ),
        )
        final_card = replace(
            card,
            lineage=replace(
                card.lineage,
                research_pack_id=research_run.evidence_pack.pack_id,
                research_pack_checksum=sha256_hex(_stable_json(research_run.evidence_pack.as_dict())),
                research_pack_path=research_run.pack_path,
                prompt_id=prompt.prompt_id,
                prompt_version=prompt.version,
                prompt_checksum=prompt.checksum,
                provider_id=response.provider_id,
                model_id=response.model_id,
                requested_provider_id=response.requested_provider_id or response.provider_id,
                requested_model_id=response.requested_model_id or response.model_id,
                routing_policy_id=response.routing_policy_id,
                routing_policy_version=response.routing_policy_version,
                raw_response_artifact=raw_response_artifact,
                structured_artifact=None,
                research_pack_artifact=research_pack_artifact,
                creative_treatment_artifact=creative_treatment_artifact,
                speculative_asset_briefs_artifact=speculative_asset_briefs_artifact,
                generated_asset_metadata_artifact=generated_asset_metadata_artifact,
                selected_asset_set_artifact=selected_asset_set_artifact,
                outreach_draft_artifact=outreach_draft_artifact,
                review_summary_artifact=review_summary_artifact,
                evidence_pack_ids=(research_run.evidence_pack.pack_id,),
                artifact_lineage=(
                    research_pack_artifact.artifact.artifact_id,
                    raw_response_artifact.artifact.artifact_id,
                    creative_treatment_artifact.artifact.artifact_id,
                    speculative_asset_briefs_artifact.artifact.artifact_id,
                    generated_asset_metadata_artifact.artifact.artifact_id,
                    selected_asset_set_artifact.artifact.artifact_id,
                    outreach_draft_artifact.artifact.artifact_id,
                    review_summary_artifact.artifact.artifact_id,
                ),
            ),
        )
        structured_artifact = self.artifact_catalog.register(
            run_id=request.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_STRUCTURED_ARTIFACT_TYPE,
            content=json.dumps(final_card.to_dict(), indent=2, sort_keys=True, default=str) + "\n",
            parent_artifact_ids=(raw_response_artifact.artifact.artifact_id,),
            producer=f"{response.provider_id}@{response.model_id}",
            metadata=self._response_metadata(
                request=request,
                prompt=prompt,
                response=response,
                research_run=research_run,
                research_pack_artifact=research_pack_artifact,
            ),
        )
        final_card = replace(
            final_card,
            lineage=replace(final_card.lineage, structured_artifact=structured_artifact),
        )
        previous = self.store.latest(request.workspace_id, request.client_id, request.job_id)
        change_summary = self._summarise_changes(
            previous=previous,
            request=request,
            prompt=prompt,
            response=response,
            research_run=research_run,
            card=final_card,
            structured_artifact=structured_artifact,
            raw_response_artifact=raw_response_artifact,
            research_pack_artifact=research_pack_artifact,
        )
        record = OpportunityCardVersionRecord(
            job_id=request.job_id,
            workspace_id=request.workspace_id,
            client_id=request.client_id,
            version=(previous.version + 1 if previous else 1),
            request=request,
            research_pack_id=research_run.evidence_pack.pack_id,
            input_checksum=request.request_checksum(),
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_checksum=prompt.checksum,
            provider_id=response.provider_id,
            model_id=response.model_id,
            requested_provider_id=response.requested_provider_id,
            requested_model_id=response.requested_model_id,
            routing_policy_id=response.routing_policy_id,
            routing_policy_version=response.routing_policy_version,
            opportunity_card=final_card,
            research_pack_artifact=research_pack_artifact,
            raw_response_artifact=raw_response_artifact,
            structured_artifact=structured_artifact,
            creative_treatment_artifact=creative_treatment_artifact,
            speculative_asset_briefs_artifact=speculative_asset_briefs_artifact,
            generated_asset_metadata_artifact=generated_asset_metadata_artifact,
            selected_asset_set_artifact=selected_asset_set_artifact,
            outreach_draft_artifact=outreach_draft_artifact,
            review_summary_artifact=review_summary_artifact,
            validation_findings=final_card.validation_findings,
            change_summary=change_summary,
            previous_version=(previous.version if previous else None),
            artifact_lineage=tuple(dict.fromkeys((*final_card.lineage.artifact_lineage, structured_artifact.artifact.artifact_id))),
            approval_history=(),
            status=final_card.status,
        )
        self.store.save(record)
        return record

    def latest(self, workspace_id: str, client_id: str, job_id: str) -> OpportunityCardVersionRecord | None:
        return self.store.latest(workspace_id, client_id, job_id)

    def get(
        self,
        workspace_id: str,
        client_id: str,
        job_id: str,
        version: int | None = None,
    ) -> OpportunityCardVersionRecord:
        if version is None:
            latest = self.store.latest(workspace_id, client_id, job_id)
            if latest is None:
                raise KeyError(f"opportunity card not found: {workspace_id}/{client_id}/{job_id}")
            return latest
        return self.store.get(workspace_id, client_id, job_id, version)

    def review(self, job_id: str, *, workspace_id: str | None = None, client_id: str | None = None) -> OpportunityCardVersionRecord:
        return self._resolve_record(job_id, workspace_id=workspace_id, client_id=client_id)

    def approve(
        self,
        job_id: str,
        *,
        reviewer_id: str = "Matt",
        rationale: str = "",
        workspace_id: str | None = None,
        client_id: str | None = None,
    ) -> OpportunityCardVersionRecord:
        record = self._resolve_record(job_id, workspace_id=workspace_id, client_id=client_id)
        return self._transition(record, "approved", reviewer_id=reviewer_id, rationale=rationale)

    def revise(
        self,
        job_id: str,
        instruction: str,
        *,
        reviewer_id: str = "Matt",
        workspace_id: str | None = None,
        client_id: str | None = None,
    ) -> OpportunityCardVersionRecord:
        record = self._resolve_record(job_id, workspace_id=workspace_id, client_id=client_id)
        return self._transition(record, "revision_requested", reviewer_id=reviewer_id, rationale=instruction)

    def _transition(
        self,
        previous: OpportunityCardVersionRecord,
        status: str,
        *,
        reviewer_id: str,
        rationale: str,
    ) -> OpportunityCardVersionRecord:
        approval_event = {
            "decision": status,
            "reviewer_id": reviewer_id,
            "rationale": rationale,
            "created_at": utc_now(),
        }
        card = replace(
            previous.opportunity_card,
            status=status,
            lineage=replace(
                previous.opportunity_card.lineage,
                structured_artifact=None,
                review_summary_artifact=None,
            ),
        )
        prompt = self._load_prompt_version()
        structured_artifact = self.artifact_catalog.register(
            run_id=previous.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_STRUCTURED_ARTIFACT_TYPE,
            content=json.dumps(card.to_dict(), indent=2, sort_keys=True, default=str) + "\n",
            parent_artifact_ids=(previous.raw_response_artifact.artifact.artifact_id,),
            producer=f"{previous.provider_id}@{previous.model_id}",
            metadata={
                "request": previous.request.to_dict(),
                "prompt_id": prompt.prompt_id,
                "prompt_version": prompt.version,
                "prompt_checksum": prompt.checksum,
                "provider_id": previous.provider_id,
                "model_id": previous.model_id,
                "requested_provider_id": previous.requested_provider_id,
                "requested_model_id": previous.requested_model_id,
                "routing_policy_id": previous.routing_policy_id,
                "routing_policy_version": previous.routing_policy_version,
                "research_pack_id": previous.research_pack_id,
                "research_pack_checksum": previous.research_pack_artifact.artifact.checksum,
                "research_pack_path": previous.research_pack_artifact.artifact.location,
                "research_pack_artifact": previous.research_pack_artifact.to_dict(),
            },
        )
        review_summary_artifact = self.artifact_catalog.register(
            run_id=previous.job_id,
            stage_id=DEFAULT_STAGE_ID,
            artifact_type=DEFAULT_REVIEW_ARTIFACT_TYPE,
            content="\n".join(
                [
                    "# Opportunity Card Review Update",
                    f"- Company: {previous.opportunity_card.company_name}",
                    f"- Job ID: {previous.job_id}",
                    f"- Status: {status}",
                    f"- Reviewer: {reviewer_id}",
                    f"- Rationale: {rationale or 'No rationale provided.'}",
                ]
            )
            + "\n",
            parent_artifact_ids=(structured_artifact.artifact.artifact_id,),
            producer=f"{previous.provider_id}@{previous.model_id}",
            metadata={
                "request": previous.request.to_dict(),
                "prompt_id": prompt.prompt_id,
                "prompt_version": prompt.version,
                "prompt_checksum": prompt.checksum,
                "provider_id": previous.provider_id,
                "model_id": previous.model_id,
                "requested_provider_id": previous.requested_provider_id,
                "requested_model_id": previous.requested_model_id,
                "routing_policy_id": previous.routing_policy_id,
                "routing_policy_version": previous.routing_policy_version,
                "reviewer_id": reviewer_id,
                "rationale": rationale,
            },
        )
        final_card = replace(
            card,
            lineage=replace(
                card.lineage,
                research_pack_id=previous.research_pack_id,
                research_pack_checksum=previous.research_pack_artifact.artifact.checksum,
                research_pack_path=previous.research_pack_artifact.artifact.location,
                prompt_id=prompt.prompt_id,
                prompt_version=prompt.version,
                prompt_checksum=prompt.checksum,
                provider_id=previous.provider_id,
                model_id=previous.model_id,
                requested_provider_id=previous.requested_provider_id,
                requested_model_id=previous.requested_model_id,
                routing_policy_id=previous.routing_policy_id,
                routing_policy_version=previous.routing_policy_version,
                structured_artifact=structured_artifact,
                review_summary_artifact=review_summary_artifact,
                artifact_lineage=tuple(
                    dict.fromkeys(
                        (
                            *previous.artifact_lineage,
                            structured_artifact.artifact.artifact_id,
                            review_summary_artifact.artifact.artifact_id,
                        )
                    )
                ),
            ),
        )
        change_summary = self._summarise_changes(
            previous=previous,
            request=previous.request,
            prompt=prompt,
            response=OpportunityCardEngineResponse(
                raw_response=Path(previous.raw_response_artifact.artifact.location).read_text(encoding="utf-8"),
                provider_id=previous.provider_id,
                model_id=previous.model_id,
                prompt_id=previous.prompt_id,
                prompt_version=previous.prompt_version,
                prompt_checksum=previous.prompt_checksum,
                requested_provider_id=previous.requested_provider_id,
                requested_model_id=previous.requested_model_id,
                routing_policy_id=previous.routing_policy_id,
                routing_policy_version=previous.routing_policy_version,
                provider_metadata={},
            ),
            research_run=ResearchRun(
                job=_research_job_from_request(previous.request)[0],
                evidence_pack=_load_evidence_pack_from_artifact(previous.research_pack_artifact),
                pack_path=previous.research_pack_artifact.artifact.location,
                status="complete",
                blockers=[],
                warnings=[],
                deduplicated_record_count=len(previous.opportunity_card.evidence_references),
            ),
            card=final_card,
            structured_artifact=structured_artifact,
            raw_response_artifact=previous.raw_response_artifact,
            research_pack_artifact=previous.research_pack_artifact,
        )
        record = OpportunityCardVersionRecord(
            job_id=previous.job_id,
            workspace_id=previous.workspace_id,
            client_id=previous.client_id,
            version=previous.version + 1,
            request=previous.request,
            research_pack_id=previous.research_pack_id,
            input_checksum=previous.input_checksum,
            prompt_id=previous.prompt_id,
            prompt_version=previous.prompt_version,
            prompt_checksum=previous.prompt_checksum,
            provider_id=previous.provider_id,
            model_id=previous.model_id,
            requested_provider_id=previous.requested_provider_id,
            requested_model_id=previous.requested_model_id,
            routing_policy_id=previous.routing_policy_id,
            routing_policy_version=previous.routing_policy_version,
            opportunity_card=final_card,
            research_pack_artifact=previous.research_pack_artifact,
            raw_response_artifact=previous.raw_response_artifact,
            structured_artifact=structured_artifact,
            creative_treatment_artifact=previous.creative_treatment_artifact,
            speculative_asset_briefs_artifact=previous.speculative_asset_briefs_artifact,
            generated_asset_metadata_artifact=previous.generated_asset_metadata_artifact,
            selected_asset_set_artifact=previous.selected_asset_set_artifact,
            outreach_draft_artifact=previous.outreach_draft_artifact,
            review_summary_artifact=review_summary_artifact,
            validation_findings=final_card.validation_findings,
            change_summary=change_summary,
            previous_version=previous.version,
            artifact_lineage=tuple(dict.fromkeys((*previous.artifact_lineage, structured_artifact.artifact.artifact_id, review_summary_artifact.artifact.artifact_id))),
            approval_history=tuple((*previous.approval_history, approval_event)),
            status=status,
        )
        self.store.save(record)
        return record

    def _resolve_record(
        self,
        job_id: str,
        *,
        workspace_id: str | None = None,
        client_id: str | None = None,
    ) -> OpportunityCardVersionRecord:
        if workspace_id and client_id:
            latest = self.store.latest(workspace_id, client_id, job_id)
            if latest is None:
                raise OpportunityCardBlockedError(f"Opportunity Card not found: {workspace_id}/{client_id}/{job_id}")
            return latest
        latest = self.store.latest_by_job(job_id)
        if latest is None:
            raise OpportunityCardBlockedError(f"Opportunity Card not found: {job_id}")
        return latest

    def _parse_response(
        self,
        *,
        request: OpportunityCardRequest,
        prompt: PromptVersion,
        response: OpportunityCardEngineResponse,
        research_run: ResearchRun,
        research_pack_artifact: ArtifactRecord,
        raw_response_artifact: ArtifactRecord,
    ) -> tuple[OpportunityCard, tuple[OpportunityCardValidationFinding, ...]]:
        try:
            raw_payload = json.loads(_extract_json_candidate(response.raw_response))
        except json.JSONDecodeError as exc:
            raise OpportunityCardValidationError("Opportunity Card response is not valid JSON.") from exc
        if not isinstance(raw_payload, Mapping):
            raise OpportunityCardValidationError("Opportunity Card response must be a JSON object.")
        payload = dict(raw_payload)
        lineage = OpportunityCardLineage(
            research_pack_id=research_run.evidence_pack.pack_id,
            research_pack_checksum=sha256_hex(_stable_json(research_run.evidence_pack.as_dict())),
            research_pack_path=research_run.pack_path,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompt_checksum=prompt.checksum,
            provider_id=response.provider_id,
            model_id=response.model_id,
            requested_provider_id=response.requested_provider_id or response.provider_id,
            requested_model_id=response.requested_model_id or response.model_id,
            routing_policy_id=response.routing_policy_id,
            routing_policy_version=response.routing_policy_version,
            raw_response_artifact=raw_response_artifact,
            research_pack_artifact=research_pack_artifact,
            evidence_pack_ids=(research_run.evidence_pack.pack_id,),
            artifact_lineage=(research_pack_artifact.artifact.artifact_id, raw_response_artifact.artifact.artifact_id),
        )
        payload["card_id"] = str(payload.get("card_id") or request.job_id)
        payload["workspace_id"] = request.workspace_id
        payload["client_id"] = request.client_id
        payload["company_name"] = str(payload.get("company_name") or request.company_name or request.company_domain)
        payload["company_url"] = request.company_url
        payload["lineage"] = lineage.to_dict()
        payload.setdefault("status", "draft")
        card = _load_opportunity_card(payload)
        findings = tuple(card.validation_findings)
        return card, findings

    def _generate_speculative_assets(
        self,
        *,
        request: OpportunityCardRequest,
        card: OpportunityCard,
        research_run: ResearchRun,
        prompt: PromptVersion,
    ) -> SpeculativeAssetSet:
        policy = AssetGenerationPolicy()
        briefs = card.speculative_asset_briefs[:4]
        if len(briefs) < 2:
            raise OpportunityCardValidationError("Opportunity Card must include at least two speculative asset briefs.")
        candidate_results: list[SpeculativeAssetResult] = []
        for attempt_no, brief in enumerate(briefs, start=1):
            asset_request = SpeculativeAssetRequest(
                job_id=request.job_id,
                workspace_id=request.workspace_id,
                client_id=request.client_id,
                card_id=card.card_id,
                creative_territory=card.creative_treatment.creative_territory,
                asset_type=brief.asset_type,
                prompt=f"{brief.brief}\n\nOutput specification:\n{brief.output_specification}",
                output_specification=brief.output_specification,
                attempt_no=attempt_no,
                revision_round=0,
                requested_by=request.requested_by,
                metadata={
                    "request": request.to_dict(),
                    "evidence_ids": list(brief.evidence_ids),
                    "source_notes": [note.to_dict() for note in brief.source_notes],
                    "prompt_id": prompt.prompt_id,
                    "prompt_checksum": prompt.checksum,
                    "research_pack_id": research_run.evidence_pack.pack_id,
                },
            )
            try:
                result = self.asset_provider.submit(asset_request)
            except Exception as exc:  # noqa: BLE001
                raise OpportunityCardBlockedError(f"Speculative asset generation failed: {exc}") from exc
            candidate_results.append(result)
        selected_results = tuple(
            result for result in candidate_results[: policy.max_selected_outputs] if result.status in {"generated", "completed", "approved"}
        )
        rejected_results = tuple(result for result in candidate_results if result not in selected_results)
        approval_required = policy.external_use_requires_approval
        status = "awaiting_approval" if selected_results else "assets_pending"
        return SpeculativeAssetSet(
            job_id=request.job_id,
            workspace_id=request.workspace_id,
            client_id=request.client_id,
            card_id=card.card_id,
            policy=policy,
            candidate_results=tuple(candidate_results),
            selected_results=selected_results,
            rejected_results=rejected_results,
            approval_required=approval_required,
            status=status,
            extensions={
                "research_pack_id": research_run.evidence_pack.pack_id,
                "prompt_id": prompt.prompt_id,
                "request": request.to_dict(),
            },
        )

    def _validate_card(
        self,
        card: OpportunityCard,
        research_run: ResearchRun,
        asset_set: SpeculativeAssetSet,
    ) -> tuple[OpportunityCardValidationFinding, ...]:
        findings: list[OpportunityCardValidationFinding] = []
        records_by_id = {record["evidence_id"]: record for record in research_run.evidence_pack.records}
        aliases = dict(research_run.evidence_pack.evidence_aliases)
        canonical_ids = set(records_by_id)
        if len(card.speculative_asset_briefs) < 2 or len(card.speculative_asset_briefs) > 4:
            findings.append(
                OpportunityCardValidationFinding(
                    code="speculative_asset_brief_count",
                    severity="error",
                    message="Opportunity Card must contain between 2 and 4 speculative asset briefs.",
                    location="speculative_asset_briefs",
                    details={"count": len(card.speculative_asset_briefs)},
                )
            )
        if not card.disclaimer or "speculative" not in card.disclaimer.lower() or "uncommissioned" not in card.disclaimer.lower():
            findings.append(
                OpportunityCardValidationFinding(
                    code="missing_speculative_disclaimer",
                    severity="blocking",
                    message="Opportunity Card must state that the work is speculative and uncommissioned.",
                    location="disclaimer",
                )
            )
        if not card.recommended_next_conversation:
            findings.append(
                OpportunityCardValidationFinding(
                    code="missing_next_conversation",
                    severity="error",
                    message="Opportunity Card must recommend the next conversation with Matt.",
                    location="recommended_next_conversation",
                )
            )
        for label, section in (
            ("commercial_diagnosis", card.commercial_diagnosis),
            ("growth_opportunity", card.growth_opportunity),
            ("narrative_direction", card.narrative_direction),
            ("creative_treatment", card.creative_treatment),
            ("outreach_draft", card.outreach_draft),
        ):
            findings.extend(
                self._validate_evidence_bearing_section(
                    section=section,
                    label=label,
                    records_by_id=records_by_id,
                    aliases=aliases,
                    canonical_ids=canonical_ids,
                )
            )
        for index, brief in enumerate(card.speculative_asset_briefs, start=1):
            findings.extend(
                self._validate_evidence_bearing_section(
                    section=brief,
                    label=f"speculative_asset_briefs[{index}]",
                    records_by_id=records_by_id,
                    aliases=aliases,
                    canonical_ids=canonical_ids,
                )
            )
        if not card.source_notes:
            findings.append(
                OpportunityCardValidationFinding(
                    code="missing_source_notes",
                    severity="warning",
                    message="Opportunity Card should retain source notes for the prospecting context.",
                    location="source_notes",
                )
            )
        if not card.evidence_references:
            findings.append(
                OpportunityCardValidationFinding(
                    code="missing_evidence_references",
                    severity="warning",
                    message="Opportunity Card should retain evidence references for material claims.",
                    location="evidence_references",
                )
            )
        for note in card.source_notes:
            findings.extend(
                self._validate_note(
                    note,
                    records_by_id=records_by_id,
                    aliases=aliases,
                    canonical_ids=canonical_ids,
                )
            )
        for reference in card.evidence_references:
            findings.extend(
                self._validate_reference(
                    reference,
                    records_by_id=records_by_id,
                    aliases=aliases,
                    canonical_ids=canonical_ids,
                )
            )
        if not card.commercial_diagnosis.evidence_ids and not card.commercial_diagnosis.is_hypothesis:
            findings.append(
                OpportunityCardValidationFinding(
                    code="missing_evidence_for_diagnosis",
                    severity="error",
                    message="Commercial diagnosis must be evidence-backed or explicitly marked as a hypothesis.",
                    location="commercial_diagnosis",
                )
            )
        if not card.growth_opportunity.evidence_ids and not card.growth_opportunity.is_hypothesis:
            findings.append(
                OpportunityCardValidationFinding(
                    code="missing_evidence_for_growth_opportunity",
                    severity="error",
                    message="Growth opportunity must be evidence-backed or explicitly marked as a hypothesis.",
                    location="growth_opportunity",
                )
            )
        if not card.narrative_direction.evidence_ids and not card.narrative_direction.is_hypothesis:
            findings.append(
                OpportunityCardValidationFinding(
                    code="missing_evidence_for_narrative_direction",
                    severity="error",
                    message="Narrative direction must be evidence-backed or explicitly marked as a hypothesis.",
                    location="narrative_direction",
                )
            )
        if asset_set.approval_required and not asset_set.selected_results:
            findings.append(
                OpportunityCardValidationFinding(
                    code="asset_selection_pending",
                    severity="warning",
                    message="Speculative asset generation produced no selected outputs yet.",
                    location="selected_asset_set",
                )
            )
        return _dedupe_findings(findings)

    def _validate_evidence_bearing_section(
        self,
        *,
        section: Any,
        label: str,
        records_by_id: Mapping[str, Mapping[str, Any]],
        aliases: Mapping[str, str],
        canonical_ids: set[str],
    ) -> tuple[OpportunityCardValidationFinding, ...]:
        findings: list[OpportunityCardValidationFinding] = []
        evidence_ids = tuple(dict.fromkeys(getattr(section, "evidence_ids", ()) or ()))
        source_notes = tuple(getattr(section, "source_notes", ()) or ())
        is_hypothesis = bool(getattr(section, "is_hypothesis", False))
        if not evidence_ids and not is_hypothesis:
            findings.append(
                OpportunityCardValidationFinding(
                    code="unsupported_claim",
                    severity="error",
                    message=f"{label} must reference evidence IDs or be marked as a hypothesis.",
                    location=label,
                )
            )
        for evidence_id in evidence_ids:
            resolved = aliases.get(evidence_id, evidence_id)
            if resolved not in canonical_ids:
                findings.append(
                    OpportunityCardValidationFinding(
                        code="missing_evidence_reference",
                        severity="error",
                        message=f"{label} references an evidence ID that was not collected for the research job.",
                        location=label,
                        evidence_ids=(evidence_id,),
                        details={"resolved_evidence_id": resolved},
                    )
                )
        for note in source_notes:
            findings.extend(
                self._validate_note(
                    note,
                    records_by_id=records_by_id,
                    aliases=aliases,
                    canonical_ids=canonical_ids,
                )
            )
        return tuple(findings)

    def _validate_note(
        self,
        note: SourceNote,
        *,
        records_by_id: Mapping[str, Mapping[str, Any]],
        aliases: Mapping[str, str],
        canonical_ids: set[str],
    ) -> tuple[OpportunityCardValidationFinding, ...]:
        findings: list[OpportunityCardValidationFinding] = []
        if not note.text:
            findings.append(
                OpportunityCardValidationFinding(
                    code="empty_source_note",
                    severity="warning",
                    message="Source notes should not be empty.",
                    location="source_notes",
                )
            )
        for evidence_id in note.evidence_ids:
            resolved = aliases.get(evidence_id, evidence_id)
            if resolved not in canonical_ids:
                findings.append(
                    OpportunityCardValidationFinding(
                        code="missing_source_note_evidence",
                        severity="error",
                        message="A source note references an evidence ID that was not collected.",
                        location="source_notes",
                        evidence_ids=(evidence_id,),
                        details={"resolved_evidence_id": resolved},
                    )
                )
        for reference in note.evidence_references:
            findings.extend(
                self._validate_reference(
                    reference,
                    records_by_id=records_by_id,
                    aliases=aliases,
                    canonical_ids=canonical_ids,
                )
            )
        return tuple(findings)

    def _validate_reference(
        self,
        reference: EvidenceReference,
        *,
        records_by_id: Mapping[str, Mapping[str, Any]],
        aliases: Mapping[str, str],
        canonical_ids: set[str],
    ) -> tuple[OpportunityCardValidationFinding, ...]:
        resolved = aliases.get(reference.evidence_id, reference.evidence_id)
        if resolved not in canonical_ids:
            return (
                OpportunityCardValidationFinding(
                    code="missing_evidence_reference",
                    severity="error",
                    message="Evidence reference points to an evidence ID that was not collected.",
                    location="evidence_references",
                    evidence_ids=(reference.evidence_id,),
                    details={"resolved_evidence_id": resolved},
                ),
            )
        if not reference.source_note:
            return (
                OpportunityCardValidationFinding(
                    code="missing_source_note",
                    severity="warning",
                    message="Evidence reference should retain a source note.",
                    location="evidence_references",
                    evidence_ids=(reference.evidence_id,),
                ),
            )
        return ()

    def _card_status(
        self,
        findings: Sequence[OpportunityCardValidationFinding],
        asset_set: SpeculativeAssetSet,
    ) -> str:
        if any(finding.severity == "blocking" for finding in findings):
            return "blocked"
        if any(finding.severity == "error" for finding in findings):
            return "blocked"
        if asset_set.approval_required and asset_set.selected_results:
            return "ready_for_review"
        if asset_set.status == "awaiting_approval":
            return "ready_for_review"
        return "assets_pending" if not asset_set.selected_results else "ready_for_review"

    def _render_review_summary(
        self,
        card: OpportunityCard,
        research_run: ResearchRun,
        asset_set: SpeculativeAssetSet,
    ) -> str:
        lines = [
            "# Opportunity Card Review Summary",
            f"- Company: {card.company_name}",
            f"- URL: {card.company_url}",
            f"- Status: {card.status}",
            f"- Research pack: {research_run.evidence_pack.pack_id}",
            f"- Evidence records: {len(research_run.evidence_pack.records)}",
            f"- Selected speculative assets: {len(asset_set.selected_results)}",
            f"- Confidence: {card.confidence}",
            "",
            "## Commercial diagnosis",
            card.commercial_diagnosis.statement,
            "",
            "## Growth opportunity",
            card.growth_opportunity.statement,
            "",
            "## Narrative direction",
            card.narrative_direction.statement,
            "",
            "## Creative treatment",
            card.creative_treatment.treatment,
            "",
            "## Recommended next conversation",
            card.recommended_next_conversation,
        ]
        return "\n".join(lines).strip()

    def _load_prompt_version(self) -> PromptVersion:
        if not self.prompt_source_path.is_file():
            raise OpportunityCardBlockedError(f"Opportunity Card prompt source not found: {self.prompt_source_path}")
        content = self.prompt_source_path.read_text(encoding="utf-8")
        metadata = {
            "source_path": str(self.prompt_source_path),
            "source_title": "Narratiive Opportunity Card Prompt v1",
            "source_checksum": sha256_hex(content),
            "purpose": "opportunity_card_orchestration",
            "prompt_asset": {
                "source_path": str(self.prompt_source_path),
                "source_title": "Narratiive Opportunity Card Prompt v1",
                "source_checksum": sha256_hex(content),
            },
        }
        if DEFAULT_STRATEGIC_PRINCIPLES_PATH.is_file():
            principles = DEFAULT_STRATEGIC_PRINCIPLES_PATH.read_text(encoding="utf-8")
            metadata["strategic_principles"] = {
                "source_path": str(DEFAULT_STRATEGIC_PRINCIPLES_PATH),
                "source_checksum": sha256_hex(principles),
                "content": principles,
            }
        history = self.prompt_registry.history(self.prompt_id)
        if history and history[-1].content == content and history[-1].metadata == metadata:
            prompt = history[-1]
        else:
            prompt = self.prompt_registry.publish(self.prompt_id, content, metadata=metadata)
        self.prompt_registry.activate(self.prompt_id, prompt.version)
        return prompt

    def _response_metadata(
        self,
        *,
        request: OpportunityCardRequest,
        prompt: PromptVersion,
        response: OpportunityCardEngineResponse,
        research_run: ResearchRun,
        research_pack_artifact: ArtifactRecord,
    ) -> dict[str, Any]:
        return {
            "request": request.to_dict(),
            "prompt_id": prompt.prompt_id,
            "prompt_version": prompt.version,
            "prompt_checksum": prompt.checksum,
            "provider_id": response.provider_id,
            "model_id": response.model_id,
            "requested_provider_id": response.requested_provider_id,
            "requested_model_id": response.requested_model_id,
            "routing_policy_id": response.routing_policy_id,
            "routing_policy_version": response.routing_policy_version,
            "research_pack_id": research_run.evidence_pack.pack_id,
            "research_pack_checksum": sha256_hex(_stable_json(research_run.evidence_pack.as_dict())),
            "research_pack_path": research_run.pack_path,
            "research_pack_artifact": research_pack_artifact.to_dict(),
        }

    def _summarise_changes(
        self,
        *,
        previous: OpportunityCardVersionRecord | None,
        request: OpportunityCardRequest,
        prompt: PromptVersion,
        response: OpportunityCardEngineResponse,
        research_run: ResearchRun,
        card: OpportunityCard,
        structured_artifact: ArtifactRecord,
        raw_response_artifact: ArtifactRecord,
        research_pack_artifact: ArtifactRecord,
    ) -> tuple[OpportunityCardChangeSummary, ...]:
        if previous is None:
            return ()
        changes: list[OpportunityCardChangeSummary] = []
        comparisons = (
            ("input_checksum", previous.input_checksum, request.request_checksum(), "Opportunity Card request changed."),
            ("research_pack_id", previous.research_pack_id, research_run.evidence_pack.pack_id, "Research pack changed."),
            ("prompt_version", previous.prompt_version, prompt.version, "Prompt version changed."),
            ("prompt_checksum", previous.prompt_checksum, prompt.checksum, "Prompt content changed."),
            ("provider_id", previous.provider_id, response.provider_id, "Provider changed."),
            ("model_id", previous.model_id, response.model_id, "Model changed."),
            ("status", previous.status, card.status, "Opportunity Card status changed."),
            ("raw_response_checksum", previous.raw_response_artifact.artifact.checksum, raw_response_artifact.artifact.checksum, "Raw response changed."),
            ("structured_checksum", previous.structured_artifact.artifact.checksum, structured_artifact.artifact.checksum, "Structured Opportunity Card changed."),
            ("research_pack_checksum", previous.research_pack_artifact.artifact.checksum, research_pack_artifact.artifact.checksum, "Research pack changed."),
        )
        for field, before, after, reason in comparisons:
            if before != after:
                changes.append(OpportunityCardChangeSummary(field=field, before=before, after=after, reason=reason))
        return tuple(changes)


def _load_evidence_pack_from_artifact(artifact: ArtifactRecord) -> EvidencePack:
    payload = json.loads(Path(artifact.artifact.location).read_text(encoding="utf-8"))
    return EvidencePack(
        pack_id=str(payload["pack_id"]),
        workspace_id=str(payload["workspace_id"]),
        job_id=str(payload["job_id"]),
        query=str(payload["query"]),
        created_at=str(payload["created_at"]),
        previous_pack_id=payload.get("previous_pack_id"),
        lineage=list(payload.get("lineage") or []),
        sources=list(payload.get("sources") or []),
        records=list(payload.get("records") or []),
        claims=list(payload.get("claims") or []),
        unsupported_claims=list(payload.get("unsupported_claims") or []),
        evidence_aliases=dict(payload.get("evidence_aliases") or {}),
        missing_inputs=list(payload.get("missing_inputs") or []),
        blockers=list(payload.get("blockers") or []),
        status=str(payload.get("status", "complete")),
        source_policy=dict(payload.get("source_policy") or {}),
    )
