from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

Capability = Literal[
    "research",
    "commercial",
    "client_service",
    "content",
    "operations",
    "review",
]
AssignmentStatus = Literal["assigned", "in_progress", "completed", "blocked", "failed"]


@dataclass(frozen=True, slots=True)
class AgentCapability:
    agent_id: str
    name: str
    capabilities: tuple[Capability, ...]
    available: bool = True

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("agent_id is required")
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.capabilities:
            raise ValueError("at least one capability is required")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("duplicate capabilities are not allowed")


@dataclass(frozen=True, slots=True)
class DelegationRequest:
    task_id: str
    title: str
    required_capability: Capability
    priority_score: int
    context: str

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        if not self.title.strip():
            raise ValueError("title is required")
        if not self.context.strip():
            raise ValueError("context is required")
        if not 0 <= self.priority_score <= 100:
            raise ValueError("priority_score must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class DelegatedAssignment:
    task_id: str
    agent_id: str
    agent_name: str
    capability: Capability
    priority_score: int
    status: AssignmentStatus = "assigned"


class CapabilityRegistry:
    def __init__(self, agents: Iterable[AgentCapability]) -> None:
        self._agents = tuple(agents)
        ids = [agent.agent_id for agent in self._agents]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate agent_id")

    def available_for(self, capability: Capability) -> tuple[AgentCapability, ...]:
        return tuple(
            sorted(
                (
                    agent
                    for agent in self._agents
                    if agent.available and capability in agent.capabilities
                ),
                key=lambda agent: (len(agent.capabilities), agent.agent_id),
            )
        )


class DelegationEngine:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def assign(self, request: DelegationRequest) -> DelegatedAssignment:
        candidates = self._registry.available_for(request.required_capability)
        if not candidates:
            raise ValueError(
                f"no available agent for capability: {request.required_capability}"
            )
        agent = candidates[0]
        return DelegatedAssignment(
            task_id=request.task_id,
            agent_id=agent.agent_id,
            agent_name=agent.name,
            capability=request.required_capability,
            priority_score=request.priority_score,
        )

    def assign_many(
        self,
        requests: Iterable[DelegationRequest],
    ) -> tuple[DelegatedAssignment, ...]:
        items = tuple(requests)
        task_ids = [item.task_id for item in items]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("duplicate task_id")

        ordered = sorted(items, key=lambda item: (-item.priority_score, item.task_id))
        return tuple(self.assign(item) for item in ordered)
