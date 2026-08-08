import pytest

from runtime.delegation_framework import (
    AgentCapability,
    CapabilityRegistry,
    DelegationEngine,
    DelegationRequest,
)


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry(
        (
            AgentCapability(
                agent_id="research-agent",
                name="Research Agent",
                capabilities=("research",),
            ),
            AgentCapability(
                agent_id="commercial-agent",
                name="Commercial Agent",
                capabilities=("commercial",),
            ),
            AgentCapability(
                agent_id="generalist-agent",
                name="Generalist Agent",
                capabilities=("research", "operations"),
            ),
            AgentCapability(
                agent_id="offline-reviewer",
                name="Offline Reviewer",
                capabilities=("review",),
                available=False,
            ),
        )
    )


def test_assigns_to_available_specialist_capability() -> None:
    engine = DelegationEngine(_registry())
    assignment = engine.assign(
        DelegationRequest(
            task_id="task-1",
            title="Qualify new lead",
            required_capability="commercial",
            priority_score=90,
            context="Review the account and propose the next commercial action.",
        )
    )

    assert assignment.task_id == "task-1"
    assert assignment.agent_id == "commercial-agent"
    assert assignment.capability == "commercial"
    assert assignment.status == "assigned"


def test_prefers_narrower_specialist_for_same_capability() -> None:
    engine = DelegationEngine(_registry())
    assignment = engine.assign(
        DelegationRequest(
            task_id="task-2",
            title="Research account",
            required_capability="research",
            priority_score=70,
            context="Prepare an account brief.",
        )
    )

    assert assignment.agent_id == "research-agent"


def test_assign_many_orders_highest_priority_first() -> None:
    engine = DelegationEngine(_registry())
    assignments = engine.assign_many(
        (
            DelegationRequest(
                task_id="low",
                title="Research category",
                required_capability="research",
                priority_score=30,
                context="Background research.",
            ),
            DelegationRequest(
                task_id="high",
                title="Build follow-up plan",
                required_capability="commercial",
                priority_score=95,
                context="Advance the active opportunity.",
            ),
        )
    )

    assert [assignment.task_id for assignment in assignments] == ["high", "low"]


def test_unavailable_capability_fails_closed() -> None:
    engine = DelegationEngine(_registry())

    with pytest.raises(ValueError, match="no available agent"):
        engine.assign(
            DelegationRequest(
                task_id="review-1",
                title="Review proposal",
                required_capability="review",
                priority_score=80,
                context="Quality-assure the proposal before sending.",
            )
        )


def test_duplicate_task_ids_fail_closed() -> None:
    engine = DelegationEngine(_registry())
    request = DelegationRequest(
        task_id="dup",
        title="Research lead",
        required_capability="research",
        priority_score=50,
        context="Research the lead.",
    )

    with pytest.raises(ValueError, match="duplicate task_id"):
        engine.assign_many((request, request))


def test_duplicate_agent_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicate agent_id"):
        CapabilityRegistry(
            (
                AgentCapability("same", "Agent One", ("research",)),
                AgentCapability("same", "Agent Two", ("commercial",)),
            )
        )


def test_invalid_request_priority_fails_closed() -> None:
    with pytest.raises(ValueError, match="priority_score"):
        DelegationRequest(
            task_id="bad",
            title="Bad request",
            required_capability="operations",
            priority_score=101,
            context="Invalid priority.",
        )
