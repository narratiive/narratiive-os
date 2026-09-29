from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from runtime.media_control import CanonicalMediaSnapshot, MediaRecommendation


class MediaMonitoringError(ValueError):
    pass


class MediaMonitoringEngine:
    """Deterministic, read-only interpretation of canonical media evidence."""

    CADENCES = {"daily": timedelta(hours=36), "weekly": timedelta(days=8)}
    TREND_METRICS = ("spend", "impressions", "clicks", "ctr", "cpc", "conversions", "cpa", "roas")
    TREND_THRESHOLD = Decimal("30")

    def build(
        self,
        history: Sequence[CanonicalMediaSnapshot],
        recommendations: Sequence[MediaRecommendation],
        diagnostics: Mapping[str, Any],
        *,
        cadence: str,
        query: str = "",
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        cadence = cadence.strip().casefold()
        if cadence not in self.CADENCES:
            raise MediaMonitoringError("media monitoring cadence must be daily or weekly")
        now = _timestamp(generated_at or datetime.now(timezone.utc).isoformat(), "generated_at")
        matched = tuple(item for item in history if _matches(item, query))
        grouped: dict[tuple[str, str, str, str], list[CanonicalMediaSnapshot]] = defaultdict(list)
        for snapshot in matched:
            grouped[
                (
                    snapshot.identity.workspace_id,
                    snapshot.identity.client_id,
                    snapshot.identity.campaign_id,
                    snapshot.provider.value,
                )
            ].append(snapshot)

        facts: list[dict[str, Any]] = []
        trends: list[dict[str, Any]] = []
        exceptions: list[dict[str, Any]] = []
        creative_diagnostics: list[dict[str, Any]] = []
        latest_keys: set[tuple[str, str, str]] = set()
        for key in sorted(grouped):
            snapshots = sorted(grouped[key], key=lambda item: (_timestamp(item.period_end, "period_end"), item.ingested_at))
            current = snapshots[-1]
            previous = snapshots[-2] if len(snapshots) > 1 else None
            latest_keys.add((current.identity.client_id, current.identity.campaign_id, current.provider.value))
            current_metrics = {
                metric.name: str(metric.value) if metric.available and metric.value is not None else None
                for metric in current.metrics
            }
            age_seconds = max(Decimal("0"), Decimal(str((now - _timestamp(current.ingested_at, "ingested_at")).total_seconds())))
            facts.append(
                {
                    "classification": "observed_fact",
                    "workspace_id": current.identity.workspace_id,
                    "client_id": current.identity.client_id,
                    "campaign_id": current.identity.campaign_id,
                    "provider": current.provider.value,
                    "provider_campaign_id": current.provider_mapping.campaign_id,
                    "period_start": current.period_start,
                    "period_end": current.period_end,
                    "ingested_at": current.ingested_at,
                    "age_hours": str((age_seconds / Decimal("3600")).quantize(Decimal("0.01"))),
                    "campaign_status": current.campaign_status,
                    "review_status": current.review_status,
                    "tracking_status": current.tracking_status,
                    "currency": current.currency,
                    "metrics": current_metrics,
                    "attribution_contexts": sorted({item.attribution_context for item in current.metrics}),
                }
            )
            if now - _timestamp(current.ingested_at, "ingested_at") > self.CADENCES[cadence]:
                exceptions.append(
                    _exception(
                        current,
                        "high",
                        "stale_evidence",
                        "The latest verified provider snapshot is older than the monitoring freshness limit.",
                        (f"ingested_at={current.ingested_at}", f"cadence={cadence}"),
                        "Refresh the read-only provider snapshot before making a performance decision.",
                        "observed_exception",
                    )
                )
            spend = _metric(current, "spend")
            impressions = _metric(current, "impressions")
            if spend is not None and spend > 0 and impressions == 0:
                exceptions.append(
                    _exception(
                        current,
                        "critical",
                        "delivery_evidence_conflict",
                        "Provider evidence reports spend but zero impressions.",
                        (f"spend={spend}", "impressions=0"),
                        "Inspect provider reporting and tracking before interpreting performance.",
                        "observed_exception",
                    )
                )
            if previous is not None and _comparable_periods(previous, current):
                for metric_name in self.TREND_METRICS:
                    before = _metric(previous, metric_name)
                    after = _metric(current, metric_name)
                    if before is None or after is None or before == 0:
                        continue
                    change = ((after - before) / abs(before) * Decimal("100")).quantize(Decimal("0.01"))
                    trend = {
                        "classification": "observed_change",
                        "client_id": current.identity.client_id,
                        "campaign_id": current.identity.campaign_id,
                        "provider": current.provider.value,
                        "metric": metric_name,
                        "previous": str(before),
                        "current": str(after),
                        "change_percent": str(change),
                        "periods_comparable": True,
                    }
                    trends.append(trend)
                    if abs(change) >= self.TREND_THRESHOLD:
                        exceptions.append(
                            _exception(
                                current,
                                "high" if abs(change) >= Decimal("50") else "medium",
                                "material_metric_change",
                                f"{metric_name} changed materially between comparable reporting windows.",
                                (f"previous={before}", f"current={after}", f"change_percent={change}"),
                                "Review the provider breakdowns and campaign context; direction alone does not establish cause.",
                                "rule_based_signal",
                            )
                        )
            creative_diagnostics.append(_creative_diagnostic(current))

        bounded_recommendations = [
            {
                **item.to_dict(),
                "evidence": list(item.evidence),
                "classification": "rule_based_interpretation",
                "causal_claim": False,
            }
            for item in recommendations
            if (item.client_id, item.campaign_id) in {(key[0], key[1]) for key in latest_keys}
        ]
        provider_health = {
            name: value
            for name, value in diagnostics.items()
            if name in {"meta", "tiktok", "google"} and isinstance(value, Mapping)
        }
        for provider, value in sorted(provider_health.items()):
            health = str(value.get("health") or "unknown")
            if health == "healthy":
                continue
            severity = {"offline": "critical", "degraded": "high", "not_configured": "medium"}.get(
                health, "high"
            )
            exceptions.append(
                {
                    "classification": "observed_exception",
                    "severity": severity,
                    "category": "provider_health",
                    "client_id": None,
                    "campaign_id": None,
                    "provider": provider,
                    "summary": f"The {provider} read-only integration is {health.replace('_', ' ')}.",
                    "evidence": [
                        f"health={health}",
                        f"connection_status={value.get('connection_status')}",
                        f"credential_health={value.get('credential_health')}",
                    ],
                    "recommended_next_action": (
                        "Complete the documented provider setup or resolve the latest failed read, then run live certification."
                    ),
                    "human_approval_required": health == "not_configured",
                }
            )
        currencies = {str(item["currency"]) for item in facts}
        spend_values = [
            Decimal(str(item["metrics"]["spend"]))
            for item in facts
            if item["metrics"].get("spend") is not None
        ]
        comparable_total = bool(spend_values) and len(currencies) == 1
        report_core = {
            "cadence": cadence,
            "query": query.strip(),
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "facts": facts,
            "trends": trends,
            "exceptions": _deduplicate(exceptions),
            "creative_diagnostics": creative_diagnostics,
            "recommendations": bounded_recommendations,
            "provider_health": provider_health,
            "total_spend": str(sum(spend_values, Decimal("0"))) if comparable_total else None,
            "total_spend_currency": next(iter(currencies)) if comparable_total else None,
            "cross_provider_total_available": comparable_total,
            "measurement_warning": (
                "Provider definitions and attribution settings differ. Changes are observed associations, "
                "not causal explanations, and cross-provider metrics are not assumed equivalent."
            ),
            "human_approval_required": bool(bounded_recommendations) or any(
                bool(item.get("human_approval_required")) for item in exceptions
            ),
            "external_action_taken": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }
        checksum = hashlib.sha256(
            json.dumps(report_core, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        return {
            "report_id": f"media-{cadence}-{checksum[:20]}",
            "status": "attention_required" if exceptions or bounded_recommendations else "clear",
            **report_core,
        }


def _matches(snapshot: CanonicalMediaSnapshot, query: str) -> bool:
    needle = query.strip().casefold()
    return not needle or needle in {
        snapshot.identity.workspace_id.casefold(),
        snapshot.identity.client_id.casefold(),
        snapshot.identity.brand_id.casefold(),
        snapshot.identity.campaign_id.casefold(),
        snapshot.provider.value,
    }


def _metric(snapshot: CanonicalMediaSnapshot, name: str) -> Decimal | None:
    value = snapshot.metric(name)
    return value.value if value is not None and value.available else None


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise MediaMonitoringError(f"media monitoring {field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise MediaMonitoringError(f"media monitoring {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _comparable_periods(previous: CanonicalMediaSnapshot, current: CanonicalMediaSnapshot) -> bool:
    previous_duration = _timestamp(previous.period_end, "period_end") - _timestamp(previous.period_start, "period_start")
    current_duration = _timestamp(current.period_end, "period_end") - _timestamp(current.period_start, "period_start")
    return previous_duration == current_duration and previous.currency == current.currency


def _exception(
    snapshot: CanonicalMediaSnapshot,
    severity: str,
    category: str,
    summary: str,
    evidence: tuple[str, ...],
    next_action: str,
    classification: str,
) -> dict[str, Any]:
    return {
        "classification": classification,
        "severity": severity,
        "category": category,
        "client_id": snapshot.identity.client_id,
        "campaign_id": snapshot.identity.campaign_id,
        "provider": snapshot.provider.value,
        "summary": summary,
        "evidence": list(evidence),
        "recommended_next_action": next_action,
        "human_approval_required": True,
    }


def _creative_diagnostic(snapshot: CanonicalMediaSnapshot) -> dict[str, Any]:
    rows = snapshot.breakdowns.get("creative_performance")
    available = isinstance(rows, list) and bool(rows)
    return {
        "classification": "observed_fact",
        "client_id": snapshot.identity.client_id,
        "campaign_id": snapshot.identity.campaign_id,
        "provider": snapshot.provider.value,
        "mapped_asset_count": len(snapshot.creative_mappings),
        "creative_level_performance_available": available,
        "creative_rows": rows if available else [],
        "limitation": (
            "No provider-level creative performance rows were present; campaign-level results must not be attributed to an individual asset."
            if not available
            else "Rows retain provider measurement definitions and require human interpretation."
        ),
    }


def _deduplicate(values: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
