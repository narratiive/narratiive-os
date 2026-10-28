"""FIELDWORK v4 commercial-opening and cohort-model contracts.

The module is deliberately presentation-neutral.  It validates the five
founder-facing moves and calculates only supported or explicitly illustrative
commercial scenarios.  Renderers may style the result but may not rewrite it.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


FIELDWORK_V4_VERSION = "4.0.0"
FIELDWORK_V4_OPENING_ROLES = (
    "commercial_position_today",
    "twelve_month_opportunity",
    "where_gains_come_from",
    "audience_opportunity",
    "strategic_direction",
)
FIELDWORK_V4_OPENING_TITLES = (
    "The commercial position today",
    "The 12-month opportunity",
    "Where the gains come from",
    "The audience opportunity",
    "The strategic direction",
)


def _required_text(value: Any, field: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise ValueError(f"FIELDWORK v4 requires {field}")
    return text


def validate_fieldwork_v4_opening(value: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return a normalized five-slide opening or fail closed."""
    if str(value.get("contract_version") or "") != FIELDWORK_V4_VERSION:
        raise ValueError("FIELDWORK opening must declare contract_version 4.0.0")
    raw_slides = value.get("slides")
    if not isinstance(raw_slides, list) or len(raw_slides) != 5:
        raise ValueError("FIELDWORK v4 requires exactly five opening content slides")
    normalized: list[dict[str, Any]] = []
    for index, (raw, expected_role, expected_title) in enumerate(
        zip(raw_slides, FIELDWORK_V4_OPENING_ROLES, FIELDWORK_V4_OPENING_TITLES), 1
    ):
        if not isinstance(raw, Mapping) or raw.get("role") != expected_role:
            raise ValueError(f"FIELDWORK v4 slide {index} must use role {expected_role}")
        evidence_refs = tuple(str(item).strip() for item in raw.get("evidence_refs") or () if str(item).strip())
        assumptions = tuple(str(item).strip() for item in raw.get("assumptions") or () if str(item).strip())
        classification = str(raw.get("classification") or "").strip()
        if classification not in {"evidence", "interpretation", "hypothesis", "illustrative_scenario"}:
            raise ValueError(f"FIELDWORK v4 slide {index} has an invalid classification")
        if classification == "evidence" and not evidence_refs:
            raise ValueError(f"FIELDWORK v4 slide {index} evidence requires source references")
        if classification in {"hypothesis", "illustrative_scenario"} and not assumptions:
            raise ValueError(f"FIELDWORK v4 slide {index} must state its assumptions")
        content = dict(raw.get("content") or {})
        if index == 3:
            levers = content.get("levers")
            if not isinstance(levers, list) or not 2 <= len(levers) <= 4:
                raise ValueError("FIELDWORK v4 gains slide requires two to four levers")
            for lever in levers:
                if not isinstance(lever, Mapping) or not all(
                    _required_text(lever.get(key), f"slide 3 lever {key}")
                    for key in ("action", "behaviour", "commercial_consequence", "measure")
                ):
                    raise ValueError("FIELDWORK v4 lever is incomplete")
        normalized.append({
            "role": expected_role,
            "title": expected_title,
            "headline": _required_text(raw.get("headline"), f"slide {index} headline"),
            "body": _required_text(raw.get("body"), f"slide {index} body"),
            "visual_treatment": _required_text(raw.get("visual_treatment"), f"slide {index} visual treatment"),
            "classification": classification,
            "evidence_refs": evidence_refs,
            "assumptions": assumptions,
            "content": content,
        })
    return tuple(normalized)


