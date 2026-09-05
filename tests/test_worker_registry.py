from __future__ import annotations

import unittest

from runtime.worker_registry import (
    CapabilityWorkerRegistry,
    MalformedWorkerOutput,
    NoAvailableWorker,
    ProhibitedWorkerSideEffect,
    WorkerAvailability,
    WorkerMetadata,
    WorkerRegistration,
    WorkerSelectionPolicy,
    build_tony_worker_registry,
)


def _registration(
    worker_id: str,
    adapter,
    *,
    capabilities=("strategic_reasoning",),
    availability=WorkerAvailability.AVAILABLE,
    priority=100,
    max_attempts=1,
    side_effect_permissions=("preparation",),
) -> WorkerRegistration:
    return WorkerRegistration(
        WorkerMetadata(
            worker_id=worker_id,
            provider="test-provider",
            capabilities=capabilities,
            availability=availability,
            selection_priority=priority,
            max_attempts=max_attempts,
            side_effect_permissions=side_effect_permissions,
        ),
        adapter,
    )


class CapabilityWorkerRegistryTests(unittest.TestCase):
    def test_operational_claude_resolves_by_capability_with_truthful_metadata(self) -> None:
        adapter = lambda contract: {"verified": True, "work_product": "safe internal work"}
        registry = build_tony_worker_registry(
            {"Claude": adapter},
            {"TONY_DISPATCH_CLAUDE_MODEL": "configured-model"},
        )
        resolution = registry.resolve("strategic_reasoning")
        metadata = resolution.registration.metadata
        self.assertEqual(metadata.worker_id, "claude-anthropic")
        self.assertEqual(metadata.provider, "anthropic")
        self.assertEqual(metadata.model, "configured-model")
        self.assertEqual(metadata.dispatch_name, "Claude")
        self.assertEqual(metadata.side_effect_permissions, ("preparation",))

    def test_generic_workflow_contract_is_adapted_to_safe_claude_dispatch(self) -> None:
        received = []

        def claude(contract):
            received.append(contract)
            return {"draft": "prepared"}

        registry = build_tony_worker_registry({"Claude": claude}, {})
        result = registry.execute(
            registry.resolve("synthesis"),
            {
                "brief": "safe",
                "workflow_context": {
                    "workflow_id": "discovery-preparation",
                    "stage_id": "prepare",
                    "expected_outputs": ["draft"],
                    "quality_contract": "draft-quality",
                },
            },
        )
        self.assertEqual(result["draft"], "prepared")
        self.assertEqual(received[0]["worker"], "Claude")
        self.assertEqual(received[0]["execution_mode"], "autonomous_prepare")
        self.assertEqual(received[0]["execution_truth"], "not_dispatched")
        self.assertEqual(received[0]["target"]["brief"], "safe")

    def test_planned_capability_is_visible_but_not_routable(self) -> None:
        registry = build_tony_worker_registry({})
        declared = {item.metadata.worker_id: item.metadata for item in registry.all()}
        self.assertEqual(declared["creative-production-unavailable"].availability, WorkerAvailability.PLANNED)
        with self.assertRaisesRegex(NoAvailableWorker, "creative_asset_production"):
            registry.resolve("creative_asset_production")

    def test_existing_research_engine_adapter_makes_research_capability_operational(self) -> None:
        adapter = lambda contract: {"evidence_pack": {"records": []}}
        registry = build_tony_worker_registry({}, research_adapter=adapter)

        resolution = registry.resolve("market_research", side_effect="external_read")

        self.assertEqual(resolution.worker_id, "narratiive-research-engine")
        self.assertEqual(resolution.registration.metadata.provider, "narratiive-os")
        self.assertEqual(resolution.registration.metadata.side_effect_permissions, ("external_read",))

    def test_multiple_workers_use_explicit_policy_then_stable_default(self) -> None:
        registry = CapabilityWorkerRegistry(
            (
                _registration("worker-b", lambda contract: {"result": "b"}, priority=20),
                _registration("worker-a", lambda contract: {"result": "a"}, priority=10),
            )
        )
        self.assertEqual(registry.resolve("strategic_reasoning").worker_id, "worker-a")
        selected = registry.resolve(
            "strategic_reasoning",
            policy=WorkerSelectionPolicy("prefer-b", ("worker-b",)),
        )
        self.assertEqual(selected.worker_id, "worker-b")
        self.assertEqual(selected.reason, "selected_by_policy")

    def test_malformed_output_fails_at_worker_boundary(self) -> None:
        registry = CapabilityWorkerRegistry((_registration("worker", lambda contract: "not-json"),))
        with self.assertRaises(MalformedWorkerOutput):
            registry.execute(registry.resolve("strategic_reasoning"), {})

        non_json = CapabilityWorkerRegistry(
            (_registration("non-json", lambda contract: {"value": object()}),)
        )
        with self.assertRaises(MalformedWorkerOutput):
            non_json.execute(non_json.resolve("strategic_reasoning"), {})

    def test_bounded_retry_succeeds_and_records_attempt(self) -> None:
        calls = []

        def flaky(contract):
            calls.append(contract)
            if len(calls) == 1:
                raise RuntimeError("transient")
            return {"verified": True, "work_product": "prepared"}

        registry = CapabilityWorkerRegistry((_registration("worker", flaky, max_attempts=2),))
        result = registry.execute(registry.resolve("strategic_reasoning"), {"safe": True})
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["worker_execution"]["attempt"], 2)

    def test_prohibited_external_execution_is_blocked_before_and_after_adapter(self) -> None:
        calls = []
        registry = CapabilityWorkerRegistry(
            (_registration("worker", lambda contract: calls.append(contract) or {"verified": True}),)
        )
        resolution = registry.resolve("strategic_reasoning")
        with self.assertRaises(ProhibitedWorkerSideEffect):
            registry.execute(resolution, {}, side_effect="external_write", approval_granted=True)
        self.assertEqual(calls, [])

        claiming = CapabilityWorkerRegistry(
            (_registration("claiming", lambda contract: {"verified": True, "external_action_taken": True}),)
        )
        with self.assertRaisesRegex(ProhibitedWorkerSideEffect, "claimed a prohibited external action"):
            claiming.execute(claiming.resolve("strategic_reasoning"), {})


if __name__ == "__main__":
    unittest.main()
