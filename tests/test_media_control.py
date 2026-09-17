from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from runtime.campaign_engine import CampaignIdentity
from runtime.execution_journal import ExecutionJournal
from runtime.media_control import (
    ConnectionHealth,
    CanonicalMediaPlan,
    CreativePlatformMapping,
    FixtureTransport,
    GoogleReadOnlyAdapter,
    MalformedProviderResponse,
    MediaAuthority,
    MediaConfigurationError,
    MediaControlService,
    MediaMutationDisabled,
    MediaPolicyEngine,
    MediaProvider,
    MediaProviderError,
    MetaReadOnlyAdapter,
    PreLaunchValidator,
    ProviderConfiguration,
    ProviderObjectMapping,
    TikTokReadOnlyAdapter,
)
from runtime.tony_command_service import CommandResponse
from runtime.tony_media_commands import TonyMediaCommandService


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "northstar_media"


def identity() -> CampaignIdentity:
    return CampaignIdentity(
        workspace_id="test-northstar-workspace",
        client_id="northstar-test-co",
        brand_id="northstar-test-brand",
        market_ids=("gb",),
        product_ids=("northstar-test-product",),
        campaign_id="northstar-test-autumn-growth",
    )


def response(provider: MediaProvider) -> dict:
    return json.loads((FIXTURES / f"{provider.value}.json").read_text(encoding="utf-8"))


def adapter(provider: MediaProvider, payload=None, *, operation="get_performance"):
    configuration = ProviderConfiguration(
        provider=provider,
        account_id=f"test-{provider.value}-account",
        credential_env_names=(f"TEST_{provider.value.upper()}_TOKEN",),
        timezone_name="Europe/London",
        currency="GBP",
    )
    classes = {
        MediaProvider.META: MetaReadOnlyAdapter,
        MediaProvider.TIKTOK: TikTokReadOnlyAdapter,
        MediaProvider.GOOGLE: GoogleReadOnlyAdapter,
    }
    return classes[provider](
        configuration,
        FixtureTransport({operation: response(provider) if payload is None else payload}),
        environment={f"TEST_{provider.value.upper()}_TOKEN": "fixture-only"},
    )


def mapping(provider: MediaProvider) -> ProviderObjectMapping:
    return ProviderObjectMapping(
        provider=provider,
        account_id=f"test-{provider.value}-account",
        campaign_id=f"test-{provider.value}-campaign",
        ad_group_ids=(f"test-{provider.value}-group",),
        ad_ids=(f"test-{provider.value}-ad",),
        creative_ids=(f"test-{provider.value}-creative",),
    )


class _Fallback:
    mission_control_loader = None
    github_configured = False

    def execute(self, command, objects):
        return CommandResponse("fallback", "ready", "fallback", {})