def build_fieldwork_v4_cohort_model(value: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate qualified visits x conversion x realised customer revenue.

    Existing-customer and other-channel revenue stay separate.  The function
    never upgrades revenue to contribution or profit without supplied costs.
    """
    if str(value.get("model_type") or "") != "new_customer_cohort":
        raise ValueError("FIELDWORK v4 commercial model must use new_customer_cohort")
    period = _required_text(value.get("period"), "commercial model period")
    population = _required_text(value.get("population"), "commercial model population")
    raw_inputs = value.get("inputs")
    raw_scenarios = value.get("scenarios")
    if not isinstance(raw_inputs, list) or not isinstance(raw_scenarios, list):
        raise ValueError("FIELDWORK v4 commercial model requires inputs and scenarios")
    inputs = {str(item.get("input_id") or ""): item for item in raw_inputs if isinstance(item, Mapping)}
    required_ids = (
        "qualified_visits",
        "first_purchase_conversion_rate",
        "realized_revenue_per_acquired_customer",
    )
    try:
        visits = Decimal(str(inputs[required_ids[0]]["value"]))
        conversion = Decimal(str(inputs[required_ids[1]]["value"]))
        revenue_per_customer = Decimal(str(inputs[required_ids[2]]["value"]))
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError("FIELDWORK v4 cohort model requires numeric baseline inputs") from exc
    if visits <= 0 or not Decimal("0") < conversion <= Decimal("1") or revenue_per_customer <= 0:
        raise ValueError("FIELDWORK v4 cohort baseline inputs are out of range")
    for input_id in required_ids:
        item = inputs[input_id]
        if str(item.get("status") or "") not in {"sourced", "client_supplied", "illustrative"}:
            raise ValueError(f"FIELDWORK v4 input {input_id} has no evidence status")
        if item.get("status") != "illustrative" and not item.get("source_ids"):
            raise ValueError(f"FIELDWORK v4 input {input_id} requires source ids")
    baseline = visits * conversion * revenue_per_customer
    scenarios: list[dict[str, Any]] = []
    for raw in raw_scenarios:
        if not isinstance(raw, Mapping):
            raise ValueError("FIELDWORK v4 scenarios must be objects")
        try:
            vm = Decimal(str(raw["qualified_visits_multiplier"]))
            cm = Decimal(str(raw["conversion_multiplier"]))
            rm = Decimal(str(raw["revenue_per_customer_multiplier"]))
        except (KeyError, InvalidOperation) as exc:
            raise ValueError("FIELDWORK v4 scenarios require all three multipliers") from exc
        if min(vm, cm, rm) <= 0:
            raise ValueError("FIELDWORK v4 scenario multipliers must be positive")
        scenario_revenue = baseline * vm * cm * rm
        scenarios.append({
            "name": _required_text(raw.get("name"), "scenario name"),
            "qualified_visits_multiplier": float(vm),
            "conversion_multiplier": float(cm),
            "revenue_per_customer_multiplier": float(rm),
            "new_customer_cohort_revenue": int(scenario_revenue.quantize(Decimal("1"))),
            "incremental_new_customer_cohort_revenue": int((scenario_revenue - baseline).quantize(Decimal("1"))),
            "uplift_percent": float(((scenario_revenue / baseline) - Decimal("1")) * Decimal("100")),
            "classification": _required_text(raw.get("classification"), "scenario classification"),
            "assumptions": [str(item) for item in raw.get("assumptions") or []],
        })
    if not 1 <= len(scenarios) <= 3:
        raise ValueError("FIELDWORK v4 requires one to three commercial scenarios")
    if any(item["classification"] not in {"planning_case", "sensitivity", "illustrative_scenario"} for item in scenarios):
        raise ValueError("FIELDWORK v4 scenario classification is invalid")
    if any(item["classification"] == "illustrative_scenario" and not item["assumptions"] for item in scenarios):
        raise ValueError("illustrative FIELDWORK v4 scenarios require assumptions")
    currency = _required_text(value.get("currency"), "commercial model currency")
    return {
        "contract_version": FIELDWORK_V4_VERSION,
        "model_type": "new_customer_cohort",
        "period": period,
        "population": population,
        "currency": currency,
        "baseline": {
            "qualified_visits": int(visits),
            "first_purchase_conversion_rate": float(conversion),
            "realized_revenue_per_acquired_customer": float(revenue_per_customer),
            "new_customer_cohort_revenue": int(baseline.quantize(Decimal("1"))),
        },
        "scenarios": scenarios,
        "existing_customer_revenue": dict(value.get("existing_customer_revenue") or {"status": "not_modelled_separately"}),
        "other_channels": list(value.get("other_channels") or []),
        "output_metric": "revenue_index" if currency == "INDEX" else "revenue",
        "limitations": list(value.get("limitations") or []),
        "inputs": [dict(item) for item in raw_inputs if isinstance(item, Mapping)],
    }
