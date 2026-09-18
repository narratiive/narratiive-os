from __future__ import annotations

import unittest
from typing import Any

from runtime.media_control import MediaMutationDisabled, MediaProvider, ProviderConfiguration
from runtime.media_provider_transports import (
    GoogleAdsReadTransport,
    JSONResponse,
    MediaHTTPError,
    MetaMarketingReadTransport,
    TikTokBusinessReadTransport,
    build_configured_media_adapters,
)


class FakeHTTP:
    def __init__(self, responses=()) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method, url, *, headers=None, query=None, body=None, form=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "query": dict(query or {}),
                "body": dict(body or {}) if body is not None else None,
                "form": dict(form or {}) if form is not None else None,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def configuration(provider: MediaProvider) -> ProviderConfiguration:
    credentials = {
        MediaProvider.META: ("META_ACCESS_TOKEN",),
        MediaProvider.TIKTOK: ("TIKTOK_ACCESS_TOKEN",),
        MediaProvider.GOOGLE: ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN"),
    }
    account_ids = {
        MediaProvider.META: "123",
        MediaProvider.TIKTOK: "456",
        MediaProvider.GOOGLE: "123-456-7890",
    }
    return ProviderConfiguration(
        provider=provider,
        account_id=account_ids[provider],
        manager_account_id="987-654-3210" if provider is MediaProvider.GOOGLE else "",
        credential_env_names=credentials[provider],
        timezone_name="Europe/London",
        currency="GBP",
    )


