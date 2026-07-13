from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Collection, Mapping

from .execution_package import ExecutionPackage
from .provider import ProviderClient, ProviderResponse


class LatencyClass(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    SLOW = "slow"


class CostClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    reasoning: bool
    long_context: bool
    structured_output: bool
    vision: bool
    tool_use: bool
    latency_class: LatencyClass
    cost_class: CostClass


@dataclass(frozen=True, slots=True)
class ProviderModelRecord:
    provider_id: str
    model_id: str
    capabilities: ModelCapabilities

    def __post_init__(self) -> None:
        _require_value(self.provider_id, "provider_id")
        _require_value(self.model_id, "model_id")


@dataclass(frozen=True, slots=True)
class RouteTarget:
    provider_id: str
    model_id: str

    def __post_init__(self) -> None:
        _require_value(self.provider_id, "provider_id")
        _require_value(self.model_id, "model_id")


class ProviderCapabilityRegistry:
    """In-memory provider/model declarations; never stores credentials."""

    def __init__(self, records: Collection[ProviderModelRecord] = ()) -> None:
        self._records: dict[RouteTarget, ProviderModelRecord] = {}
        for record in records:
            self.register(record)

    def register(self, record: ProviderModelRecord) -> None:
        target = RouteTarget(record.provider_id, record.model_id)
        if target in self._records:
            raise ValueError(
                f"provider model is already registered: {record.provider_id}/{record.model_id}"
            )
        self._records[target] = record

    def get(self, target: RouteTarget) -> ProviderModelRecord:
        try:
            return self._records[target]
        except KeyError as exc:
            raise KeyError(
                f"provider model is not registered: {target.provider_id}/{target.model_id}"
            ) from exc

    def contains(self, target: RouteTarget) -> bool:
        return target in self._records


class ProviderAvailability(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProviderHealthRecord:
    target: RouteTarget
    availability: ProviderAvailability
    reason: str = ""


class ProviderHealthRegistry:
    """Current provider availability used by deterministic routing decisions."""

    def __init__(self, records: Collection[ProviderHealthRecord] = ()) -> None:
        self._records = {record.target: record for record in records}

    def set(self, record: ProviderHealthRecord) -> None:
        self._records[record.target] = record

    def get(self, target: RouteTarget) -> ProviderHealthRecord:
        return self._records.get(
            target,
            ProviderHealthRecord(
                target=target,
                availability=ProviderAvailability.UNKNOWN,
                reason="health_not_reported",
            ),
        )


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    policy_id: str
    version: str
    primary: RouteTarget
    fallbacks: tuple[RouteTarget, ...] = ()
    workspace_id: str = "*"
    stage_id: str | None = None
    specialist_id: str | None = None

    def __post_init__(self) -> None:
        _require_value(self.policy_id, "policy_id")
        _require_value(self.version, "version")
        _require_value(self.workspace_id, "workspace_id")
        if self.stage_id is not None:
            _require_value(self.stage_id, "stage_id")
        if self.specialist_id is not None:
            _require_value(self.specialist_id, "specialist_id")
        targets = (self.primary, *self.fallbacks)
        if len(targets) != len(set(targets)):
            raise ValueError("routing policy targets must be unique")


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    target: RouteTarget
    policy_id: str
    policy_version: str
    routing_reason: str
    fallback_index: int
    workspace_id: str
    stage_id: str
    specialist_id: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "provider_id": self.target.provider_id,
            "model_id": self.target.model_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "routing_reason": self.routing_reason,
            "fallback_index": self.fallback_index,
            "workspace_id": self.workspace_id,
            "stage_id": self.stage_id,
            "specialist_id": self.specialist_id,
        }


class NoRoutingPolicy(RuntimeError):
    pass


class NoAvailableProvider(RuntimeError):
    pass


class ModelRouter:
    def __init__(
        self,
        *,
        capabilities: ProviderCapabilityRegistry,
        health: ProviderHealthRegistry,
        policies: Collection[RoutingPolicy],
    ) -> None:
        self.capabilities = capabilities
        self.health = health
        self.policies = tuple(policies)
        if not self.policies:
            raise ValueError("at least one routing policy is required")

    def route(
        self,
        package: ExecutionPackage,
        *,
        configured_targets: Collection[RouteTarget] | None = None,
    ) -> RoutingDecision:
        workspace_id = str(package.context.get("workspace_id", "legacy")).strip() or "legacy"
        matching = [
            policy
            for policy in self.policies
            if policy.workspace_id in {"*", workspace_id}
            and policy.stage_id in {None, package.stage_id}
            and policy.specialist_id in {None, package.agent_id}
        ]
        if not matching:
            raise NoRoutingPolicy(
                f"no routing policy for workspace={workspace_id}, stage={package.stage_id}, "
                f"specialist={package.agent_id}"
            )
        policy = sorted(
            matching,
            key=lambda item: (
                -(item.workspace_id == workspace_id),
                -(item.stage_id == package.stage_id),
                -(item.specialist_id == package.agent_id),
                item.policy_id,
                item.version,
            ),
        )[0]

        configured = set(configured_targets) if configured_targets is not None else None
        skipped: list[str] = []
        for index, target in enumerate((policy.primary, *policy.fallbacks)):
            if not self.capabilities.contains(target):
                skipped.append(f"{target.provider_id}/{target.model_id}:unregistered")
                continue
            if configured is not None and target not in configured:
                skipped.append(f"{target.provider_id}/{target.model_id}:unconfigured")
                continue
            health = self.health.get(target)
            if health.availability not in {
                ProviderAvailability.AVAILABLE,
                ProviderAvailability.DEGRADED,
            }:
                skipped.append(
                    f"{target.provider_id}/{target.model_id}:{health.availability.value}"
                )
                continue
            reason = "primary_available"
            if index:
                reason = "fallback_selected_after=" + ",".join(skipped)
            elif health.availability == ProviderAvailability.DEGRADED:
                reason = "primary_degraded_but_available"
            return RoutingDecision(
                target=target,
                policy_id=policy.policy_id,
                policy_version=policy.version,
                routing_reason=reason,
                fallback_index=index,
                workspace_id=workspace_id,
                stage_id=package.stage_id,
                specialist_id=package.agent_id,
            )
        raise NoAvailableProvider(
            f"no available provider for policy {policy.policy_id}@{policy.version}"
        )


class RoutedProviderClient:
    """ProviderClient that selects a configured client for each execution package."""

    def __init__(
        self,
        *,
        router: ModelRouter,
        providers: Mapping[RouteTarget, ProviderClient],
    ) -> None:
        self.router = router
        self.providers = dict(providers)

    def generate(self, package: ExecutionPackage) -> ProviderResponse:
        decision = self.router.route(
            package,
            configured_targets=self.providers.keys(),
        )
        response = self.providers[decision.target].generate(package)
        return ProviderResponse(
            job_id=response.job_id,
            run_id=response.run_id,
            stage_id=response.stage_id,
            output_type=response.output_type,
            content=response.content,
            metadata={
                **dict(response.metadata or {}),
                "routing": decision.to_dict(),
            },
        )


def _require_value(value: str, field_name: str) -> None:
    if not str(value).strip():
        raise ValueError(f"{field_name} must not be empty")
