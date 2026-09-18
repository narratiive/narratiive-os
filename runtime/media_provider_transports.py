from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Protocol

from runtime.media_control import (
    GoogleReadOnlyAdapter,
    MediaConfigurationError,
    MediaProvider,
    MediaProviderAdapter,
    MediaProviderError,
    MetaReadOnlyAdapter,
    ProviderConfiguration,
    TikTokReadOnlyAdapter,
)


class MediaHTTPError(MediaProviderError):
    """Sanitised HTTP failure. Response bodies and credentials are not exposed."""


@dataclass(frozen=True, slots=True)
class JSONResponse:
    status: int
    headers: Mapping[str, str]
    payload: Any


class JSONHTTPClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        form: Mapping[str, Any] | None = None,
    ) -> JSONResponse: ...


class UrllibJSONHTTPClient:
    """Small bounded JSON client used only by fixed-host read transports."""

    def __init__(self, *, timeout_seconds: float = 20, max_response_bytes: int = 10_000_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        form: Mapping[str, Any] | None = None,
    ) -> JSONResponse:
        if body is not None and form is not None:
            raise MediaHTTPError("HTTP request cannot contain both JSON and form bodies")
        resolved_url = _url_with_query(url, query or {})
        data = None
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        if body is not None:
            data = json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urllib.parse.urlencode(dict(form)).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(
            resolved_url,
            data=data,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.max_response_bytes + 1)
                if len(raw) > self.max_response_bytes:
                    raise MediaHTTPError("provider response exceeded the configured size limit")
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise MediaHTTPError("provider returned a non-JSON response") from exc
                return JSONResponse(
                    status=int(response.status),
                    headers={str(key): str(value) for key, value in response.headers.items()},
                    payload=payload,
                )
        except urllib.error.HTTPError as exc:
            raise MediaHTTPError(f"provider HTTP request failed with status {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise MediaHTTPError("provider HTTP request could not be completed") from exc


class MetaMarketingReadTransport:
    provider = MediaProvider.META

    def __init__(
        self,
        configuration: ProviderConfiguration,
        access_token: str,
        http: JSONHTTPClient,
        *,
        graph_version: str,
    ) -> None:
        if not access_token.strip():
            raise MediaConfigurationError("Meta access token is required")
        if not graph_version.startswith("v") or "." not in graph_version:
            raise MediaConfigurationError("META_GRAPH_API_VERSION must be an explicit version such as v24.0")
        self.configuration = configuration
        self._access_token = access_token
        self.http = http
        self.base_url = f"https://graph.facebook.com/{graph_version}"

    def request(self, provider: MediaProvider, operation: str, parameters: Mapping[str, Any]) -> Any:
        _require_provider(provider, self.provider)
        account_id = _meta_account_id(self.configuration.account_id)
        if operation == "authenticate":
            return self._get("/me", {"fields": "id,name"})
        if operation == "get_accounts":
            return _data(self._get("/me/adaccounts", {"fields": "id,name,account_status,currency,timezone_name"}))
        if operation == "get_campaigns":
            return _data(self._get(f"/{account_id}/campaigns", {"fields": "id,name,status,effective_status,objective"}))
        campaign_id = _required(parameters, "campaign_id")
        if operation == "get_campaign":
            return self._get(f"/{campaign_id}", {"fields": "id,name,status,effective_status,objective,daily_budget,lifetime_budget"})
        if operation == "get_ad_groups":
            return _data(self._get(f"/{campaign_id}/adsets", {"fields": "id,name,status,effective_status,daily_budget,lifetime_budget"}))
        if operation == "get_ads":
            return _data(self._get(f"/{campaign_id}/ads", {"fields": "id,name,status,effective_status,creative{id,name}"}))
        if operation == "get_creatives":
            ads = _data(self._get(f"/{campaign_id}/ads", {"fields": "id,creative{id,name,object_type}"}))
            return [item.get("creative", {}) for item in ads if isinstance(item.get("creative"), Mapping)]
        if operation == "get_delivery_status":
            return self._get(f"/{campaign_id}", {"fields": "id,status,effective_status,issues_info"})
        if operation == "get_review_status":
            return {"ads": _data(self._get(f"/{campaign_id}/ads", {"fields": "id,effective_status,review_feedback"}))}
        if operation == "get_performance":
            return self._performance(campaign_id, parameters)
        raise MediaProviderError(f"unsupported Meta read operation: {operation}")

    def _performance(self, campaign_id: str, parameters: Mapping[str, Any]) -> Mapping[str, Any]:
        start = _date(_required(parameters, "period_start"))
        end = _date(_required(parameters, "period_end"))
        campaign = self._get(
            f"/{campaign_id}",
            {"fields": "id,status,effective_status,daily_budget,lifetime_budget"},
        )
        insight_rows = _data(
            self._get(
                f"/{campaign_id}/insights",
                {
                    "fields": (
                        "spend,impressions,reach,frequency,cpm,clicks,ctr,cpc,"
                        "actions,action_values,cost_per_action_type,video_play_actions,video_p100_watched_actions"
                    ),
                    "time_range": json.dumps({"since": start, "until": end}, separators=(",", ":")),
                    "level": "campaign",
                },
            )
        )
        insight = insight_rows[0] if insight_rows else {}
        actions = _action_map(insight.get("actions"))
        values = _action_map(insight.get("action_values"))
        costs = _action_map(insight.get("cost_per_action_type"))
        conversions = _first_action(actions, ("offsite_conversion", "purchase", "lead"))
        conversion_value = _first_action(values, ("offsite_conversion", "purchase"))
        cpa = _first_action(costs, ("offsite_conversion", "purchase", "lead"))
        spend = _number(insight.get("spend"))
        metrics = {
            "spend": spend,
            "budget": _minor_currency(campaign.get("lifetime_budget") or campaign.get("daily_budget")),
            "impressions": _number(insight.get("impressions")),
            "reach": _number(insight.get("reach")),
            "frequency": _number(insight.get("frequency")),
            "cpm": _number(insight.get("cpm")),
            "clicks": _number(insight.get("clicks")),
            "ctr": _number(insight.get("ctr")),
            "cpc": _number(insight.get("cpc")),
            "video_views": _sum_action_values(insight.get("video_play_actions")),
            "video_completions": _sum_action_values(insight.get("video_p100_watched_actions")),
            "conversions": conversions,
            "conversion_value": conversion_value,
            "cpa": cpa,
            "roas": _ratio(conversion_value, spend),
        }
        return _canonical_response(
            configuration=self.configuration,
            start=parameters["period_start"],
            end=parameters["period_end"],
            campaign_status=str(campaign.get("effective_status") or campaign.get("status") or "unknown"),
            review_status="unknown",
            tracking_status="unknown",
            authorised_budget=metrics["budget"],
            attribution_context="Meta account attribution settings; verify in Ads Manager",
            metrics=metrics,
        )

    def _get(self, path: str, query: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self.http.request(
            "GET",
            f"{self.base_url}{path}",
            query={**dict(query), "access_token": self._access_token},
        )
        return _mapping_payload(response, "Meta")


class TikTokBusinessReadTransport:
    provider = MediaProvider.TIKTOK
    base_url = "https://business-api.tiktok.com/open_api/v1.3"

    def __init__(self, configuration: ProviderConfiguration, access_token: str, http: JSONHTTPClient) -> None:
        if not access_token.strip():
            raise MediaConfigurationError("TikTok access token is required")
        self.configuration = configuration
        self._access_token = access_token
        self.http = http

    def request(self, provider: MediaProvider, operation: str, parameters: Mapping[str, Any]) -> Any:
        _require_provider(provider, self.provider)
        advertiser_id = self.configuration.account_id
        if operation in {"authenticate", "get_accounts"}:
            payload = self._get("/oauth2/advertiser/get/", {})
            return payload.get("data", {}).get("list", []) if operation == "get_accounts" else payload
        if operation == "get_campaigns":
            return self._list("/campaign/get/", {"advertiser_id": advertiser_id})
        campaign_id = _required(parameters, "campaign_id")
        filtering = json.dumps({"campaign_ids": [campaign_id]}, separators=(",", ":"))
        if operation == "get_campaign":
            rows = self._list("/campaign/get/", {"advertiser_id": advertiser_id, "filtering": filtering})
            return rows[0] if rows else {}
        if operation == "get_ad_groups":
            return self._list("/adgroup/get/", {"advertiser_id": advertiser_id, "filtering": filtering})
        if operation in {"get_ads", "get_creatives", "get_review_status"}:
            rows = self._list("/ad/get/", {"advertiser_id": advertiser_id, "filtering": filtering})
            if operation == "get_creatives":
                return [
                    {key: item.get(key) for key in ("ad_id", "ad_name", "video_id", "image_ids", "creative_type")}
                    for item in rows
                ]
            if operation == "get_review_status":
                return {"ads": [{"ad_id": item.get("ad_id"), "review_status": item.get("review_status")} for item in rows]}
            return rows
        if operation == "get_delivery_status":
            campaign = self.request(provider, "get_campaign", parameters)
            return {key: campaign.get(key) for key in ("campaign_id", "operation_status", "secondary_status")}
        if operation == "get_performance":
            return self._performance(campaign_id, parameters)
        raise MediaProviderError(f"unsupported TikTok read operation: {operation}")

    def _performance(self, campaign_id: str, parameters: Mapping[str, Any]) -> Mapping[str, Any]:
        campaign = self.request(self.provider, "get_campaign", {"campaign_id": campaign_id})
        payload = self._get(
            "/report/integrated/get/",
            {
                "advertiser_id": self.configuration.account_id,
                "report_type": "BASIC",
                "data_level": "AUCTION_CAMPAIGN",
                "dimensions": json.dumps(["campaign_id"]),
                "metrics": json.dumps([
                    "spend", "impressions", "reach", "frequency", "cpm", "clicks", "ctr", "cpc",
                    "video_play_actions", "video_views_p100", "conversion", "total_purchase_value", "cost_per_conversion", "purchase_roas",
                ]),
                "filters": json.dumps([{"field_name": "campaign_ids", "filter_type": "IN", "filter_value": [campaign_id]}]),
                "start_date": _date(_required(parameters, "period_start")),
                "end_date": _date(_required(parameters, "period_end")),
            },
        )
        rows = payload.get("data", {}).get("list", [])
        metrics_value = rows[0].get("metrics", {}) if rows and isinstance(rows[0], Mapping) else {}
        metrics = {
            "spend": _number(metrics_value.get("spend")),
            "budget": _number(campaign.get("budget")),
            "impressions": _number(metrics_value.get("impressions")),
            "reach": _number(metrics_value.get("reach")),
            "frequency": _number(metrics_value.get("frequency")),
            "cpm": _number(metrics_value.get("cpm")),
            "clicks": _number(metrics_value.get("clicks")),
            "ctr": _number(metrics_value.get("ctr")),
            "cpc": _number(metrics_value.get("cpc")),
            "video_views": _number(metrics_value.get("video_play_actions")),
            "video_completions": _number(metrics_value.get("video_views_p100")),
            "conversions": _number(metrics_value.get("conversion")),
            "conversion_value": _number(metrics_value.get("total_purchase_value")),
            "cpa": _number(metrics_value.get("cost_per_conversion")),
            "roas": _number(metrics_value.get("purchase_roas")),
        }
        return _canonical_response(
            configuration=self.configuration,
            start=parameters["period_start"], end=parameters["period_end"],
            campaign_status=str(campaign.get("secondary_status") or campaign.get("operation_status") or "unknown"),
            review_status="unknown", tracking_status="unknown",
            authorised_budget=metrics["budget"],
            attribution_context="TikTok advertiser attribution settings; verify in Ads Manager",
            metrics=metrics,
        )

    def _list(self, path: str, query: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        payload = self._get(path, query)
        rows = payload.get("data", {}).get("list", [])
        if not isinstance(rows, list):
            raise MediaHTTPError("TikTok returned a malformed list response")
        return [item for item in rows if isinstance(item, Mapping)]

    def _get(self, path: str, query: Mapping[str, Any]) -> Mapping[str, Any]:
        response = self.http.request(
            "GET", f"{self.base_url}{path}",
            headers={"Access-Token": self._access_token}, query=query,
        )
        payload = _mapping_payload(response, "TikTok")
        if int(payload.get("code", 0)) != 0:
            raise MediaHTTPError("TikTok returned an unsuccessful API code")
        return payload


class GoogleAdsReadTransport:
    provider = MediaProvider.GOOGLE

    def __init__(
        self,
        configuration: ProviderConfiguration,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        http: JSONHTTPClient,
        api_version: str,
        developer_token: str = "",
    ) -> None:
        if any(not value.strip() for value in (client_id, client_secret, refresh_token)):
            raise MediaConfigurationError("Google Ads OAuth client and refresh token are required")
        if not api_version.startswith("v"):
            raise MediaConfigurationError("GOOGLE_ADS_API_VERSION must be an explicit version such as v25")
        self.configuration = configuration
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._developer_token = developer_token
        self.http = http
        self.api_version = api_version

    def request(self, provider: MediaProvider, operation: str, parameters: Mapping[str, Any]) -> Any:
        _require_provider(provider, self.provider)
        if operation in {"authenticate", "get_accounts"}:
            payload = self._json(
                "GET",
                f"https://googleads.googleapis.com/{self.api_version}/customers:listAccessibleCustomers",
            )
            accounts = [{"resource_name": item} for item in payload.get("resourceNames", [])]
            return {"accounts": accounts} if operation == "authenticate" else accounts
        campaign_id = str(parameters.get("campaign_id", "")).strip()
        if operation == "get_campaigns":
            return self._rows("SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type FROM campaign WHERE campaign.status != 'REMOVED'")
        if not campaign_id:
            raise MediaConfigurationError("campaign_id is required")
        condition = f"campaign.id = {int(campaign_id)}"
        queries = {
            "get_campaign": f"SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, campaign_budget.amount_micros FROM campaign WHERE {condition}",
            "get_ad_groups": f"SELECT ad_group.id, ad_group.name, ad_group.status, campaign.id FROM ad_group WHERE {condition}",
            "get_ads": f"SELECT ad_group_ad.ad.id, ad_group_ad.status, ad_group.id, campaign.id FROM ad_group_ad WHERE {condition}",
            "get_creatives": f"SELECT ad_group_ad.ad.id, ad_group_ad.ad.resource_name, ad_group_ad.ad.type, campaign.id FROM ad_group_ad WHERE {condition}",
            "get_delivery_status": f"SELECT campaign.id, campaign.status, campaign.serving_status FROM campaign WHERE {condition}",
            "get_review_status": f"SELECT ad_group_ad.ad.id, ad_group_ad.policy_summary.approval_status, ad_group_ad.policy_summary.review_status FROM ad_group_ad WHERE {condition}",
        }
        if operation in queries:
            rows = self._rows(queries[operation])
            return rows[0] if operation in {"get_campaign", "get_delivery_status"} and rows else ({"ads": rows} if operation == "get_review_status" else rows)
        if operation == "get_performance":
            return self._performance(campaign_id, parameters)
        raise MediaProviderError(f"unsupported Google Ads read operation: {operation}")

    def _performance(self, campaign_id: str, parameters: Mapping[str, Any]) -> Mapping[str, Any]:
        start = _date(_required(parameters, "period_start"))
        end = _date(_required(parameters, "period_end"))
        rows = self._rows(
            "SELECT campaign.id, campaign.status, campaign_budget.amount_micros, "
            "metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.ctr, metrics.average_cpc, "
            "metrics.average_cpm, metrics.conversions, metrics.conversions_value, metrics.cost_per_conversion, "
            "metrics.value_per_conversion "
            f"FROM campaign WHERE campaign.id = {int(campaign_id)} AND segments.date BETWEEN '{start}' AND '{end}'"
        )
        row = rows[0] if rows else {}
        campaign = row.get("campaign", {}) if isinstance(row.get("campaign"), Mapping) else {}
        budget = row.get("campaignBudget", {}) if isinstance(row.get("campaignBudget"), Mapping) else {}
        native = row.get("metrics", {}) if isinstance(row.get("metrics"), Mapping) else {}
        spend = _micro_currency(native.get("costMicros"))
        conversion_value = _number(native.get("conversionsValue"))
        metrics = {
            "spend": spend,
            "budget": _micro_currency(budget.get("amountMicros")),
            "impressions": _number(native.get("impressions")),
            "reach": None,
            "frequency": None,
            "cpm": _micro_currency(native.get("averageCpm")),
            "clicks": _number(native.get("clicks")),
            "ctr": _percentage(native.get("ctr")),
            "cpc": _micro_currency(native.get("averageCpc")),
            "video_views": None,
            "video_completions": None,
            "conversions": _number(native.get("conversions")),
            "conversion_value": conversion_value,
            "cpa": _micro_currency(native.get("costPerConversion")),
            "roas": _ratio(conversion_value, spend),
        }
        return _canonical_response(
            configuration=self.configuration,
            start=parameters["period_start"], end=parameters["period_end"],
            campaign_status=str(campaign.get("status", "unknown")),
            review_status="unknown", tracking_status="unknown",
            authorised_budget=metrics["budget"],
            attribution_context="Google Ads account conversion attribution settings; verify in Ads Manager",
            metrics=metrics,
        )

    def _rows(self, query: str) -> list[Mapping[str, Any]]:
        customer = self.configuration.account_id.replace("-", "")
        payload = self._json(
            "POST",
            f"https://googleads.googleapis.com/{self.api_version}/customers/{customer}/googleAds:searchStream",
            body={"query": query},
        )
        if not isinstance(payload, list):
            raise MediaHTTPError("Google Ads searchStream returned a malformed response")
        rows: list[Mapping[str, Any]] = []
        for batch in payload:
            if isinstance(batch, Mapping) and isinstance(batch.get("results"), list):
                rows.extend(item for item in batch["results"] if isinstance(item, Mapping))
        return rows

    def _json(self, method: str, url: str, *, body: Mapping[str, Any] | None = None) -> Any:
        access_token = self._access_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        if self._developer_token:
            headers["developer-token"] = self._developer_token
        if self.configuration.manager_account_id:
            headers["login-customer-id"] = self.configuration.manager_account_id.replace("-", "")
        response = self.http.request(method, url, headers=headers, body=body)
        if response.status < 200 or response.status >= 300:
            raise MediaHTTPError(f"Google Ads HTTP request failed with status {response.status}")
        return response.payload

    def _access_token(self) -> str:
        response = self.http.request(
            "POST",
            "https://oauth2.googleapis.com/token",
            form={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
        )
        payload = _mapping_payload(response, "Google OAuth")
        token = str(payload.get("access_token", "")).strip()
        if not token:
            raise MediaHTTPError("Google OAuth response did not contain an access token")
        return token


def build_configured_media_adapters(
    environment: Mapping[str, str],
    *,
    http: JSONHTTPClient | None = None,
) -> dict[MediaProvider, MediaProviderAdapter]:
    """Build only fully configured, read-only adapters. No network call occurs here."""

    client = http or UrllibJSONHTTPClient()
    adapters: dict[MediaProvider, MediaProviderAdapter] = {}
    for provider in MediaProvider:
        configuration = _configuration(provider, environment)
        if configuration.validate(environment):
            continue
        if provider is MediaProvider.META:
            graph_version = str(environment.get("META_GRAPH_API_VERSION", "")).strip()
            if not graph_version:
                continue
            transport = MetaMarketingReadTransport(
                configuration,
                str(environment["META_ACCESS_TOKEN"]),
                client,
                graph_version=graph_version,
            )
            adapters[provider] = MetaReadOnlyAdapter(configuration, transport, environment=environment)
        elif provider is MediaProvider.TIKTOK:
            transport = TikTokBusinessReadTransport(
                configuration,
                str(environment["TIKTOK_ACCESS_TOKEN"]),
                client,
            )
            adapters[provider] = TikTokReadOnlyAdapter(configuration, transport, environment=environment)
        else:
            api_version = str(environment.get("GOOGLE_ADS_API_VERSION", "")).strip()
            if not api_version:
                continue
            transport = GoogleAdsReadTransport(
                configuration,
                client_id=str(environment["GOOGLE_ADS_CLIENT_ID"]),
                client_secret=str(environment["GOOGLE_ADS_CLIENT_SECRET"]),
                refresh_token=str(environment["GOOGLE_ADS_REFRESH_TOKEN"]),
                developer_token=str(environment.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")),
                http=client,
                api_version=api_version,
            )
            adapters[provider] = GoogleReadOnlyAdapter(configuration, transport, environment=environment)
    return adapters


def _configuration(provider: MediaProvider, environment: Mapping[str, str]) -> ProviderConfiguration:
    prefix = "GOOGLE_ADS" if provider is MediaProvider.GOOGLE else provider.value.upper()
    credentials = {
        MediaProvider.META: ("META_ACCESS_TOKEN",),
        MediaProvider.TIKTOK: ("TIKTOK_ACCESS_TOKEN",),
        MediaProvider.GOOGLE: ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN"),
    }
    return ProviderConfiguration(
        provider=provider,
        account_id=str(environment.get(f"{prefix}_ACCOUNT_ID", "")),
        manager_account_id=str(environment.get(f"{prefix}_MANAGER_ACCOUNT_ID", "")),
        credential_env_names=credentials[provider],
        timezone_name=str(environment.get(f"{prefix}_TIMEZONE", "")),
        currency=str(environment.get(f"{prefix}_CURRENCY", "")),
    )


def _canonical_response(
    *,
    configuration: ProviderConfiguration,
    start: Any,
    end: Any,
    campaign_status: str,
    review_status: str,
    tracking_status: str,
    authorised_budget: Any,
    attribution_context: str,
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "period_start": str(start),
        "period_end": str(end),
        "currency": configuration.currency.upper(),
        "timezone": configuration.timezone_name,
        "campaign_status": campaign_status,
        "review_status": review_status,
        "tracking_status": tracking_status,
        "authorised_budget": authorised_budget,
        "attribution_context": attribution_context,
        "metrics": dict(metrics),
        "breakdowns": {},
    }


def _mapping_payload(response: JSONResponse, provider: str) -> Mapping[str, Any]:
    if response.status < 200 or response.status >= 300:
        raise MediaHTTPError(f"{provider} HTTP request failed with status {response.status}")
    if not isinstance(response.payload, Mapping):
        raise MediaHTTPError(f"{provider} returned a malformed response")
    return response.payload


def _url_with_query(url: str, query: Mapping[str, Any]) -> str:
    values = {key: value for key, value in query.items() if value not in (None, "")}
    if not values:
        return url
    separator = "&" if "?" in url else "?"
    return url + separator + urllib.parse.urlencode(values, doseq=True)


def _data(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = payload.get("data", [])
    if not isinstance(value, list):
        raise MediaHTTPError("provider returned a malformed data list")
    return [item for item in value if isinstance(item, Mapping)]


def _required(parameters: Mapping[str, Any], name: str) -> str:
    value = str(parameters.get(name, "")).strip()
    if not value:
        raise MediaConfigurationError(f"{name} is required")
    return value


def _require_provider(actual: MediaProvider, expected: MediaProvider) -> None:
    if actual is not expected:
        raise MediaConfigurationError("provider transport mismatch")


def _meta_account_id(value: str) -> str:
    stripped = value.strip()
    return stripped if stripped.startswith("act_") else f"act_{stripped}"


def _date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError as exc:
        raise MediaConfigurationError("reporting period must use ISO-8601 timestamps") from exc


def _number(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return str(Decimal(str(value)))
    except Exception as exc:
        raise MediaHTTPError("provider returned a malformed numeric metric") from exc


def _micro_currency(value: Any) -> str | None:
    numeric = _number(value)
    if numeric is None:
        return None
    return str(Decimal(numeric) / Decimal("1000000"))


def _minor_currency(value: Any) -> str | None:
    numeric = _number(value)
    if numeric is None:
        return None
    return str(Decimal(numeric) / Decimal("100"))


def _percentage(value: Any) -> str | None:
    numeric = _number(value)
    if numeric is None:
        return None
    return str(Decimal(numeric) * Decimal("100"))


def _ratio(numerator: Any, denominator: Any) -> str | None:
    if numerator is None or denominator in (None, "0", 0, Decimal("0")):
        return None
    return str(Decimal(str(numerator)) / Decimal(str(denominator)))


def _action_map(value: Any) -> dict[str, str]:
    if not isinstance(value, list):
        return {}
    result: dict[str, str] = {}
    for item in value:
        if isinstance(item, Mapping) and item.get("action_type") and item.get("value") not in (None, ""):
            result[str(item["action_type"])] = str(item["value"])
    return result


def _first_action(values: Mapping[str, str], suffixes: tuple[str, ...]) -> str | None:
    for suffix in suffixes:
        for name, value in values.items():
            if name == suffix or name.endswith(f".{suffix}"):
                return _number(value)
    return None


def _sum_action_values(value: Any) -> str | None:
    mapped = _action_map(value)
    if not mapped:
        return None
    return str(sum((Decimal(item) for item in mapped.values()), Decimal("0")))
