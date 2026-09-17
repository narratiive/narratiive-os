from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from runtime.campaign_engine import CampaignIdentity
from runtime.execution_journal import ExecutionJournal, ExecutionRecord


class MediaControlError(RuntimeError):
    """Base error for fail-closed media operations."""


class MediaConfigurationError(MediaControlError):
    pass


class MediaMutationDisabled(MediaControlError):
    pass


class MediaProviderError(MediaControlError):
    pass


class MalformedProviderResponse(MediaProviderError):
    pass


class MediaProvider(str, Enum):
    META = "meta"
    TIKTOK = "tiktok"
    GOOGLE = "google"


class MediaAuthority(str, Enum):
    READ = "read"
    ANALYSE = "analyse"
    RECOMMEND = "recommend"
    DRAFT = "draft"
    EXECUTE_WITHIN_LIMITS = "execute_within_limits"
    EXECUTE_WITH_APPROVAL = "execute_with_approval"
    PROHIBITED = "prohibited"


class ConnectionHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    NOT_CONFIGURED = "not_configured"


class MediaLifecycleStage(str, Enum):
    MEDIA_PLAN = "media_plan"
    MEDIA_REVIEW = "media_review"
    HUMAN_APPROVAL = "human_approval"
    TRAFFICKING = "trafficking"
    PRE_LAUNCH_VALIDATION = "pre_launch_validation"
    HUMAN_LAUNCH_APPROVAL = "human_launch_approval"
    LAUNCH = "launch"
    MONITOR = "monitor"
    OPTIMISE = "optimise"
    LEARN = "learn"


