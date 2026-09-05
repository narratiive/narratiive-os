from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


WorkerAdapter = Callable[[dict[str, Any]], dict[str, Any]]


class WorkerAvailability(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    PLANNED = "planned"


class NoAvailableWorker(RuntimeError):
    pass


class MalformedWorkerOutput(RuntimeError):
    pass


class ProhibitedWorkerSideEffect(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerMetadata:
    worker_id: str
    provider: str
    capabilities: tuple[str, ...]
    availability: WorkerAvailability
    input_forms: tuple[str, ...] = ("json",)
    output_forms: tuple[str, ...] = ("json",)
    side_effect_permissions: tuple[str, ...] = ("preparation",)
    timeout_seconds: int = 90
    max_attempts: int = 1
    model: str = ""
    cost_class: str = "unknown"
    health_reason: str = ""
    dispatch_name: str = ""
    selection_priority: int = 100

    def __post_init__(self) -> None:
        if not self.worker_id.strip() or not self.provider.strip() or not self.capabilities:
            raise ValueError("worker_id, provider and capabilities are required")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("worker capabilities must be unique")
        if self.timeout_seconds <= 0 or self.max_attempts <= 0:
            raise ValueError("worker timeout and max_attempts must be positive")
        allowed = {"none", "preparation", "external_read", "external_write"}
        if not set(self.side_effect_permissions).issubset(allowed):
            raise ValueError("worker side-effect permission is invalid")


@dataclass(frozen=True, slots=True)
class WorkerRegistration:
    metadata: WorkerMetadata
    adapter: WorkerAdapter | None = None


@dataclass(frozen=True, slots=True)
class WorkerSelectionPolicy:
    policy_id: str = "deterministic-default"
    preferred_worker_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkerResolution:
    registration: WorkerRegistration
    capability: str
    policy_id: str
    reason: str

    @property
    def worker_id(self) -> str:
        return self.registration.metadata.worker_id


class CapabilityWorkerRegistry:
    """Resolve workflow capabilities to truthful worker adapters."""

    def __init__(self, registrations: Iterable[WorkerRegistration] = ()) -> None:
        self._registrations: dict[str, WorkerRegistration] = {}
        for registration in registrations:
            self.register(registration)

    def register(self, registration: WorkerRegistration) -> None:
        worker_id = registration.metadata.worker_id
        if worker_id in self._registrations:
            raise ValueError(f"duplicate worker_id: {worker_id}")
        if registration.metadata.availability in {WorkerAvailability.AVAILABLE, WorkerAvailability.DEGRADED}:
            if registration.adapter is None:
                raise ValueError("available workers require an execution adapter")
        self._registrations[worker_id] = registration

    def all(self) -> tuple[WorkerRegistration, ...]:
        return tuple(self._registrations[key] for key in sorted(self._registrations))

    def eligible(self, capability: str, *, side_effect: str = "preparation") -> tuple[WorkerRegistration, ...]:
        return tuple(
            sorted(
                (
                    registration
                    for registration in self._registrations.values()
                    if capability in registration.metadata.capabilities
                    and registration.metadata.availability in {WorkerAvailability.AVAILABLE, WorkerAvailability.DEGRADED}
                    and registration.adapter is not None
                    and side_effect in registration.metadata.side_effect_permissions
                ),
                key=lambda item: (item.metadata.selection_priority, item.metadata.worker_id),
            )
        )

    def resolve(
        self,
        capability: str,
        *,
        side_effect: str = "preparation",
        policy: WorkerSelectionPolicy | None = None,
    ) -> WorkerResolution:
        selection_policy = policy or WorkerSelectionPolicy()
        candidates = self.eligible(capability, side_effect=side_effect)
        if not candidates:
            declared = sorted(
                registration.metadata.worker_id
                for registration in self._registrations.values()
                if capability in registration.metadata.capabilities
            )
            suffix = f"; declared={','.join(declared)}" if declared else ""
            raise NoAvailableWorker(f"no available worker for capability: {capability}{suffix}")
        preferred = {worker_id: index for index, worker_id in enumerate(selection_policy.preferred_worker_ids)}
        chosen = min(
            candidates,
            key=lambda item: (
                preferred.get(item.metadata.worker_id, len(preferred)),
                item.metadata.selection_priority,
                item.metadata.worker_id,
            ),
        )
        reason = "only_eligible_worker" if len(candidates) == 1 else "selected_by_policy"
        return WorkerResolution(chosen, capability, selection_policy.policy_id, reason)

    def execute(
        self,
        resolution: WorkerResolution,
        contract: Mapping[str, Any],
        *,
        side_effect: str = "preparation",
        approval_granted: bool = False,
    ) -> dict[str, Any]:
        metadata = resolution.registration.metadata
        if side_effect not in metadata.side_effect_permissions:
            raise ProhibitedWorkerSideEffect(f"worker {metadata.worker_id} cannot perform {side_effect}")
        if side_effect == "external_write" and not approval_granted:
            raise ProhibitedWorkerSideEffect("external-write worker execution requires explicit approval")
        if resolution.registration.adapter is None:
            raise NoAvailableWorker(f"worker has no execution adapter: {metadata.worker_id}")

        last_error: Exception | None = None
        for attempt in range(1, metadata.max_attempts + 1):
            try:
                returned = resolution.registration.adapter(dict(contract))
                result = _normalise_worker_result(returned)
                if result.get("external_action_taken") is True and side_effect != "external_write":
                    raise ProhibitedWorkerSideEffect("worker claimed a prohibited external action")
                result["worker_execution"] = {
                    "worker_id": metadata.worker_id,
                    "provider": metadata.provider,
                    "capability": resolution.capability,
                    "policy_id": resolution.policy_id,
                    "selection_reason": resolution.reason,
                    "attempt": attempt,
                    "side_effect_classification": side_effect,
                }
                return result
            except (MalformedWorkerOutput, ProhibitedWorkerSideEffect):
                raise
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"worker execution failed after {metadata.max_attempts} attempt(s): {last_error}")


def build_tony_worker_registry(
    dispatchers: Mapping[str, WorkerAdapter],
    environ: Mapping[str, str] | None = None,
) -> CapabilityWorkerRegistry:
    env = os.environ if environ is None else environ
    registrations: list[WorkerRegistration] = []
    claude = dispatchers.get("Claude")
    if claude is not None:
        def claude_preparation_adapter(contract: dict[str, Any]) -> dict[str, Any]:
            if contract.get("worker") == "Claude":
                return claude(contract)
            context = contract.get("workflow_context")
            if not isinstance(context, Mapping):
                raise RuntimeError("generic Claude work requires workflow context")
            expected = context.get("expected_outputs") or []
            instruction = (
                f"Prepare the internal work for workflow {context.get('workflow_id')} "
                f"step {context.get('stage_id')}. Return the required fields: "
                f"{', '.join(str(item) for item in expected)}. "
                f"Satisfy quality contract {context.get('quality_contract')}."
            )
            return claude(
                {
                    "worker": "Claude",
                    "execution_mode": "autonomous_prepare",
                    "eligible": True,
                    "state": "ready_for_autonomous_dispatch",
                    "execution_truth": "not_dispatched",
                    "instruction": instruction,
                    "target": dict(contract),
                }
            )

        registrations.append(
            WorkerRegistration(
                WorkerMetadata(
                    worker_id="claude-anthropic",
                    provider="anthropic",
                    model=str(env.get("TONY_DISPATCH_CLAUDE_MODEL", "")).strip(),
                    capabilities=("strategic_reasoning", "synthesis", "copy_drafting", "structured_data_processing"),
                    availability=WorkerAvailability.AVAILABLE,
                    side_effect_permissions=("preparation",),
                    timeout_seconds=90,
                    max_attempts=1,
                    cost_class="configured_model",
                    dispatch_name="Claude",
                    selection_priority=10,
                ),
                claude_preparation_adapter,
            )
        )

    planned = (
        ("market-research-unavailable", ("market_research", "web_research")),
        ("document-generation-unavailable", ("document_generation", "deck_generation")),
        ("creative-production-unavailable", ("creative_asset_production", "image_generation", "video_generation")),
        ("crm-operations-unavailable", ("crm_operations",)),
        ("email-operations-unavailable", ("email_preparation", "email_sending")),
        ("calendar-operations-unavailable", ("calendar_operations",)),
    )
    for worker_id, capabilities in planned:
        registrations.append(
            WorkerRegistration(
                WorkerMetadata(
                    worker_id=worker_id,
                    provider="unconfigured",
                    capabilities=capabilities,
                    availability=WorkerAvailability.PLANNED,
                    side_effect_permissions=(),
                    health_reason="execution_adapter_not_configured",
                )
            )
        )
    return CapabilityWorkerRegistry(registrations)


def _normalise_worker_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise MalformedWorkerOutput("worker output must be a non-empty object")
    try:
        return json.loads(json.dumps(dict(value), sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise MalformedWorkerOutput("worker output is not JSON-compatible") from exc
