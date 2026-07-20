import unittest

from runtime.execution_package import ExecutionPackage
from runtime.provider import ProviderResponse
from runtime.provider_routing import (
    AmbiguousRoutingPolicy,
    CostClass,
    LatencyClass,
    ModelCapabilities,
    ModelRouter,
    NoAvailableProvider,
    ProviderAvailability,
    ProviderCapabilityRegistry,
    ProviderHealthRecord,
    ProviderHealthRegistry,
    ProviderModelRecord,
    RouteTarget,
    RoutedProviderClient,
    RoutingPolicy,
)


CAPABILITIES = ModelCapabilities(
    reasoning=True,
    long_context=True,
    structured_output=True,
    vision=False,
    tool_use=False,
    latency_class=LatencyClass.STANDARD,
    cost_class=CostClass.MEDIUM,
)


def package(*, workspace_id: str = "legacy", stage_id: str = "research") -> ExecutionPackage:
    return ExecutionPackage(
        schema_version=1,
        job_id="job-1",
        run_id="run-1",
        stage_id=stage_id,
        agent_id="research_analyst",
        agent_version="1.0",
        agent_ref="agents/research.md",
        instructions="Research supplied evidence.",
        input_artifacts=(),
        memory_records=(),
        confidence_scorecard=None,
        context={"workspace_id": workspace_id},
        expected_output_type="completed_research",
    )


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, execution_package: ExecutionPackage) -> ProviderResponse:
        self.calls += 1
        return ProviderResponse(
            job_id=execution_package.job_id,
            run_id=execution_package.run_id,
            stage_id=execution_package.stage_id,
            output_type=execution_package.expected_output_type,
            content="evidence-backed output",
            metadata={"request_id": "safe-request-id"},
        )


class ProviderRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.primary = RouteTarget("primary-provider", "reasoning-model")
        self.fallback = RouteTarget("fallback-provider", "text-model")
        self.capabilities = ProviderCapabilityRegistry(
            (
                ProviderModelRecord(
                    self.primary.provider_id,
                    self.primary.model_id,
                    CAPABILITIES,
                ),
                ProviderModelRecord(
                    self.fallback.provider_id,
                    self.fallback.model_id,
                    ModelCapabilities(
                        reasoning=False,
                        long_context=False,
                        structured_output=True,
                        vision=False,
                        tool_use=False,
                        latency_class=LatencyClass.FAST,
                        cost_class=CostClass.LOW,
                    ),
                ),
            )
        )
        self.health = ProviderHealthRegistry()

    def test_capability_registry_records_declared_model_features(self) -> None:
        record = self.capabilities.get(self.primary)
        self.assertTrue(record.capabilities.reasoning)
        self.assertTrue(record.capabilities.long_context)
        self.assertTrue(record.capabilities.structured_output)
        self.assertFalse(record.capabilities.vision)
        self.assertFalse(record.capabilities.tool_use)
        self.assertEqual(record.capabilities.latency_class, LatencyClass.STANDARD)
        self.assertEqual(record.capabilities.cost_class, CostClass.MEDIUM)

    def test_workspace_stage_and_specialist_policy_is_more_specific(self) -> None:
        self.health.set(
            ProviderHealthRecord(self.primary, ProviderAvailability.AVAILABLE)
        )
        self.health.set(
            ProviderHealthRecord(self.fallback, ProviderAvailability.AVAILABLE)
        )
        router = ModelRouter(
            capabilities=self.capabilities,
            health=self.health,
            policies=(
                RoutingPolicy(
                    policy_id="default",
                    version="1",
                    primary=self.fallback,
                ),
                RoutingPolicy(
                    policy_id="rave-research",
                    version="3",
                    workspace_id="rave",
                    stage_id="research",
                    specialist_id="research_analyst",
                    primary=self.primary,
                ),
            ),
        )

        decision = router.route(package(workspace_id="rave"))

        self.assertEqual(decision.target, self.primary)
        self.assertEqual(decision.policy_id, "rave-research")
        self.assertEqual(decision.policy_version, "3")

    def test_equally_specific_policies_fail_closed(self) -> None:
        self.health.set(
            ProviderHealthRecord(self.primary, ProviderAvailability.AVAILABLE)
        )
        router = ModelRouter(
            capabilities=self.capabilities,
            health=self.health,
            policies=(
                RoutingPolicy(
                    policy_id="research-a",
                    version="1",
                    workspace_id="rave",
                    stage_id="research",
                    primary=self.primary,
                ),
                RoutingPolicy(
                    policy_id="research-b",
                    version="2",
                    workspace_id="rave",
                    stage_id="research",
                    primary=self.primary,
                ),
            ),
        )

        with self.assertRaisesRegex(
            AmbiguousRoutingPolicy,
            "multiple equally specific routing policies",
        ):
            router.route(package(workspace_id="rave"))

    def test_policy_ids_and_versions_never_break_specificity_ties(self) -> None:
        self.health.set(
            ProviderHealthRecord(self.primary, ProviderAvailability.AVAILABLE)
        )
        older_lexical_policy = RoutingPolicy(
            policy_id="aaa-policy",
            version="1",
            primary=self.primary,
            stage_id="research",
        )
        newer_lexical_policy = RoutingPolicy(
            policy_id="zzz-policy",
            version="999",
            primary=self.primary,
            stage_id="research",
        )
        for policies in (
            (older_lexical_policy, newer_lexical_policy),
            (newer_lexical_policy, older_lexical_policy),
        ):
            with self.subTest(policy_order=[item.policy_id for item in policies]):
                router = ModelRouter(
                    capabilities=self.capabilities,
                    health=self.health,
                    policies=policies,
                )
                with self.assertRaises(AmbiguousRoutingPolicy):
                    router.route(package())

    def test_fallback_selection_is_deterministic_and_auditable(self) -> None:
        self.health.set(
            ProviderHealthRecord(
                self.primary,
                ProviderAvailability.UNAVAILABLE,
                "scheduled_maintenance",
            )
        )
        self.health.set(
            ProviderHealthRecord(self.fallback, ProviderAvailability.AVAILABLE)
        )
        router = ModelRouter(
            capabilities=self.capabilities,
            health=self.health,
            policies=(
                RoutingPolicy(
                    policy_id="research-policy",
                    version="2",
                    primary=self.primary,
                    fallbacks=(self.fallback,),
                    stage_id="research",
                ),
            ),
        )

        first = router.route(package())
        second = router.route(package())

        self.assertEqual(first, second)
        self.assertEqual(first.target, self.fallback)
        self.assertEqual(first.fallback_index, 1)
        self.assertIn("primary-provider/reasoning-model:unavailable", first.routing_reason)

    def test_unknown_health_is_not_routable(self) -> None:
        router = ModelRouter(
            capabilities=self.capabilities,
            health=self.health,
            policies=(RoutingPolicy("default", "1", self.primary),),
        )
        with self.assertRaises(NoAvailableProvider):
            router.route(package())

    def test_routed_client_records_selection_without_changing_response_contract(self) -> None:
        self.health.set(
            ProviderHealthRecord(self.primary, ProviderAvailability.AVAILABLE)
        )
        router = ModelRouter(
            capabilities=self.capabilities,
            health=self.health,
            policies=(RoutingPolicy("default", "1", self.primary),),
        )
        provider = FakeProvider()
        client = RoutedProviderClient(
            router=router,
            providers={self.primary: provider},
        )

        response = client.generate(package())

        self.assertEqual(provider.calls, 1)
        self.assertEqual(response.content, "evidence-backed output")
        self.assertEqual(response.metadata["routing"]["provider_id"], "primary-provider")
        self.assertEqual(response.metadata["routing"]["policy_version"], "1")


if __name__ == "__main__":
    unittest.main()