WRITE_OPERATIONS = frozenset(
    {
        "create_campaign",
        "create_ad_group",
        "create_ad",
        "upload_creative",
        "update_budget",
        "pause_ad",
        "resume_ad",
        "activate_campaign",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderConfiguration:
    provider: MediaProvider
    account_id: str
    credential_env_names: tuple[str, ...]
    manager_account_id: str = ""
    timezone_name: str = ""
    currency: str = ""

    def validate(self, environment: Mapping[str, str] | None = None) -> tuple[str, ...]:
        env = environment or os.environ
        failures: list[str] = []
        if not self.account_id.strip():
            failures.append("account_id is required")
        missing = [name for name in self.credential_env_names if not str(env.get(name, "")).strip()]
        if missing:
            failures.append("missing credential environment variables: " + ", ".join(missing))
        if self.currency and (len(self.currency) != 3 or not self.currency.isalpha()):
            failures.append("currency must be an ISO 4217 three-letter code")
        if not self.timezone_name.strip():
            failures.append("timezone is required")
        return tuple(failures)


@dataclass(frozen=True, slots=True)
class ProviderObjectMapping:
    provider: MediaProvider
    account_id: str
    campaign_id: str
    ad_group_ids: tuple[str, ...] = ()
    ad_ids: tuple[str, ...] = ()
    creative_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.account_id.strip() or not self.campaign_id.strip():
            raise MediaControlError("provider account_id and campaign_id are required")


@dataclass(frozen=True, slots=True)
class CanonicalMediaPlan:
    """Approved-strategy media projection; platforms never become strategy truth."""

    identity: CampaignIdentity
    plan_id: str
    version: str
    checksum: str
    objective: str
    audience_ids: tuple[str, ...]
    approved_client_budget: Decimal
    platform_budgets: Mapping[MediaProvider, Decimal]
    currency: str
    start_at: str
    end_at: str
    kpis: tuple[str, ...]
    tracking_references: tuple[str, ...]
    stage: MediaLifecycleStage = MediaLifecycleStage.MEDIA_PLAN
    human_approval_id: str = ""
    launch_approval_id: str = ""

    def __post_init__(self) -> None:
        required = (self.plan_id, self.version, self.checksum, self.objective)
        if any(not value.strip() for value in required):
            raise MediaControlError("media plan identity, version, checksum and objective are required")
        if not self.audience_ids or not self.kpis or not self.tracking_references:
            raise MediaControlError("media plan requires audiences, KPIs and tracking references")
        if self.approved_client_budget <= 0:
            raise MediaControlError("approved client budget must be positive")
        if not self.platform_budgets or any(value < 0 for value in self.platform_budgets.values()):
            raise MediaControlError("platform budgets must be present and non-negative")
        if sum(self.platform_budgets.values(), Decimal("0")) > self.approved_client_budget:
            raise MediaControlError("sum of platform authorised budgets exceeds approved client budget")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise MediaControlError("media plan currency must be an ISO 4217 three-letter code")
        if _parse_timestamp(self.end_at, "end_at") <= _parse_timestamp(self.start_at, "start_at"):
            raise MediaControlError("media plan end_at must follow start_at")
        if self.stage in {
            MediaLifecycleStage.TRAFFICKING,
            MediaLifecycleStage.PRE_LAUNCH_VALIDATION,
            MediaLifecycleStage.HUMAN_LAUNCH_APPROVAL,
            MediaLifecycleStage.LAUNCH,
            MediaLifecycleStage.MONITOR,
            MediaLifecycleStage.OPTIMISE,
            MediaLifecycleStage.LEARN,
        } and not self.human_approval_id.strip():
            raise MediaControlError("media plan cannot pass human approval without an explicit approval ID")
        if self.stage in {
            MediaLifecycleStage.LAUNCH,
            MediaLifecycleStage.MONITOR,
            MediaLifecycleStage.OPTIMISE,
            MediaLifecycleStage.LEARN,
        } and not self.launch_approval_id.strip():
            raise MediaControlError("media plan cannot pass launch approval without an explicit approval ID")


@dataclass(frozen=True, slots=True)
class CreativePlatformMapping:
    narratiive_asset_id: str
    campaign_world_id: str
    creative_territory: str
    format: str
    hook: str
    message: str
    audience: str
    provider: MediaProvider
    placement: str
    provider_creative_ids: tuple[str, ...]
    provider_ad_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        required = (
            self.narratiive_asset_id,
            self.campaign_world_id,
            self.creative_territory,
            self.format,
            self.provider.value,
        )
        if any(not value.strip() for value in required):
            raise MediaControlError("creative mappings require stable Narratiive and provider context")
        if not self.provider_creative_ids and not self.provider_ad_ids:
            raise MediaControlError("creative mapping requires at least one native provider ID")


@dataclass(frozen=True, slots=True)
class MetricValue:
    name: str
    value: Decimal | None
    provider: MediaProvider
    definition: str
    period_start: str
    period_end: str
    currency: str | None = None
    attribution_context: str = ""
    available: bool = True
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.definition.strip():
            raise MediaControlError("metric name and definition are required")
        if not self.period_start or not self.period_end:
            raise MediaControlError("metric period is required")
        if self.available and self.value is None:
            raise MediaControlError("available metric requires a value")
        if not self.available and self.value is not None:
            raise MediaControlError("unavailable metric must not contain a value")
        if not self.available and not self.unavailable_reason.strip():
            raise MediaControlError("unavailable metric requires a reason")
        if self.currency and (len(self.currency) != 3 or not self.currency.isalpha()):
            raise MediaControlError("metric currency must be an ISO 4217 three-letter code")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["provider"] = self.provider.value
        value["value"] = str(self.value) if self.value is not None else None
        return value


@dataclass(frozen=True, slots=True)
class CanonicalMediaSnapshot:
    identity: CampaignIdentity
    provider: MediaProvider
    provider_mapping: ProviderObjectMapping
    period_start: str
    period_end: str
    currency: str
    timezone_name: str
    campaign_status: str
    review_status: str
    tracking_status: str
    authorised_budget: Decimal | None
    metrics: tuple[MetricValue, ...]
    creative_mappings: tuple[CreativePlatformMapping, ...] = ()
    breakdowns: Mapping[str, Any] = field(default_factory=dict)
    ingested_at: str = ""

    def metric(self, name: str) -> MetricValue | None:
        return next((metric for metric in self.metrics if metric.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": asdict(self.identity),
            "provider": self.provider.value,
            "provider_mapping": {
                **asdict(self.provider_mapping),
                "provider": self.provider_mapping.provider.value,
            },
            "period_start": self.period_start,
            "period_end": self.period_end,
            "currency": self.currency,
            "timezone_name": self.timezone_name,
            "campaign_status": self.campaign_status,
            "review_status": self.review_status,
            "tracking_status": self.tracking_status,
            "authorised_budget": str(self.authorised_budget) if self.authorised_budget is not None else None,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "creative_mappings": [
                {**asdict(item), "provider": item.provider.value} for item in self.creative_mappings
            ],
            "breakdowns": dict(self.breakdowns),
            "ingested_at": self.ingested_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CanonicalMediaSnapshot":
        identity_value = value["identity"]
        mapping_value = value["provider_mapping"]
        return cls(
            identity=CampaignIdentity(
                workspace_id=str(identity_value["workspace_id"]),
                client_id=str(identity_value["client_id"]),
                brand_id=str(identity_value["brand_id"]),
                market_ids=tuple(identity_value["market_ids"]),
                product_ids=tuple(identity_value["product_ids"]),
                campaign_id=str(identity_value["campaign_id"]),
            ),
            provider=MediaProvider(str(value["provider"])),
            provider_mapping=ProviderObjectMapping(
                provider=MediaProvider(str(mapping_value["provider"])),
                account_id=str(mapping_value["account_id"]),
                campaign_id=str(mapping_value["campaign_id"]),
                ad_group_ids=tuple(mapping_value.get("ad_group_ids", ())),
                ad_ids=tuple(mapping_value.get("ad_ids", ())),
                creative_ids=tuple(mapping_value.get("creative_ids", ())),
            ),
            period_start=str(value["period_start"]),
            period_end=str(value["period_end"]),
            currency=str(value["currency"]),
            timezone_name=str(value["timezone_name"]),
            campaign_status=str(value["campaign_status"]),
            review_status=str(value["review_status"]),
            tracking_status=str(value["tracking_status"]),
            authorised_budget=_decimal_or_none(value.get("authorised_budget")),
            metrics=tuple(
                MetricValue(
                    name=str(item["name"]),
                    value=_decimal_or_none(item.get("value")),
                    provider=MediaProvider(str(item["provider"])),
                    definition=str(item["definition"]),
                    period_start=str(item["period_start"]),
                    period_end=str(item["period_end"]),
                    currency=item.get("currency"),
                    attribution_context=str(item.get("attribution_context", "")),
                    available=bool(item.get("available", True)),
                    unavailable_reason=str(item.get("unavailable_reason", "")),
                )
                for item in value.get("metrics", ())
            ),
            creative_mappings=tuple(
                CreativePlatformMapping(
                    narratiive_asset_id=str(item["narratiive_asset_id"]),
                    campaign_world_id=str(item["campaign_world_id"]),
                    creative_territory=str(item["creative_territory"]),
                    format=str(item["format"]),
                    hook=str(item.get("hook", "")),
                    message=str(item.get("message", "")),
                    audience=str(item.get("audience", "")),
                    provider=MediaProvider(str(item["provider"])),
                    placement=str(item.get("placement", "")),
                    provider_creative_ids=tuple(item.get("provider_creative_ids", ())),
                    provider_ad_ids=tuple(item.get("provider_ad_ids", ())),
                )
                for item in value.get("creative_mappings", ())
            ),
            breakdowns=dict(value.get("breakdowns", {})),
            ingested_at=str(value.get("ingested_at", "")),
        )


@dataclass(frozen=True, slots=True)
class MediaRecommendation:
    recommendation_id: str
    client_id: str
    campaign_id: str
    severity: str
    category: str
    summary: str
    evidence: tuple[str, ...]
    proposed_action: str
    authority: MediaAuthority = MediaAuthority.RECOMMEND
    human_approval_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["authority"] = self.authority.value
        return value


@dataclass(frozen=True, slots=True)
class PreLaunchValidation:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    total_platform_budget: Decimal
    approved_client_budget: Decimal


class MediaPolicyEngine:
    """Deterministic Phase 1 authority boundary. Prompts cannot override it."""

    ALLOWED = frozenset({MediaAuthority.READ, MediaAuthority.ANALYSE, MediaAuthority.RECOMMEND})

    def authorize(self, authority: MediaAuthority, operation: str) -> None:
        if operation in WRITE_OPERATIONS or authority not in self.ALLOWED:
            raise MediaMutationDisabled(
                f"Phase 1 prohibits {operation} ({authority.value}); no provider mutation executed"
            )


class ProviderTransport(Protocol):
    def request(self, provider: MediaProvider, operation: str, parameters: Mapping[str, Any]) -> Any: ...


class MediaProviderAdapter(Protocol):
    provider: MediaProvider

    def authenticate(self) -> Mapping[str, Any]: ...
    def get_accounts(self) -> Sequence[Mapping[str, Any]]: ...
    def get_campaigns(self) -> Sequence[Mapping[str, Any]]: ...
    def get_campaign(self, campaign_id: str) -> Mapping[str, Any]: ...
    def get_ad_groups(self, campaign_id: str) -> Sequence[Mapping[str, Any]]: ...
    def get_ads(self, campaign_id: str) -> Sequence[Mapping[str, Any]]: ...
    def get_creatives(self, campaign_id: str) -> Sequence[Mapping[str, Any]]: ...
    def get_performance(self, campaign_id: str, period_start: str, period_end: str) -> Mapping[str, Any]: ...
    def get_delivery_status(self, campaign_id: str) -> Mapping[str, Any]: ...
    def get_review_status(self, campaign_id: str) -> Mapping[str, Any]: ...


class ReadOnlyProviderAdapter:
    provider: MediaProvider

    def __init__(
        self,
        configuration: ProviderConfiguration,
        transport: ProviderTransport,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if configuration.provider is not self.provider:
            raise MediaConfigurationError("adapter/provider configuration mismatch")
        failures = configuration.validate(environment)
        if failures:
            raise MediaConfigurationError("; ".join(failures))
        self.configuration = configuration
        self.transport = transport

    def _read(self, operation: str, **parameters: Any) -> Any:
        try:
            return self.transport.request(self.provider, operation, parameters)
        except MediaProviderError:
            raise
        except Exception as exc:
            raise MediaProviderError(f"{self.provider.value} {operation} failed") from exc

    def authenticate(self) -> Mapping[str, Any]:
        return self._read("authenticate")

    def get_accounts(self) -> Sequence[Mapping[str, Any]]:
        return self._read("get_accounts")

    def get_campaigns(self) -> Sequence[Mapping[str, Any]]:
        return self._read("get_campaigns", account_id=self.configuration.account_id)

    def get_campaign(self, campaign_id: str) -> Mapping[str, Any]:
        return self._read("get_campaign", campaign_id=campaign_id)

    def get_ad_groups(self, campaign_id: str) -> Sequence[Mapping[str, Any]]:
        return self._read("get_ad_groups", campaign_id=campaign_id)

    def get_ads(self, campaign_id: str) -> Sequence[Mapping[str, Any]]:
        return self._read("get_ads", campaign_id=campaign_id)

    def get_creatives(self, campaign_id: str) -> Sequence[Mapping[str, Any]]:
        return self._read("get_creatives", campaign_id=campaign_id)

    def get_performance(self, campaign_id: str, period_start: str, period_end: str) -> Mapping[str, Any]:
        value = self._read(
            "get_performance",
            campaign_id=campaign_id,
            period_start=period_start,
            period_end=period_end,
        )
        if not isinstance(value, Mapping):
            raise MalformedProviderResponse(f"{self.provider.value} performance response must be an object")
        return value

    def get_delivery_status(self, campaign_id: str) -> Mapping[str, Any]:
        return self._read("get_delivery_status", campaign_id=campaign_id)

    def get_review_status(self, campaign_id: str) -> Mapping[str, Any]:
        return self._read("get_review_status", campaign_id=campaign_id)

    def _mutation_disabled(self, operation: str, *_args: Any, **_kwargs: Any) -> None:
        raise MediaMutationDisabled(f"{self.provider.value} {operation} is disabled in Phase 1")

    create_campaign = lambda self, *args, **kwargs: self._mutation_disabled("create_campaign", *args, **kwargs)
    create_ad_group = lambda self, *args, **kwargs: self._mutation_disabled("create_ad_group", *args, **kwargs)
    create_ad = lambda self, *args, **kwargs: self._mutation_disabled("create_ad", *args, **kwargs)
    upload_creative = lambda self, *args, **kwargs: self._mutation_disabled("upload_creative", *args, **kwargs)
    update_budget = lambda self, *args, **kwargs: self._mutation_disabled("update_budget", *args, **kwargs)
    pause_ad = lambda self, *args, **kwargs: self._mutation_disabled("pause_ad", *args, **kwargs)
    resume_ad = lambda self, *args, **kwargs: self._mutation_disabled("resume_ad", *args, **kwargs)
    activate_campaign = lambda self, *args, **kwargs: self._mutation_disabled("activate_campaign", *args, **kwargs)


class MetaReadOnlyAdapter(ReadOnlyProviderAdapter):
    provider = MediaProvider.META


class TikTokReadOnlyAdapter(ReadOnlyProviderAdapter):
    provider = MediaProvider.TIKTOK


class GoogleReadOnlyAdapter(ReadOnlyProviderAdapter):
    provider = MediaProvider.GOOGLE


class FixtureTransport:
    """Deterministic provider transport for isolated certification only."""

    def __init__(self, responses: Mapping[str, Any]) -> None:
        self.responses = dict(responses)
        self.calls: list[tuple[MediaProvider, str, Mapping[str, Any]]] = []

    def request(self, provider: MediaProvider, operation: str, parameters: Mapping[str, Any]) -> Any:
        self.calls.append((provider, operation, dict(parameters)))
        value = self.responses.get(operation)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise MediaProviderError(f"fixture has no response for {provider.value} {operation}")
        return value


class MediaNormaliser:
    METRIC_DEFINITIONS = {
        "spend": "Provider-reported media cost for the requested reporting period.",
        "budget": "Provider-reported authorised or configured budget.",
        "impressions": "Provider-counted ad impressions.",
        "reach": "Provider-estimated unique accounts reached.",
        "frequency": "Provider-reported average impressions per reached account.",
        "cpm": "Provider-reported cost per thousand impressions.",
        "clicks": "Provider-counted clicks under its click definition.",
        "ctr": "Provider-reported click-through rate.",
        "cpc": "Provider-reported cost per click.",
        "video_views": "Provider-counted video views under its view threshold.",
        "video_completions": "Provider-counted completed video views.",
        "conversions": "Provider-attributed conversions under the retained attribution context.",
        "conversion_value": "Provider-attributed conversion value.",
        "cpa": "Provider-reported cost per attributed conversion.",
        "roas": "Provider-reported attributed return on ad spend.",
    }

    def normalise(
        self,
        identity: CampaignIdentity,
        provider: MediaProvider,
        provider_mapping: ProviderObjectMapping,
        response: Mapping[str, Any],
        creative_mappings: Sequence[CreativePlatformMapping] = (),
    ) -> CanonicalMediaSnapshot:
        required = (
            "period_start",
            "period_end",
            "currency",
            "timezone",
            "campaign_status",
            "review_status",
            "tracking_status",
            "metrics",
        )
        missing = [name for name in required if name not in response]
        if missing:
            raise MalformedProviderResponse("provider response is missing: " + ", ".join(missing))
        raw_metrics = response["metrics"]
        if not isinstance(raw_metrics, Mapping):
            raise MalformedProviderResponse("provider metrics must be an object")
        period_start = _parse_timestamp(response["period_start"], "period_start")
        period_end = _parse_timestamp(response["period_end"], "period_end")
        if period_end < period_start:
            raise MalformedProviderResponse("provider period_end precedes period_start")
        currency = str(response["currency"]).upper()
        if len(currency) != 3 or not currency.isalpha():
            raise MalformedProviderResponse("provider currency must be an ISO 4217 three-letter code")
        if not str(response["timezone"]).strip():
            raise MalformedProviderResponse("provider timezone is required")
        attribution = str(response.get("attribution_context", "unavailable"))
        metrics: list[MetricValue] = []
        for name, definition in self.METRIC_DEFINITIONS.items():
            raw = raw_metrics.get(name)
            available = raw is not None
            try:
                numeric = _decimal_or_none(raw)
            except (InvalidOperation, ValueError) as exc:
                raise MalformedProviderResponse(f"invalid numeric metric: {name}") from exc
            metrics.append(
                MetricValue(
                    name=name,
                    value=numeric,
                    provider=provider,
                    definition=definition,
                    period_start=str(response["period_start"]),
                    period_end=str(response["period_end"]),
                    currency=currency if name in {"spend", "budget", "cpm", "cpc", "conversion_value", "cpa"} else None,
                    attribution_context=attribution,
                    available=available,
                    unavailable_reason="provider did not supply this metric" if not available else "",
                )
            )
        return CanonicalMediaSnapshot(
            identity=identity,
            provider=provider,
            provider_mapping=provider_mapping,
            period_start=str(response["period_start"]),
            period_end=str(response["period_end"]),
            currency=currency,
            timezone_name=str(response["timezone"]),
            campaign_status=str(response["campaign_status"]),
            review_status=str(response["review_status"]),
            tracking_status=str(response["tracking_status"]),
            authorised_budget=_decimal_or_none(response.get("authorised_budget")),
            metrics=tuple(metrics),
            creative_mappings=tuple(creative_mappings),
            breakdowns=dict(response.get("breakdowns", {})),
            ingested_at=_utc_now(),
        )


class PreLaunchValidator:
    def validate(
        self,
        *,
        approved_client_budget: Decimal,
        platform_budgets: Mapping[MediaProvider, Decimal],
        prerequisites: Mapping[str, bool],
        currencies: Sequence[str],
        timezones: Sequence[str],
    ) -> PreLaunchValidation:
        errors = [f"missing or unverified prerequisite: {name}" for name, ok in prerequisites.items() if not ok]
        total = sum(platform_budgets.values(), Decimal("0"))
        if total > approved_client_budget:
            errors.append("sum of platform authorised budgets exceeds approved client budget")
        if not currencies or any(len(value) != 3 or not value.isalpha() for value in currencies):
            errors.append("currency is missing or invalid")
        if not timezones or any(not value.strip() for value in timezones):
            errors.append("timezone is missing or invalid")
        return PreLaunchValidation(
            ok=not errors,
            errors=tuple(errors),
            warnings=(),
            total_platform_budget=total,
            approved_client_budget=approved_client_budget,
        )


class MediaControlService:
    """Canonical read-only media control plane backed by Narratiive's execution journal."""

    AUDIT_ACTION = "media.provider_interaction"

    def __init__(
        self,
        adapters: Mapping[MediaProvider, MediaProviderAdapter],
        journal: ExecutionJournal,
        *,
        policy: MediaPolicyEngine | None = None,
        normaliser: MediaNormaliser | None = None,
    ) -> None:
        self.adapters = dict(adapters)
        self.journal = journal
        self.policy = policy or MediaPolicyEngine()
        self.normaliser = normaliser or MediaNormaliser()

    def ingest(
        self,
        *,
        identity: CampaignIdentity,
        provider_mapping: ProviderObjectMapping,
        period_start: str,
        period_end: str,
        request_id: str,
        tony_request: str,
        creative_mappings: Sequence[CreativePlatformMapping] = (),
    ) -> CanonicalMediaSnapshot:
        self.policy.authorize(MediaAuthority.READ, "get_performance")
        prior = self._record_for_request(request_id)
        if prior is not None:
            payload = prior.metadata.get("canonical_output")
            if not isinstance(payload, Mapping):
                raise MediaControlError("duplicate request has no trusted canonical output")
            return CanonicalMediaSnapshot.from_dict(payload)
        adapter = self.adapters.get(provider_mapping.provider)
        if adapter is None:
            self._audit_failure(identity, provider_mapping.provider, request_id, tony_request, "adapter not configured")
            raise MediaConfigurationError(f"{provider_mapping.provider.value} adapter is not configured")
        try:
            raw = adapter.get_performance(provider_mapping.campaign_id, period_start, period_end)
            snapshot = self.normaliser.normalise(
                identity,
                provider_mapping.provider,
                provider_mapping,
                raw,
                creative_mappings,
            )
        except Exception as exc:
            self._audit_failure(
                identity,
                provider_mapping.provider,
                request_id,
                tony_request,
                _audit_safe_error(exc),
            )
            raise
        self.journal.append(
            decision_id=f"media-{identity.campaign_id}",
            workspace_id=identity.workspace_id,
            client_id=identity.client_id,
            action=self.AUDIT_ACTION,
            rationale="Read-only provider performance ingestion requested by Tony.",
            actor="media-control-layer",
            status="completed",
            record_id=f"media-{_safe_hash(request_id)}",
            metadata={
                "timestamp": _utc_now(),
                "tony_request": tony_request,
                "agent": "media-agent",
                "provider": provider_mapping.provider.value,
                "operation": "get_performance",
                "authority": MediaAuthority.READ.value,
                "request_id": request_id,
                "result": "normalised",
                "affected_object_ids": [provider_mapping.campaign_id],
                "before_state": None,
                "after_state": "performance_ingested",
                "approval_id": None,
                "error": None,
                "retry_state": "not_required",
                "canonical_output": snapshot.to_dict(),
            },
        )
        return snapshot

    def prohibit_mutation(
        self,
        *,
        identity: CampaignIdentity,
        provider: MediaProvider,
        operation: str,
        request_id: str,
        approval_id: str = "",
    ) -> None:
        try:
            self.policy.authorize(MediaAuthority.EXECUTE_WITH_APPROVAL, operation)
        except MediaMutationDisabled as exc:
            self.journal.append(
                decision_id=f"media-{identity.campaign_id}",
                workspace_id=identity.workspace_id,
                client_id=identity.client_id,
                action=self.AUDIT_ACTION,
                rationale="Phase 1 policy blocked a provider mutation before adapter dispatch.",
                actor="media-control-layer",
                status="blocked",
                record_id=f"media-{_safe_hash(request_id)}",
                metadata={
                    "timestamp": _utc_now(),
                    "provider": provider.value,
                    "operation": operation,
                    "authority": MediaAuthority.EXECUTE_WITH_APPROVAL.value,
                    "request_id": request_id,
                    "result": "blocked",
                    "affected_object_ids": [],
                    "before_state": None,
                    "after_state": None,
                    "approval_id": approval_id or None,
                    "error": str(exc),
                    "retry_state": "prohibited_in_phase_1",
                },
            )
            raise

    def snapshots(self, *, client_id: str = "", campaign_id: str = "") -> tuple[CanonicalMediaSnapshot, ...]:
        snapshots: list[CanonicalMediaSnapshot] = []
        for record in self.journal.read_all():
            if record.action != self.AUDIT_ACTION or record.status != "completed":
                continue
            payload = record.metadata.get("canonical_output")
            if not isinstance(payload, Mapping):
                continue
            snapshot = CanonicalMediaSnapshot.from_dict(payload)
            if client_id and snapshot.identity.client_id != client_id:
                continue
            if campaign_id and snapshot.identity.campaign_id != campaign_id:
                continue
            snapshots.append(snapshot)
        latest: dict[tuple[str, str], CanonicalMediaSnapshot] = {}
        for snapshot in snapshots:
            latest[(snapshot.identity.campaign_id, snapshot.provider.value)] = snapshot
        return tuple(latest.values())

    def analyse(self, snapshots: Sequence[CanonicalMediaSnapshot]) -> tuple[MediaRecommendation, ...]:
        self.policy.authorize(MediaAuthority.ANALYSE, "analyse_performance")
        recommendations: list[MediaRecommendation] = []
        for snapshot in snapshots:
            evidence_prefix = f"{snapshot.provider.value}:{snapshot.provider_mapping.campaign_id}"
            if snapshot.review_status.casefold() in {"rejected", "disapproved"}:
                recommendations.append(self._recommend(snapshot, "critical", "creative_rejected", "A provider has rejected creative.", (evidence_prefix,), "Review rejection reason and prepare a compliant replacement; do not publish."))
            if snapshot.tracking_status.casefold() not in {"healthy", "active", "verified"}:
                recommendations.append(self._recommend(snapshot, "critical", "tracking", "Tracking is not verified.", (evidence_prefix, snapshot.tracking_status), "Investigate tracking before making performance decisions."))
            spend = snapshot.metric("spend")
            budget = snapshot.authorised_budget
            if spend and spend.value is not None and budget is not None and spend.value > budget * Decimal("0.9"):
                recommendations.append(self._recommend(snapshot, "high", "overspend_risk", "Spend has passed 90% of the authorised provider budget.", (f"spend={spend.value}", f"budget={budget}"), "Ask Matt to review pacing; no budget change is authorised."))
            roas = snapshot.metric("roas")
            if roas and roas.value is not None:
                if roas.value >= Decimal("3"):
                    recommendations.append(self._recommend(snapshot, "info", "high_performer", "Provider-attributed ROAS indicates a high performer.", (f"roas={roas.value}", roas.attribution_context), "Preserve the learning and review creative/audience drivers."))
                elif roas.value < Decimal("1"):
                    recommendations.append(self._recommend(snapshot, "high", "poor_performer", "Provider-attributed ROAS indicates a poor performer.", (f"roas={roas.value}", roas.attribution_context), "Prepare a creative or targeting review for human decision."))
        return tuple(recommendations)

    def diagnostics(self) -> dict[str, Any]:
        records = [record for record in self.journal.read_all() if record.action == self.AUDIT_ACTION]
        result: dict[str, Any] = {}
        for provider in MediaProvider:
            provider_records = [record for record in records if record.metadata.get("provider") == provider.value]
            completed = [record for record in provider_records if record.status == "completed"]
            failed = [record for record in provider_records if record.status == "failed"]
            if provider not in self.adapters:
                health = ConnectionHealth.NOT_CONFIGURED
            elif failed and (not completed or failed[-1].sequence > completed[-1].sequence):
                health = ConnectionHealth.OFFLINE
            elif failed:
                health = ConnectionHealth.DEGRADED
            else:
                health = ConnectionHealth.HEALTHY
            snapshots = [item for item in self.snapshots() if item.provider is provider]
            result[provider.value] = {
                "health": health.value,
                "last_successful_sync": completed[-1].occurred_at if completed else None,
                "last_failed_sync": failed[-1].occurred_at if failed else None,
                "credential_health": "configured_not_exposed" if provider in self.adapters else "not_configured",
                "mapped_campaigns": len({item.provider_mapping.campaign_id for item in snapshots}),
                "unmapped_campaigns": 0,
                "data_freshness": max((item.ingested_at for item in snapshots), default=None),
            }
        recommendations = self.analyse(self.snapshots())
        result["pending_recommendations"] = len(recommendations)
        result["pending_approvals"] = sum(1 for item in recommendations if item.human_approval_required)
        return result

    def _record_for_request(self, request_id: str) -> ExecutionRecord | None:
        matches = [
            record
            for record in self.journal.read_all()
            if record.action == self.AUDIT_ACTION and record.metadata.get("request_id") == request_id
        ]
        return matches[-1] if matches else None

    def _audit_failure(
        self,
        identity: CampaignIdentity,
        provider: MediaProvider,
        request_id: str,
        tony_request: str,
        error: str,
    ) -> None:
        self.journal.append(
            decision_id=f"media-{identity.campaign_id}",
            workspace_id=identity.workspace_id,
            client_id=identity.client_id,
            action=self.AUDIT_ACTION,
            rationale="Provider read failed closed; no campaign state advanced.",
            actor="media-control-layer",
            status="failed",
            record_id=f"media-{_safe_hash(request_id)}",
            metadata={
                "timestamp": _utc_now(),
                "tony_request": tony_request,
                "agent": "media-agent",
                "provider": provider.value,
                "operation": "get_performance",
                "authority": MediaAuthority.READ.value,
                "request_id": request_id,
                "result": "failed",
                "affected_object_ids": [],
                "before_state": None,
                "after_state": None,
                "approval_id": None,
                "error": error,
                "retry_state": "eligible_after_cause_resolved",
            },
        )

    @staticmethod
    def _recommend(
        snapshot: CanonicalMediaSnapshot,
        severity: str,
        category: str,
        summary: str,
        evidence: tuple[str, ...],
        proposed_action: str,
    ) -> MediaRecommendation:
        basis = f"{snapshot.identity.campaign_id}:{snapshot.provider.value}:{category}:{snapshot.period_end}"
        return MediaRecommendation(
            recommendation_id=f"rec-{_safe_hash(basis)}",
            client_id=snapshot.identity.client_id,
            campaign_id=snapshot.identity.campaign_id,
            severity=severity,
            category=category,
            summary=summary,
            evidence=evidence,
            proposed_action=proposed_action,
        )


def media_configuration_from_environment(provider: MediaProvider) -> ProviderConfiguration:
    requirements = {
        MediaProvider.META: ("META_ACCESS_TOKEN",),
        MediaProvider.TIKTOK: ("TIKTOK_ACCESS_TOKEN",),
        MediaProvider.GOOGLE: ("GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET"),
    }
    prefix = provider.value.upper()
    if provider is MediaProvider.GOOGLE:
        prefix = "GOOGLE_ADS"
    return ProviderConfiguration(
        provider=provider,
        account_id=os.getenv(f"{prefix}_ACCOUNT_ID", ""),
        manager_account_id=os.getenv(f"{prefix}_MANAGER_ACCOUNT_ID", ""),
        credential_env_names=requirements[provider],
        timezone_name=os.getenv(f"{prefix}_TIMEZONE", ""),
        currency=os.getenv(f"{prefix}_CURRENCY", ""),
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _safe_hash(value: str) -> str:
    if not value.strip():
        raise MediaControlError("request identifier is required")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any, field_name: str) -> datetime:
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MalformedProviderResponse(f"provider {field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise MalformedProviderResponse(f"provider {field_name} must include a timezone")
    return parsed


def _audit_safe_error(error: Exception) -> str:
    if isinstance(error, (MalformedProviderResponse, MediaConfigurationError, MediaMutationDisabled)):
        return f"{type(error).__name__}: {error}"
    return f"{type(error).__name__}: provider operation failed; inspect protected service logs"