class MediaProviderTransportTests(unittest.TestCase):
    def test_factory_builds_only_complete_explicitly_versioned_read_adapters(self) -> None:
        environment = {
            "META_ACCESS_TOKEN": "meta-secret",
            "META_ACCOUNT_ID": "123",
            "META_TIMEZONE": "Europe/London",
            "META_CURRENCY": "GBP",
            "META_GRAPH_API_VERSION": "v24.0",
            "TIKTOK_ACCESS_TOKEN": "tiktok-secret",
            "TIKTOK_ACCOUNT_ID": "456",
            "TIKTOK_TIMEZONE": "Europe/London",
            "TIKTOK_CURRENCY": "GBP",
            # Google is intentionally incomplete and must not be partially enabled.
            "GOOGLE_ADS_CLIENT_ID": "client",
        }
        http = FakeHTTP()
        adapters = build_configured_media_adapters(environment, http=http)
        self.assertEqual(set(adapters), {MediaProvider.META, MediaProvider.TIKTOK})
        self.assertEqual(http.calls, [])

    def test_meta_performance_is_translated_without_inventing_unavailable_metrics(self) -> None:
        http = FakeHTTP(
            (
                JSONResponse(200, {}, {"id": "meta-campaign", "effective_status": "ACTIVE", "daily_budget": "500000"}),
                JSONResponse(
                    200,
                    {},
                    {
                        "data": [
                            {
                                "spend": "1250.50",
                                "impressions": "100000",
                                "reach": "65000",
                                "frequency": "1.53",
                                "cpm": "12.505",
                                "clicks": "2000",
                                "ctr": "2",
                                "cpc": "0.62525",
                                "actions": [{"action_type": "lead", "value": "50"}],
                                "action_values": [{"action_type": "purchase", "value": "5000"}],
                                "cost_per_action_type": [{"action_type": "lead", "value": "25.01"}],
                            }
                        ]
                    },
                ),
            )
        )
        transport = MetaMarketingReadTransport(
            configuration(MediaProvider.META), "meta-secret", http, graph_version="v24.0"
        )
        result = transport.request(
            MediaProvider.META,
            "get_performance",
            {
                "campaign_id": "meta-campaign",
                "period_start": "2026-09-10T00:00:00Z",
                "period_end": "2026-09-17T00:00:00Z",
            },
        )
        self.assertEqual(result["metrics"]["budget"], "5000")
        self.assertEqual(result["metrics"]["conversions"], "50")
        self.assertEqual(result["metrics"]["video_views"], None)
        self.assertEqual(result["tracking_status"], "unknown")
        self.assertEqual(http.calls[1]["query"]["level"], "campaign")

    def test_tiktok_performance_uses_header_token_and_integrated_report(self) -> None:
        http = FakeHTTP(
            (
                JSONResponse(200, {}, {"code": 0, "data": {"list": [{"campaign_id": "77", "budget": "4000", "secondary_status": "CAMPAIGN_STATUS_ENABLE"}]}}),
                JSONResponse(200, {}, {"code": 0, "data": {"list": [{"metrics": {"spend": "900", "impressions": "120000", "clicks": "3600", "conversion": "45", "total_purchase_value": "2700", "purchase_roas": "3"}}]}}),
            )
        )
        transport = TikTokBusinessReadTransport(configuration(MediaProvider.TIKTOK), "tiktok-secret", http)
        result = transport.request(
            MediaProvider.TIKTOK,
            "get_performance",
            {"campaign_id": "77", "period_start": "2026-09-10T00:00:00Z", "period_end": "2026-09-17T00:00:00Z"},
        )
        self.assertEqual(result["metrics"]["roas"], "3")
        self.assertEqual(http.calls[0]["headers"]["Access-Token"], "tiktok-secret")
        self.assertNotIn("tiktok-secret", http.calls[0]["url"])
        self.assertTrue(http.calls[1]["url"].endswith("/report/integrated/get/"))

    def test_google_performance_refreshes_oauth_and_uses_search_stream(self) -> None:
        http = FakeHTTP(
            (
                JSONResponse(200, {}, {"access_token": "short-lived-access"}),
                JSONResponse(
                    200,
                    {},
                    [
                        {
                            "results": [
                                {
                                    "campaign": {"id": "99", "status": "ENABLED"},
                                    "campaignBudget": {"amountMicros": "5000000000"},
                                    "metrics": {
                                        "costMicros": "1250000000",
                                        "impressions": "100000",
                                        "clicks": "3000",
                                        "ctr": "0.03",
                                        "averageCpc": "416666",
                                        "averageCpm": "12500000",
                                        "conversions": "40",
                                        "conversionsValue": "3750",
                                        "costPerConversion": "31250000",
                                    },
                                }
                            ]
                        }
                    ],
                ),
            )
        )
        transport = GoogleAdsReadTransport(
            configuration(MediaProvider.GOOGLE),
            client_id="oauth-client", client_secret="oauth-secret", refresh_token="refresh-secret",
            http=http, api_version="v25",
        )
        result = transport.request(
            MediaProvider.GOOGLE,
            "get_performance",
            {"campaign_id": "99", "period_start": "2026-09-10T00:00:00Z", "period_end": "2026-09-17T00:00:00Z"},
        )
        self.assertEqual(http.calls[0]["form"]["grant_type"], "refresh_token")
        self.assertEqual(http.calls[1]["headers"]["Authorization"], "Bearer short-lived-access")
        self.assertEqual(http.calls[1]["headers"]["login-customer-id"], "9876543210")
        self.assertTrue(http.calls[1]["url"].endswith("/v25/customers/1234567890/googleAds:searchStream"))
        self.assertEqual(result["metrics"]["spend"], "1250")
        self.assertEqual(result["metrics"]["ctr"], "3.00")
        self.assertEqual(result["metrics"]["roas"], "3")
        self.assertIsNone(result["metrics"]["reach"])

    def test_write_methods_remain_blocked_without_network_after_live_factory(self) -> None:
        environment = {
            "META_ACCESS_TOKEN": "meta-secret",
            "META_ACCOUNT_ID": "123",
            "META_TIMEZONE": "Europe/London",
            "META_CURRENCY": "GBP",
            "META_GRAPH_API_VERSION": "v24.0",
        }
        http = FakeHTTP()
        adapter = build_configured_media_adapters(environment, http=http)[MediaProvider.META]
        with self.assertRaises(MediaMutationDisabled):
            adapter.activate_campaign("unsafe")
        self.assertEqual(http.calls, [])

    def test_provider_error_never_contains_secret_or_response_body(self) -> None:
        secret = "super-secret-token"
        http = FakeHTTP((JSONResponse(401, {}, {"error": {"message": secret}}),))
        transport = MetaMarketingReadTransport(
            configuration(MediaProvider.META), secret, http, graph_version="v24.0"
        )
        with self.assertRaises(MediaHTTPError) as context:
            transport.request(MediaProvider.META, "authenticate", {})
        self.assertNotIn(secret, str(context.exception))


if __name__ == "__main__":
    unittest.main()