class MediaControlTests(unittest.TestCase):
    def test_adapter_contract_reads_and_preserves_native_ids(self):
        for provider in MediaProvider:
            item = adapter(provider)
            payload = item.get_performance("native-campaign-id", "2026-09-10", "2026-09-17")
            self.assertEqual(payload["currency"], "GBP")
            self.assertEqual(item.transport.calls[0][2]["campaign_id"], "native-campaign-id")

    def test_configuration_validation_fails_closed(self):
        configuration = ProviderConfiguration(
            provider=MediaProvider.META,
            account_id="",
            credential_env_names=("MISSING_TOKEN",),
            timezone_name="",
        )
        with self.assertRaises(MediaConfigurationError):
            MetaReadOnlyAdapter(configuration, FixtureTransport({}), environment={})

    def test_every_provider_write_method_is_disabled(self):
        for provider in MediaProvider:
            item = adapter(provider)
            for operation in (
                "create_campaign",
                "create_ad_group",
                "create_ad",
                "upload_creative",
                "update_budget",
                "pause_ad",
                "resume_ad",
                "activate_campaign",
            ):
                with self.assertRaises(MediaMutationDisabled, msg=f"{provider.value}:{operation}"):
                    getattr(item, operation)({"unsafe": True})
            self.assertEqual(len(item.transport.calls), 0)

    def test_policy_allows_only_read_analyse_recommend(self):
        policy = MediaPolicyEngine()
        for authority in (MediaAuthority.READ, MediaAuthority.ANALYSE, MediaAuthority.RECOMMEND):
            policy.authorize(authority, f"test_{authority.value}")
        for authority in (
            MediaAuthority.DRAFT,
            MediaAuthority.EXECUTE_WITHIN_LIMITS,
            MediaAuthority.EXECUTE_WITH_APPROVAL,
            MediaAuthority.PROHIBITED,
        ):
            with self.assertRaises(MediaMutationDisabled):
                policy.authorize(authority, "operation")

    def test_normalisation_retains_null_metrics_and_attribution(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MediaControlService(
                {MediaProvider.GOOGLE: adapter(MediaProvider.GOOGLE)},
                ExecutionJournal(directory),
            )
            snapshot = service.ingest(
                identity=identity(),
                provider_mapping=mapping(MediaProvider.GOOGLE),
                period_start="2026-09-10T00:00:00Z",
                period_end="2026-09-17T00:00:00Z",
                request_id="northstar-google-null",
                tony_request="How is Northstar performing?",
            )
            conversions = snapshot.metric("conversions")
            self.assertIsNotNone(conversions)
            self.assertFalse(conversions.available)
            self.assertIsNone(conversions.value)
            self.assertIn("Google Ads", conversions.attribution_context)

    def test_malformed_response_is_quarantined_and_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MediaControlService(
                {MediaProvider.META: adapter(MediaProvider.META, {"metrics": {}})},
                ExecutionJournal(directory),
            )
            with self.assertRaises(MalformedProviderResponse):
                service.ingest(
                    identity=identity(), provider_mapping=mapping(MediaProvider.META),
                    period_start="a", period_end="b", request_id="northstar-malformed",
                    tony_request="test malformed",
                )
            records = service.journal.read_all()
            self.assertEqual(records[-1].status, "failed")
            self.assertIsNone(records[-1].metadata["after_state"])

    def test_invalid_period_currency_and_timezone_are_rejected(self):
        invalid_values = (
            {"period_start": "not-a-date"},
            {"period_start": "2026-09-18T00:00:00Z", "period_end": "2026-09-17T00:00:00Z"},
            {"currency": "UNKNOWN"},
            {"timezone": ""},
        )
        for index, changes in enumerate(invalid_values):
            payload = {**response(MediaProvider.META), **changes}
            with tempfile.TemporaryDirectory() as directory:
                service = MediaControlService(
                    {MediaProvider.META: adapter(MediaProvider.META, payload)},
                    ExecutionJournal(directory),
                )
                with self.assertRaises(MalformedProviderResponse):
                    service.ingest(
                        identity=identity(), provider_mapping=mapping(MediaProvider.META),
                        period_start="a", period_end="b", request_id=f"northstar-invalid-context-{index}",
                        tony_request="validate provider context",
                    )

    def test_provider_failure_and_expired_credential_fail_closed(self):
        for error in (MediaProviderError("api unavailable"), MediaProviderError("credential expired")):
            with tempfile.TemporaryDirectory() as directory:
                service = MediaControlService(
                    {MediaProvider.TIKTOK: adapter(MediaProvider.TIKTOK, error)},
                    ExecutionJournal(directory),
                )
                with self.assertRaises(MediaProviderError):
                    service.ingest(
                        identity=identity(), provider_mapping=mapping(MediaProvider.TIKTOK),
                        period_start="a", period_end="b", request_id=f"northstar-{str(error).replace(' ', '-')}",
                        tony_request="provider health check",
                    )
                self.assertEqual(service.diagnostics()["tiktok"]["health"], ConnectionHealth.OFFLINE.value)

    def test_duplicate_request_is_idempotent_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            transport_adapter = adapter(MediaProvider.META)
            service = MediaControlService({MediaProvider.META: transport_adapter}, ExecutionJournal(directory))
            arguments = dict(
                identity=identity(), provider_mapping=mapping(MediaProvider.META),
                period_start="2026-09-10T00:00:00Z", period_end="2026-09-17T00:00:00Z",
                request_id="northstar-idempotent", tony_request="sync Northstar",
            )
            first = service.ingest(**arguments)
            restarted = MediaControlService({MediaProvider.META: transport_adapter}, ExecutionJournal(directory))
            second = restarted.ingest(**arguments)
            self.assertEqual(first.to_dict(), second.to_dict())
            self.assertEqual(len(transport_adapter.transport.calls), 1)
            self.assertEqual(len(restarted.journal.read_all()), 1)

    def test_creative_mapping_and_recommendations(self):
        creative = CreativePlatformMapping(
            narratiive_asset_id="NORTHSTAR-GB-CW01-VID-004",
            campaign_world_id="northstar-cw-01",
            creative_territory="Own the next horizon",
            format="vertical_video",
            hook="Your next market is closer than it looks",
            message="Confident expansion",
            audience="UK growth leaders",
            provider=MediaProvider.TIKTOK,
            placement="for_you_feed",
            provider_creative_ids=("test-tiktok-creative",),
            provider_ad_ids=("test-tiktok-ad",),
        )
        with tempfile.TemporaryDirectory() as directory:
            service = MediaControlService(
                {MediaProvider.TIKTOK: adapter(MediaProvider.TIKTOK)},
                ExecutionJournal(directory),
            )
            snapshot = service.ingest(
                identity=identity(), provider_mapping=mapping(MediaProvider.TIKTOK),
                period_start="2026-09-10T00:00:00Z", period_end="2026-09-17T00:00:00Z",
                request_id="northstar-creative", tony_request="creative performance",
                creative_mappings=(creative,),
            )
            categories = {item.category for item in service.analyse((snapshot,))}
            self.assertEqual(snapshot.creative_mappings[0].narratiive_asset_id, "NORTHSTAR-GB-CW01-VID-004")
            self.assertTrue({"creative_rejected", "overspend_risk", "poor_performer"}.issubset(categories))

    def test_normal_campaign_returns_no_action_required(self):
        payload = response(MediaProvider.META)
        payload["metrics"] = {**payload["metrics"], "spend": "2000", "roas": "2.0"}
        with tempfile.TemporaryDirectory() as directory:
            service = MediaControlService(
                {MediaProvider.META: adapter(MediaProvider.META, payload)},
                ExecutionJournal(directory),
            )
            snapshot = service.ingest(
                identity=identity(), provider_mapping=mapping(MediaProvider.META),
                period_start=payload["period_start"], period_end=payload["period_end"],
                request_id="northstar-normal-campaign", tony_request="check normal campaign",
            )
            self.assertEqual(service.analyse((snapshot,)), ())

    def test_missing_provider_and_creative_mappings_block(self):
        with self.assertRaisesRegex(Exception, "account_id"):
            ProviderObjectMapping(
                provider=MediaProvider.META, account_id="", campaign_id="northstar-test-campaign"
            )
        with self.assertRaisesRegex(Exception, "native provider ID"):
            CreativePlatformMapping(
                narratiive_asset_id="NORTHSTAR-GB-CW01-VID-004",
                campaign_world_id="northstar-test-world-a", creative_territory="territory",
                format="video", hook="hook", message="message", audience="audience",
                provider=MediaProvider.META, placement="reels",
                provider_creative_ids=(), provider_ad_ids=(),
            )

    def test_budget_currency_timezone_and_prerequisite_validation(self):
        validator = PreLaunchValidator()
        blocked = validator.validate(
            approved_client_budget=Decimal("10000"),
            platform_budgets={MediaProvider.META: Decimal("5000"), MediaProvider.TIKTOK: Decimal("6000")},
            prerequisites={"approved_strategy": True, "approved_media_plan": False, "tracking": False},
            currencies=("GBP",),
            timezones=("Europe/London",),
        )
        self.assertFalse(blocked.ok)
        self.assertIn("sum of platform authorised budgets exceeds approved client budget", blocked.errors)
        invalid_context = validator.validate(
            approved_client_budget=Decimal("100"),
            platform_budgets={}, prerequisites={}, currencies=("UNKNOWN",), timezones=("",),
        )
        self.assertFalse(invalid_context.ok)

    def test_canonical_media_plan_binds_strategy_budget_and_human_gates(self):
        with self.assertRaisesRegex(Exception, "exceeds approved client budget"):
            CanonicalMediaPlan(
                identity=identity(), plan_id="northstar-test-media-plan", version="1.0",
                checksum="northstar-test-media-plan-checksum", objective="qualified_leads",
                audience_ids=("northstar-test-audience",), approved_client_budget=Decimal("10000"),
                platform_budgets={MediaProvider.META: Decimal("6000"), MediaProvider.TIKTOK: Decimal("5000")},
                currency="GBP", start_at="2026-10-01T00:00:00+01:00", end_at="2026-10-31T23:59:59Z",
                kpis=("cpa",), tracking_references=("northstar-test-conversion",),
            )

    def test_approval_does_not_enable_phase_one_mutation_and_audit_is_hash_chained(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MediaControlService({}, ExecutionJournal(directory))
            with self.assertRaises(MediaMutationDisabled):
                service.prohibit_mutation(
                    identity=identity(), provider=MediaProvider.META,
                    operation="activate_campaign", request_id="northstar-no-write",
                    approval_id="test-matt-approval",
                )
            record = service.journal.read_all()[0]
            self.assertEqual(record.status, "blocked")
            self.assertEqual(record.metadata["approval_id"], "test-matt-approval")
            self.assertEqual(service.journal.verify()["ok"], True)

    def test_tony_reports_media_without_external_action(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MediaControlService(
                {provider: adapter(provider) for provider in MediaProvider},
                ExecutionJournal(directory),
            )
            for provider in MediaProvider:
                service.ingest(
                    identity=identity(), provider_mapping=mapping(provider),
                    period_start="2026-09-10T00:00:00Z", period_end="2026-09-17T00:00:00Z",
                    request_id=f"northstar-tony-{provider.value}", tony_request="Northstar 7d",
                )
            tony = TonyMediaCommandService(_Fallback(), service)
            report = tony.execute("/media northstar-test-co 7d", ())
            self.assertEqual(report.status, "attention_required")
            self.assertEqual(report.data["total_spend"], "9500")
            self.assertFalse(report.data["external_action_taken"])
            integrations = tony.execute("/media-integrations", ())
            self.assertEqual(integrations.status, "healthy")
            health = tony.execute("/health", ())
            self.assertIn("media_integrations", health.data)


if __name__ == "__main__":
    unittest.main()
