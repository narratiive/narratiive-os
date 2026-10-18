"""Deterministic supervised Growth Blueprint demonstration pipeline.

This module is an additive demonstration profile. It does not replace the
checksum-locked 30-slide Blueprint canon or the existing five-stage specialist
workflow. It turns a structured, explicitly fictional intake into evidence,
commercial modelling, a seven-chapter narrative, a presentation specification,
independent QA and a pending human-approval package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Sequence

from runtime.artifact_catalog import ArtifactRecord, FileArtifactCatalog
from runtime.deliverable_production import (
    PresentationSlideSpec,
    PresentationSpecification,
    _checksum,
)


EVIDENCE_CLASSIFICATIONS = (
    "VERIFIED CLIENT",
    "VERIFIED EXTERNAL",
    "MODELLED",
    "ASSUMPTION",
    "CREATIVE ILLUSTRATION",
)

BLUEPRINT_CHAPTERS = (
    "The Opportunity",
    "The Constraint",
    "The Advantage",
    "The Strategy",
    "The Creative Future",
    "The Growth Engine",
    "The Next 12 Months",
)

OPENING_SLIDE_FUNCTIONS = (
    "Where the business could go",
    "What the commercial opportunity looks like",
    "What currently prevents growth",
    "What strategic moves are required",
    "What the future could look like",
)


class SupervisedBlueprintError(ValueError):
    """Raised when a supervised Blueprint package would overstate evidence."""


@dataclass(frozen=True, slots=True)
class SupervisedBlueprintPackage:
    intake: Mapping[str, Any]
    evidence_ledger: Mapping[str, Any]
    commercial_model: Mapping[str, Any]
    blueprint: Mapping[str, Any]
    presentation: PresentationSpecification
    qa_report: Mapping[str, Any]
    approval_checkpoint: Mapping[str, Any]
    lineage: tuple[ArtifactRecord, ...]

    def manifest(self) -> dict[str, Any]:
        return {
            "package_id": self.blueprint["blueprint_id"],
            "status": "awaiting_human_approval",
            "fictional_demonstration": True,
            "source_intake_checksum": _checksum(self.intake),
            "evidence_ledger_checksum": _checksum(self.evidence_ledger),
            "commercial_model_checksum": _checksum(self.commercial_model),
            "blueprint_checksum": _checksum(self.blueprint),
            "presentation_specification_checksum": _checksum(self.presentation.to_dict()),
            "qa_report_checksum": _checksum(self.qa_report),
            "approval_status": self.approval_checkpoint["status"],
            "external_action_taken": False,
            "release_authorised": False,
            "lineage": [record.to_dict() for record in self.lineage],
        }


def _required_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SupervisedBlueprintError(f"{name} must be an object")
    return value


def _required_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise SupervisedBlueprintError(f"{name} must be a non-empty list")
    return value


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SupervisedBlueprintError(f"{name} is required")
    return text


def _decimal(value: Any, name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SupervisedBlueprintError(f"{name} must be numeric") from exc
    if number <= 0:
        raise SupervisedBlueprintError(f"{name} must be positive")
    return number


def _package_version(intake: Mapping[str, Any]) -> int:
    raw = intake.get("identity") or {}
    try:
        version = int(raw.get("package_version") or 1)
    except (TypeError, ValueError) as exc:
        raise SupervisedBlueprintError("identity.package_version must be an integer") from exc
    if version < 1:
        raise SupervisedBlueprintError("identity.package_version must be positive")
    return version


def validate_intake(intake: Mapping[str, Any]) -> None:
    identity = _required_mapping(intake.get("identity"), "identity")
    for field in ("workspace_id", "client_id", "run_id", "company_name"):
        _required_text(identity.get(field), f"identity.{field}")
    if identity.get("fictional") is not True:
        raise SupervisedBlueprintError("demonstration intake must be explicitly fictional")
    _package_version(intake)

    ledger = _required_list(intake.get("evidence_ledger"), "evidence_ledger")
    ids: set[str] = set()
    for index, raw in enumerate(ledger):
        item = _required_mapping(raw, f"evidence_ledger[{index}]")
        evidence_id = _required_text(item.get("evidence_id"), "evidence_id")
        if evidence_id in ids:
            raise SupervisedBlueprintError(f"duplicate evidence id: {evidence_id}")
        ids.add(evidence_id)
        classification = _required_text(item.get("classification"), "classification")
        if classification not in EVIDENCE_CLASSIFICATIONS:
            raise SupervisedBlueprintError(f"unsupported evidence classification: {classification}")
        _required_text(item.get("claim"), f"{evidence_id}.claim")
        _required_text(item.get("observed_at"), f"{evidence_id}.observed_at")
        _required_text(item.get("confidence"), f"{evidence_id}.confidence")
        _required_text(item.get("validation_step"), f"{evidence_id}.validation_step")
        if classification == "VERIFIED EXTERNAL":
            _required_text(item.get("source_url"), f"{evidence_id}.source_url")
            _required_text(item.get("publisher"), f"{evidence_id}.publisher")
        if classification == "VERIFIED CLIENT":
            _required_text(item.get("source_document_id"), f"{evidence_id}.source_document_id")
        if identity["fictional"] is True and classification == "VERIFIED CLIENT":
            raise SupervisedBlueprintError("fictional fixtures cannot claim verified client evidence")

    model = _required_mapping(intake.get("commercial_model"), "commercial_model")
    if model.get("model_type") != "ecommerce":
        raise SupervisedBlueprintError("the minimal vertical slice supports ecommerce economics")
    for key in ("baseline", "scenarios"):
        _required_mapping(model.get(key), f"commercial_model.{key}") if key == "baseline" else _required_list(model.get(key), f"commercial_model.{key}")
    for ref in model.get("input_evidence_ids") or []:
        if ref not in ids:
            raise SupervisedBlueprintError(f"commercial model references unknown evidence: {ref}")
    if len(model["scenarios"]) != 3:
        raise SupervisedBlueprintError("commercial model requires downside, base and upside scenarios")
    if model.get("economics") is not None:
        economics = _required_mapping(model.get("economics"), "commercial_model.economics")
        contribution_margin = _decimal(
            economics.get("incremental_contribution_margin"),
            "commercial_model.economics.incremental_contribution_margin",
        )
        if contribution_margin >= 1:
            raise SupervisedBlueprintError("incremental_contribution_margin must be a decimal below 1")
        _decimal(
            economics.get("implementation_investment"),
            "commercial_model.economics.implementation_investment",
        )
        for index, scenario in enumerate(model["scenarios"]):
            realisation = _decimal(
                scenario.get("year_one_realisation_rate"),
                f"commercial_model.scenarios[{index}].year_one_realisation_rate",
            )
            if realisation > 1:
                raise SupervisedBlueprintError("year_one_realisation_rate must not exceed 1")

    strategy = _required_mapping(intake.get("strategy"), "strategy")
    _required_mapping(strategy.get("constraint"), "strategy.constraint")
    _required_mapping(strategy.get("advantage"), "strategy.advantage")
    if len(_required_list(strategy.get("recommendations"), "strategy.recommendations")) != 3:
        raise SupervisedBlueprintError("strategy requires exactly three prioritised recommendations")
    _required_mapping(intake.get("creative_territory"), "creative_territory")
    _required_mapping(intake.get("growth_engine"), "growth_engine")
    _required_list(intake.get("roadmap"), "roadmap")


def build_evidence_ledger(intake: Mapping[str, Any]) -> dict[str, Any]:
    validate_intake(intake)
    entries = [dict(item) for item in intake["evidence_ledger"]]
    version = _package_version(intake)
    return {
        "ledger_id": f"{intake['identity']['client_id']}-evidence-ledger-v{version}",
        "workspace_id": intake["identity"]["workspace_id"],
        "client_id": intake["identity"]["client_id"],
        "fictional_demonstration": True,
        "allowed_classifications": list(EVIDENCE_CLASSIFICATIONS),
        "entries": entries,
        "gaps": [str(item) for item in intake.get("evidence_gaps") or []],
        "verified_evidence_count": sum(
            item["classification"].startswith("VERIFIED") for item in entries
        ),
        "notice": (
            "This fictional fixture contains no verified client evidence. Verified external sources may describe "
            "the real market context, but they do not verify the fictional company's performance. Numeric company "
            "inputs remain assumptions and commercial outputs remain modelled scenarios."
        ),
    }


def _scenario_values(raw: Mapping[str, Any], prefix: str) -> tuple[Decimal, Decimal, Decimal]:
    return (
        _decimal(raw.get("annual_sessions"), f"{prefix}.annual_sessions"),
        _decimal(raw.get("conversion_rate"), f"{prefix}.conversion_rate"),
        _decimal(raw.get("average_order_value"), f"{prefix}.average_order_value"),
    )


def build_commercial_model(intake: Mapping[str, Any]) -> dict[str, Any]:
    validate_intake(intake)
    raw = intake["commercial_model"]
    baseline_sessions, baseline_conversion, baseline_aov = _scenario_values(raw["baseline"], "baseline")
    if baseline_conversion >= 1:
        raise SupervisedBlueprintError("conversion_rate must be expressed as a decimal below 1")
    baseline_revenue = baseline_sessions * baseline_conversion * baseline_aov
    economics = raw.get("economics")
    contribution_margin = (
        Decimal(str(economics["incremental_contribution_margin"]))
        if isinstance(economics, Mapping)
        else None
    )
    implementation_investment = (
        Decimal(str(economics["implementation_investment"]))
        if isinstance(economics, Mapping)
        else None
    )
    scenarios: list[dict[str, Any]] = []
    expected_names = ("Downside", "Base", "Upside")
    for expected, item in zip(expected_names, raw["scenarios"]):
        candidate = _required_mapping(item, f"scenario.{expected}")
        if candidate.get("name") != expected:
            raise SupervisedBlueprintError("scenarios must be ordered Downside, Base, Upside")
        sessions, conversion, aov = _scenario_values(candidate, f"scenario.{expected}")
        if conversion >= 1:
            raise SupervisedBlueprintError("conversion_rate must be expressed as a decimal below 1")
        revenue = sessions * conversion * aov
        incremental = revenue - baseline_revenue
        scenario = {
            "name": expected,
            "annual_sessions": int(sessions),
            "conversion_rate": float(conversion),
            "average_order_value": float(aov),
            "annual_revenue": int(revenue.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "incremental_annual_revenue": int(incremental.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "classification": "MODELLED",
            "scenario_not_forecast": True,
        }
        if contribution_margin is not None and implementation_investment is not None:
            realisation = Decimal(str(candidate["year_one_realisation_rate"]))
            realised_revenue = incremental * realisation
            contribution = realised_revenue * contribution_margin
            net_after_investment = contribution - implementation_investment
            monthly_contribution = contribution / Decimal("12")
            scenario.update(
                {
                    "year_one_realisation_rate": float(realisation),
                    "year_one_incremental_revenue": int(
                        realised_revenue.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                    ),
                    "year_one_incremental_contribution": int(
                        contribution.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                    ),
                    "year_one_net_after_investment": int(
                        net_after_investment.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                    ),
                    "illustrative_payback_months": (
                        float(
                            (implementation_investment / monthly_contribution).quantize(
                                Decimal("0.1"), rounding=ROUND_HALF_UP
                            )
                        )
                        if monthly_contribution > 0
                        else None
                    ),
                }
            )
        scenarios.append(scenario)
    if [item["annual_revenue"] for item in scenarios] != sorted(item["annual_revenue"] for item in scenarios):
        raise SupervisedBlueprintError("scenario revenue must increase from downside to upside")

    base = scenarios[1]
    traffic_effect = (Decimal(str(base["annual_sessions"])) - baseline_sessions) * baseline_conversion * baseline_aov
    conversion_effect = Decimal(str(base["annual_sessions"])) * (Decimal(str(base["conversion_rate"])) - baseline_conversion) * baseline_aov
    aov_effect = Decimal(str(base["annual_sessions"])) * Decimal(str(base["conversion_rate"])) * (Decimal(str(base["average_order_value"])) - baseline_aov)
    bridge_total = traffic_effect + conversion_effect + aov_effect
    if int(bridge_total.quantize(Decimal("1"))) != base["incremental_annual_revenue"]:
        raise SupervisedBlueprintError("sequential commercial bridge does not reconcile")

    investment_case = {
        "status": "incomplete",
        "missing_inputs": list(raw.get("missing_investment_inputs") or []),
        "warning": "Incremental revenue does not establish incremental profit, return or payback.",
    }
    if contribution_margin is not None and implementation_investment is not None:
        investment_case = {
            "status": "illustrative_assumption_case",
            "incremental_contribution_margin": float(contribution_margin),
            "implementation_investment": int(implementation_investment),
            "unresolved_inputs": list(raw.get("unresolved_inputs") or []),
            "warning": (
                "The contribution, investment and payback figures are MODELLED from ASSUMPTION inputs. "
                "They are not profit forecasts or an approved investment case."
            ),
        }

    return {
        "model_id": (
            f"{intake['identity']['client_id']}-ecommerce-opportunity-"
            f"v{_package_version(intake)}"
        ),
        "model_type": "ecommerce",
        "currency": str(raw.get("currency") or "GBP"),
        "period": "annualised run-rate at scenario inputs",
        "classification": "MODELLED",
        "scenario_not_forecast": True,
        "input_evidence_ids": list(raw["input_evidence_ids"]),
        "baseline": {
            "annual_sessions": int(baseline_sessions),
            "conversion_rate": float(baseline_conversion),
            "average_order_value": float(baseline_aov),
            "annual_revenue": int(baseline_revenue.quantize(Decimal("1"))),
            "classification": "MODELLED FROM ASSUMPTIONS",
        },
        "scenarios": scenarios,
        "base_scenario_bridge": [
            {"lever": "Traffic", "incremental_annual_revenue": int(traffic_effect.quantize(Decimal("1")))},
            {"lever": "Conversion", "incremental_annual_revenue": int(conversion_effect.quantize(Decimal("1")))},
            {"lever": "Average order value", "incremental_annual_revenue": int(aov_effect.quantize(Decimal("1")))},
        ],
        "investment_case": investment_case,
        "warnings": [
            "Every input in this fictional demonstration is an ASSUMPTION.",
            "These annualised scenarios are not forecasts, targets or promised results.",
            "Company revenue impact depends on ramp, cannibalisation, returns, margin, capacity and investment.",
        ],
    }


def _evidence_refs(value: Mapping[str, Any]) -> list[str]:
    return [str(item) for item in value.get("evidence_ids") or []]


def build_blueprint(intake: Mapping[str, Any], model: Mapping[str, Any]) -> dict[str, Any]:
    validate_intake(intake)
    company = intake["identity"]["company_name"]
    strategy = intake["strategy"]
    creative = intake["creative_territory"]
    base = model["scenarios"][1]
    base_economics = ""
    if "year_one_net_after_investment" in base:
        base_economics = (
            f" At the assumed ramp, contribution margin and £{model['investment_case']['implementation_investment']:,} "
            f"investment, the first-year net contribution proxy is £{base['year_one_net_after_investment']:,}."
        )
    chapters = [
        {
            "title": "The Opportunity",
            "argument": (
                f"{company} could test an annualised ecommerce revenue scenario of "
                f"£{base['annual_revenue']:,}, £{base['incremental_annual_revenue']:,} above the assumed baseline."
                f"{base_economics}"
            ),
            "classification": "MODELLED",
            "evidence_ids": list(model["input_evidence_ids"]),
            "decision": "Validate the baseline and economics before treating the scenario as an investment case.",
        },
        {
            "title": "The Constraint",
            "argument": strategy["constraint"]["statement"],
            "classification": "ASSUMPTION",
            "evidence_ids": _evidence_refs(strategy["constraint"]),
            "decision": strategy["constraint"]["falsification_test"],
        },
        {
            "title": "The Advantage",
            "argument": strategy["advantage"]["statement"],
            "classification": "ASSUMPTION",
            "evidence_ids": _evidence_refs(strategy["advantage"]),
            "decision": strategy["advantage"]["validation_test"],
        },
        {
            "title": "The Strategy",
            "argument": strategy["thesis"],
            "classification": "ASSUMPTION",
            "evidence_ids": sorted({ref for item in strategy["recommendations"] for ref in _evidence_refs(item)}),
            "decision": "Approve only the next tests, not the modelled revenue outcome.",
            "recommendations": [dict(item) for item in strategy["recommendations"]],
        },
        {
            "title": "The Creative Future",
            "argument": f"{creative['name']}: {creative['platform']}",
            "classification": "CREATIVE ILLUSTRATION",
            "evidence_ids": _evidence_refs(creative),
            "decision": creative["validation_test"],
            "territory": dict(creative),
        },
        {
            "title": "The Growth Engine",
            "argument": intake["growth_engine"]["thesis"],
            "classification": "ASSUMPTION",
            "evidence_ids": _evidence_refs(intake["growth_engine"]),
            "decision": intake["growth_engine"]["scale_gate"],
            "channels": [dict(item) for item in intake["growth_engine"]["channels"]],
            "measurement": [dict(item) for item in intake["growth_engine"]["measurement"]],
        },
        {
            "title": "The Next 12 Months",
            "argument": "A staged validation programme protects cash while the business replaces assumptions with evidence.",
            "classification": "ASSUMPTION",
            "evidence_ids": sorted({ref for item in intake["roadmap"] for ref in _evidence_refs(item)}),
            "decision": (
                "Matt approves the exact client-facing artefact before release. The founder then decides whether "
                "the verified economics justify the next bounded investment."
            ),
            "phases": [dict(item) for item in intake["roadmap"]],
        },
    ]
    if tuple(item["title"] for item in chapters) != BLUEPRINT_CHAPTERS:
        raise SupervisedBlueprintError("Blueprint chapter contract is incomplete")
    return {
        "blueprint_id": (
            f"{intake['identity']['client_id']}-growth-blueprint-demo-"
            f"v{_package_version(intake)}"
        ),
        "title": f"Narratiive Growth Blueprint - {company}",
        "status": "INTERNAL REVIEW DRAFT - HUMAN APPROVAL REQUIRED",
        "fictional_demonstration": True,
        "canon_relationship": (
            "Additive Issue #471/#473 demonstration profile. The checksum-locked 30-slide production canon remains unchanged."
        ),
        "opening_slide_functions": list(OPENING_SLIDE_FUNCTIONS),
        "chapters": chapters,
        "commercial_model_id": model["model_id"],
        "release_state": "pending_human_approval",
        "external_action_taken": False,
    }


def _source_notes(refs: Sequence[str], ledger_by_id: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(
        f"{ref} [{ledger_by_id[ref]['classification']}]: {ledger_by_id[ref]['claim']}"
        for ref in refs
    ) or ("No verified evidence supplied; claim remains an explicit assumption or illustration.",)


def build_presentation_specification(
    intake: Mapping[str, Any],
    ledger: Mapping[str, Any],
    model: Mapping[str, Any],
    blueprint: Mapping[str, Any],
) -> PresentationSpecification:
    company = intake["identity"]["company_name"]
    ledger_by_id = {item["evidence_id"]: item for item in ledger["entries"]}
    chapters = {item["title"]: item for item in blueprint["chapters"]}
    strategy = intake["strategy"]
    creative = intake["creative_territory"]
    presentation = intake.get("presentation") or {}
    base = model["scenarios"][1]
    refs = tuple(model["input_evidence_ids"])
    has_economics = "year_one_net_after_investment" in base
    base_decision = (
        f"The base case produces a £{base['year_one_net_after_investment']:,} first-year contribution proxy after "
        f"£{model['investment_case']['implementation_investment']:,} of assumed investment. Verify every input before committing."
        if has_economics
        else "The revenue headroom needs contribution, investment and ramp evidence before it can support a decision."
    )
    rows = [
        {
            "title": f"Where {company} could go",
            "takeaway": presentation.get("destination_takeaway") or strategy["thesis"],
            "body": (
                f"The base scenario reaches £{base['annual_revenue']:,} in annualised online revenue, but the strategic prize "
                "is a defensible reason to choose and return. This is a scenario, not a forecast."
            ),
            "layout": "single_thesis_page",
            "classification": "MODELLED",
            "refs": refs,
            "content": {
                "brand_name": company,
                "platform": presentation.get("platform") or strategy["recommendations"][0]["name"],
                "subtitle": presentation.get("subtitle") or "A conditional route from attention to repeat purchase",
            },
        },
        {
            "title": "What the commercial opportunity looks like",
            "takeaway": (
                f"The base scenario adds £{base['incremental_annual_revenue']:,} of annualised revenue headroom. "
                f"{base_decision}"
            ),
            "body": "The downside loses money after assumed investment. The base and upside only become investable if the ramp, contribution and cost assumptions survive verification.",
            "layout": "commercial_model",
            "classification": "MODELLED - SCENARIO, NOT FORECAST",
            "refs": refs,
            "content": {
                "model_type": "ecommerce",
                "scenarios": model["scenarios"],
                "baseline": model["baseline"],
                "investment_case": model["investment_case"],
            },
        },
        {
            "title": "What currently prevents growth",
            "takeaway": strategy["constraint"]["statement"],
            "body": f"Working diagnosis only. Falsify it by: {strategy['constraint']['falsification_test']}",
            "layout": "provocation_page",
            "classification": "ASSUMPTION",
            "refs": tuple(strategy["constraint"]["evidence_ids"]),
            "content": presentation.get("constraint_content") or {"left_label": "CURRENT PATTERN", "left_headline": "Reach before reason", "left_detail": "Paid attention is being asked to create the distinction.", "right_label": "WORKING CONSTRAINT", "right_headline": "No proven repeat path"},
        },
        {
            "title": "The strategic moves",
            "takeaway": presentation.get("strategic_moves_takeaway") or ", then ".join(item["name"].lower() for item in strategy["recommendations"]) + ".",
            "body": "Each move changes a customer decision and has a measurable commercial gate. Larger investment remains conditional on evidence.",
            "layout": "constraint_priority_roadmap",
            "classification": "ASSUMPTION",
            "refs": tuple(sorted({ref for item in strategy["recommendations"] for ref in item["evidence_ids"]})),
            "content": {"phases": [[item["name"].upper(), item["lever"], item["test"]] for item in strategy["recommendations"]]},
        },
        {
            "title": "What the future could look like",
            "takeaway": creative["platform"],
            "body": creative["description"],
            "layout": "creative_proof" if creative.get("asset_path") else "creative_direction",
            "classification": "CREATIVE ILLUSTRATION",
            "refs": tuple(creative["evidence_ids"]),
            "content": {
                "asset_path": creative.get("asset_path"),
                "image_alt": creative.get("asset_alt"),
                "creative_line": creative["name"],
                "primary_phrase": creative["primary_phrase"],
                "bridge": "made",
                "secondary_phrase": creative["secondary_phrase"],
                "principles": creative["principles"],
            },
        },
        {
            "title": "The Opportunity",
            "takeaway": chapters["The Opportunity"]["argument"],
            "body": base_decision,
            "layout": "single_thesis_page",
            "classification": "MODELLED",
            "refs": tuple(chapters["The Opportunity"]["evidence_ids"]),
            "content": {"chapter_label": "CHAPTER 1 / THE OPPORTUNITY", "signal": "SCENARIO", "support": "Validate before investment"},
        },
        {
            "title": "The scenario bridge",
            "takeaway": "; ".join(
                f"{item['lever']} contributes £{item['incremental_annual_revenue']:,}"
                for item in model["base_scenario_bridge"]
            ) + ".",
            "body": f"The sequential bridge reconciles to £{base['incremental_annual_revenue']:,}. The attribution order is a modelling convention.",
            "layout": "evidence_ladder",
            "classification": "MODELLED",
            "refs": refs,
            "content": {"chapter_label": "CHAPTER 1 / THE OPPORTUNITY"},
        },
        {
            "title": "The Constraint",
            "takeaway": chapters["The Constraint"]["argument"],
            "body": chapters["The Constraint"]["decision"],
            "layout": "evidence_ladder",
            "classification": "ASSUMPTION",
            "refs": tuple(chapters["The Constraint"]["evidence_ids"]),
            "content": {"chapter_label": "CHAPTER 2 / THE CONSTRAINT"},
        },
        {
            "title": "What would disprove the diagnosis",
            "takeaway": presentation.get("falsification_takeaway") or "The diagnosis must be rejected if its stated falsification test fails.",
            "body": strategy["constraint"]["falsification_test"],
            "layout": "test_plan",
            "classification": "ASSUMPTION",
            "refs": tuple(chapters["The Constraint"]["evidence_ids"]),
            "content": {"chapter_label": "CHAPTER 2 / THE CONSTRAINT"},
        },
        {
            "title": "The Advantage",
            "takeaway": chapters["The Advantage"]["argument"],
            "body": chapters["The Advantage"]["decision"],
            "layout": "market_gap_map",
            "classification": "ASSUMPTION",
            "refs": tuple(chapters["The Advantage"]["evidence_ids"]),
            "content": presentation.get("market_gap_content") or {"chapter_label": "CHAPTER 3 / THE ADVANTAGE", "x_axis": ["GENERIC", "DISTINCTIVE"], "y_axis": ["LOW PROOF", "HIGH PROOF"], "competitors": [], "current_position": [f"{company} TODAY", 42, 44], "future_position": ["TEST TERRITORY", 78, 80], "market_gap": strategy["advantage"]["statement"], "audience": "Target customer definition requires validation", "competitor_miss": "Validation required. No competitor position is asserted in this fictional fixture."},
        },
        {
            "title": "The advantage needs proof",
            "takeaway": "Founder conviction can frame a hypothesis. Customer choice data must decide whether the advantage is real.",
            "body": strategy["advantage"]["validation_test"],
            "layout": "customer_evidence_board",
            "classification": "ASSUMPTION",
            "refs": tuple(chapters["The Advantage"]["evidence_ids"]),
            "content": presentation.get("customer_evidence_content") or {"chapter_label": "CHAPTER 3 / THE ADVANTAGE", "language_status": "CUSTOMER EVIDENCE REQUIRED", "customer_language": ["Observe the occasion", "Test the proposition", "Measure willingness to pay"], "signals": [["FOUNDER VIEW", "A proposed category to own"], ["CUSTOMER DATA", "Not yet supplied"], ["CHOICE TEST", "Required before selection"]], "interpretation": "The territory remains a hypothesis until observed behaviour and customer choice evidence support it."},
        },
        {
            "title": "The Strategy",
            "takeaway": strategy["thesis"],
            "body": chapters["The Strategy"]["decision"],
            "layout": "narrative_platform_framework",
            "classification": "ASSUMPTION",
            "refs": tuple(chapters["The Strategy"]["evidence_ids"]),
            "content": presentation.get("strategy_framework_content") or {"chapter_label": "CHAPTER 4 / THE STRATEGY", "steps": [["TENSION", strategy["constraint"]["statement"]], ["SHIFT", strategy["recommendations"][0]["action"]], ["RESOLUTION", strategy["recommendations"][2]["action"]]], "banner": strategy["thesis"]},
        },
        {
            "title": "Three moves, three tests",
            "takeaway": "The strategy connects each recommendation to a measurable commercial lever.",
            "body": "The work stays reversible until conversion, repeat and contribution evidence justify larger investment.",
            "layout": "messaging_territories",
            "classification": "ASSUMPTION",
            "refs": tuple(chapters["The Strategy"]["evidence_ids"]),
            "content": {"chapter_label": "CHAPTER 4 / THE STRATEGY", "territories": [[item["name"].upper(), item["lever"], item["trade_off"], item["test"], item["owner"]] for item in strategy["recommendations"]], "verbal_assets": ["Specific promise", "Visible proof"], "tone_motion_cues": ["Direct", "Useful"], "recurring_formats": ["Claim and proof", "Test and result"]},
        },
        {
            "title": "The Creative Future",
            "takeaway": chapters["The Creative Future"]["argument"],
            "body": creative["description"],
            "layout": "creative_direction",
            "classification": "CREATIVE ILLUSTRATION",
            "refs": tuple(chapters["The Creative Future"]["evidence_ids"]),
            "content": {"chapter_label": "CHAPTER 5 / THE CREATIVE FUTURE", "primary_phrase": creative["primary_phrase"], "bridge": "meets", "secondary_phrase": creative["secondary_phrase"], "principles": creative["principles"]},
        },
        {
            "title": "The campaign behaviour",
            "takeaway": creative["platform"],
            "body": creative["example_execution"],
            "layout": "creative_principles",
            "classification": "CREATIVE ILLUSTRATION",
            "refs": tuple(chapters["The Creative Future"]["evidence_ids"]),
            "content": {"chapter_label": "CHAPTER 5 / THE CREATIVE FUTURE", "principles": creative["principles"]},
        },
        {
            "title": "The Growth Engine",
            "takeaway": chapters["The Growth Engine"]["argument"],
            "body": chapters["The Growth Engine"]["decision"],
            "layout": "channel_role_map",
            "classification": "ASSUMPTION",
            "refs": tuple(chapters["The Growth Engine"]["evidence_ids"]),
            "content": {"chapter_label": "CHAPTER 6 / THE GROWTH ENGINE", "rows": [[item["channel"], item["role"], item["gate"]] for item in chapters["The Growth Engine"]["channels"]]},
        },
        {
            "title": "Measurement before scale",
            "takeaway": "Leading indicators must move before the plan releases larger media or inventory commitments.",
            "body": "Baseline every measure before the first test. Record cost, capacity and confidence alongside performance.",
            "layout": "priority_matrix_plus_measurement_stack",
            "classification": "ASSUMPTION",
            "refs": tuple(chapters["The Growth Engine"]["evidence_ids"]),
            "content": {"chapter_label": "CHAPTER 6 / THE GROWTH ENGINE", "rows": [[item["level"], item["metrics"]] for item in chapters["The Growth Engine"]["measurement"]]},
        },
        {
            "title": "The Next 12 Months",
            "takeaway": chapters["The Next 12 Months"]["argument"],
            "body": "Start with a 12-week proof phase. Release the remaining roadmap only when baseline, contribution, customer choice and capacity evidence pass their gates.",
            "layout": "constraint_priority_roadmap",
            "classification": "ASSUMPTION",
            "refs": tuple(chapters["The Next 12 Months"]["evidence_ids"]),
            "content": {"chapter_label": "CHAPTER 7 / THE NEXT 12 MONTHS", "phases": [[item["period"], item["name"], item["outcome"]] for item in chapters["The Next 12 Months"]["phases"][:3]]},
        },
        {
            "title": "Evidence and assumptions ledger",
            "takeaway": "Every material claim resolves to an explicit evidence class and validation step.",
            "body": ledger["notice"],
            "layout": "source_register",
            "classification": "EVIDENCE REGISTER",
            "refs": tuple(item["evidence_id"] for item in ledger["entries"]),
            "content": {"chapter_label": "GOVERNANCE / EVIDENCE", "source_register_entries": ledger["entries"], "entries": ledger["entries"], "ledger_profile": "founder"},
        },
        {
            "title": "The founder decision",
            "takeaway": f"Fund a bounded proof phase, not the £{base['incremental_annual_revenue']:,} outcome.",
            "body": "Before client release, Matt approves the exact artefact. The founder then decides whether to fund 12 weeks of verification against explicit stop and scale gates.",
            "layout": "closing_mandate",
            "classification": "HUMAN DECISION REQUIRED",
            "refs": tuple(item["evidence_id"] for item in ledger["entries"]),
            "content": {"chapter_label": "DECISION / NEXT COMMITMENT", "lines": ["Fund proof,", "not scale.", "Release investment only as evidence improves."], "next_step": "Verify the baseline, cost the 12-week proof phase and approve only the first decision gate."},
        },
    ]
    if len(ledger["entries"]) > 12:
        register_index = next(
            index for index, row in enumerate(rows) if row["layout"] == "source_register"
        )
        register_row = rows[register_index]
        chunks = [ledger["entries"][:8], ledger["entries"][8:]]
        register_rows = []
        for page, entries in enumerate(chunks, 1):
            register_rows.append({
                **register_row,
                "title": f"Evidence and assumptions ledger ({page} of {len(chunks)})",
                "refs": tuple(item["evidence_id"] for item in entries),
                "content": {
                    **register_row["content"],
                    "entries": entries,
                    "source_register_entries": entries,
                },
            })
        rows[register_index:register_index + 1] = register_rows
    slides: list[PresentationSlideSpec] = []
    for number, row in enumerate(rows, 1):
        slide_refs = tuple(ref for ref in row["refs"] if ref in ledger_by_id)
        slides.append(
            PresentationSlideSpec(
                slide_no=number,
                title=row["title"],
                takeaway=row["takeaway"],
                body=row["body"],
                visual_treatment=row["layout"],
                evidence_refs=slide_refs,
                source_notes=_source_notes(slide_refs, ledger_by_id),
                layout_type=row["layout"],
                citation_labels=slide_refs or ("NO VERIFIED EVIDENCE",),
                claim_status=row["classification"],
                content_data=row["content"],
            )
        )
    return PresentationSpecification(
        specification_id=(
            f"{intake['identity']['client_id']}-supervised-demo-presentation-"
            f"v{_package_version(intake)}"
        ),
        source_blueprint_id=blueprint["blueprint_id"],
        source_blueprint_version=_package_version(intake),
        workspace_id=intake["identity"]["workspace_id"],
        client_id=intake["identity"]["client_id"],
        title=blueprint["title"],
        status="ready_for_production",
        template_source=(
            "Existing Narratiive local Artifact Tool renderer. Seven-chapter Issue #471 demonstration profile; "
            + (
                "Issue #473 founder-quality controls; "
                if _package_version(intake) >= 2
                else ""
            )
            + "locked production canon unchanged."
        ),
        slides=tuple(slides),
        source_checksum=_checksum(blueprint),
        notes=(
            "INTERNAL FICTIONAL DEMONSTRATION - HUMAN APPROVAL REQUIRED",
            "All figures are modelled from assumptions. Scenarios are not forecasts.",
        ),
    )


def run_independent_qa(
    intake: Mapping[str, Any],
    ledger: Mapping[str, Any],
    model: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    presentation: PresentationSpecification,
) -> dict[str, Any]:
    chapter_titles = tuple(item.get("title") for item in blueprint.get("chapters") or [])
    opening_titles = tuple(slide.title for slide in presentation.slides[:5])
    ledger_ids = {item["evidence_id"] for item in ledger["entries"]}
    cited_ids = {
        ref
        for chapter in blueprint["chapters"]
        for ref in chapter.get("evidence_ids") or []
    }
    version = _package_version(intake)
    base = model["scenarios"][1]
    economics_required = version >= 2
    economics_complete = (
        model["investment_case"].get("status") == "illustrative_assumption_case"
        and all(
            key in scenario
            for scenario in model["scenarios"]
            for key in (
                "year_one_realisation_rate",
                "year_one_incremental_contribution",
                "year_one_net_after_investment",
            )
        )
        and model["scenarios"][0].get("year_one_net_after_investment", 0) < 0
        and base.get("year_one_net_after_investment", 0) > 0
    )
    creative_asset = str(intake["creative_territory"].get("asset_path") or "").strip()
    checks = {
        "fictional_status_is_explicit": intake["identity"].get("fictional") is True and blueprint.get("fictional_demonstration") is True,
        "evidence_classes_are_allowed": all(item["classification"] in EVIDENCE_CLASSIFICATIONS for item in ledger["entries"]),
        "no_fictional_verified_client_evidence": not any(item["classification"] == "VERIFIED CLIENT" for item in ledger["entries"]),
        "all_blueprint_evidence_refs_resolve": cited_ids.issubset(ledger_ids),
        "three_scenarios_present": [item["name"] for item in model["scenarios"]] == ["Downside", "Base", "Upside"],
        "scenarios_are_not_forecasts": model.get("scenario_not_forecast") is True and all(item.get("scenario_not_forecast") is True for item in model["scenarios"]),
        "commercial_math_reconciles": sum(item["incremental_annual_revenue"] for item in model["base_scenario_bridge"]) == model["scenarios"][1]["incremental_annual_revenue"],
        "investment_case_exposes_downside_and_first_year_net": (
            economics_complete if economics_required else True
        ),
        "seven_chapters_are_present_in_order": chapter_titles == BLUEPRINT_CHAPTERS,
        "opening_five_are_present": len(opening_titles) == 5,
        "opening_five_cover_required_functions": all(
            phrase in " ".join((presentation.slides[index].title, presentation.slides[index].takeaway)).casefold()
            for index, phrase in enumerate(("could go", "commercial opportunity", "prevents growth", "strategic moves", "future could look"))
        ),
        "creative_territory_is_tangible": (
            bool(intake["creative_territory"].get("example_execution"))
            and chapters_by_title(blueprint)["The Creative Future"]["classification"]
            == "CREATIVE ILLUSTRATION"
            and (bool(creative_asset) if version >= 2 else True)
        ),
        "recommendations_link_to_levers_and_tests": all(item.get("lever") and item.get("test") and item.get("trade_off") for item in intake["strategy"]["recommendations"]),
        "approval_is_pending": blueprint.get("release_state") == "pending_human_approval",
        "external_action_is_false": blueprint.get("external_action_taken") is False,
        "presentation_has_evidence_register": any(slide.layout_type == "source_register" for slide in presentation.slides),
        "presentation_ends_on_founder_decision": (
            presentation.slides[-1].title == "The founder decision" if version >= 2 else True
        ),
    }
    findings = []
    if not all(checks.values()):
        findings.extend(f"FAIL: {name}" for name, passed in checks.items() if not passed)
    findings.extend(
        [
            "All commercial inputs are assumptions; replace them with authorised client evidence before real use.",
            (
                "Contribution margin, ramp and implementation investment are illustrative assumptions; "
                "actual returns, capacity, cannibalisation and working-capital effects remain unresolved."
                if economics_complete
                else "Contribution margin, implementation cost, returns, ramp, capacity and cannibalisation remain unresolved."
            ),
            "Constraint, advantage and creative territory require founder and customer validation.",
            "Rendered files remain internal review copies until Matt approves the exact checksum.",
        ]
    )
    return {
        "review_id": (
            f"{intake['identity']['client_id']}-independent-qa-v{version}"
        ),
        "reviewer_role": "Independent Quality Reviewer",
        "independence": "Deterministic adversarial checks run after specialist outputs; no content was silently repaired.",
        "status": "PASS_FOR_HUMAN_REVIEW" if all(checks.values()) else "REVISE",
        "checks": checks,
        "findings": findings,
        "recommendation": (
            "Advance the fictional demonstration to Matt's review. Do not release or reuse its assumptions as client evidence."
            if all(checks.values())
            else "Return the named failures to the responsible specialist."
        ),
    }


def chapters_by_title(blueprint: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item["title"]): item for item in blueprint.get("chapters") or []}


def _register_json(
    catalog: FileArtifactCatalog,
    *,
    run_id: str,
    stage_id: str,
    artifact_type: str,
    value: Mapping[str, Any],
    parents: Sequence[str] = (),
    producer: str,
) -> ArtifactRecord:
    return catalog.register(
        run_id=run_id,
        stage_id=stage_id,
        artifact_type=artifact_type,
        content=json.dumps(value, indent=2, sort_keys=True) + "\n",
        parent_artifact_ids=parents,
        producer=producer,
        extension=".json",
        metadata={"fictional_demonstration": True, "approval_required": True},
    )


def build_supervised_blueprint_package(
    intake: Mapping[str, Any],
    *,
    artifact_catalog: FileArtifactCatalog,
) -> SupervisedBlueprintPackage:
    """Run the vertical slice through the existing five specialist owners."""
    validate_intake(intake)
    run_id = str(intake["identity"]["run_id"])
    intake_record = _register_json(
        artifact_catalog,
        run_id=run_id,
        stage_id="research_analyst",
        artifact_type="structured_client_intake",
        value=dict(intake),
        producer="Research Analyst",
    )
    ledger = build_evidence_ledger(intake)
    ledger_record = _register_json(
        artifact_catalog,
        run_id=run_id,
        stage_id="research_analyst",
        artifact_type="evidence_ledger",
        value=ledger,
        parents=(intake_record.artifact.artifact_id,),
        producer="Research Analyst",
    )
    model = build_commercial_model(intake)
    model_record = _register_json(
        artifact_catalog,
        run_id=run_id,
        stage_id="strategy_director",
        artifact_type="commercial_opportunity_model",
        value=model,
        parents=(ledger_record.artifact.artifact_id,),
        producer="Strategy Director",
    )
    blueprint = build_blueprint(intake, model)
    blueprint_record = _register_json(
        artifact_catalog,
        run_id=run_id,
        stage_id="strategy_director",
        artifact_type="seven_chapter_growth_blueprint",
        value=blueprint,
        parents=(ledger_record.artifact.artifact_id, model_record.artifact.artifact_id),
        producer="Strategy Director",
    )
    creative_record = _register_json(
        artifact_catalog,
        run_id=run_id,
        stage_id="campaign_world_generator",
        artifact_type="creative_territory",
        value=dict(intake["creative_territory"]),
        parents=(blueprint_record.artifact.artifact_id,),
        producer="Campaign World Generator",
    )
    presentation = build_presentation_specification(intake, ledger, model, blueprint)
    presentation_record = _register_json(
        artifact_catalog,
        run_id=run_id,
        stage_id="creative_director",
        artifact_type="blueprint_presentation_specification",
        value=presentation.to_dict(),
        parents=(blueprint_record.artifact.artifact_id, creative_record.artifact.artifact_id),
        producer="Creative Director",
    )
    qa = run_independent_qa(intake, ledger, model, blueprint, presentation)
    qa_record = _register_json(
        artifact_catalog,
        run_id=run_id,
        stage_id="quality_reviewer",
        artifact_type="independent_quality_review",
        value=qa,
        parents=(presentation_record.artifact.artifact_id,),
        producer="Quality Reviewer",
    )
    approval = {
        "checkpoint_id": f"{run_id}-matt-approval",
        "status": "pending",
        "approver_role": "Matt",
        "decision_options": ["approve", "request_revision", "block"],
        "bound_blueprint_checksum": _checksum(blueprint),
        "bound_presentation_specification_checksum": _checksum(presentation.to_dict()),
        "bound_qa_checksum": _checksum(qa),
        "release_authorised": False,
        "external_action_taken": False,
        "instruction": "Record an authenticated human decision against these exact checksums before client-facing release.",
    }
    return SupervisedBlueprintPackage(
        intake=dict(intake),
        evidence_ledger=ledger,
        commercial_model=model,
        blueprint=blueprint,
        presentation=presentation,
        qa_report=qa,
        approval_checkpoint=approval,
        lineage=(intake_record, ledger_record, model_record, blueprint_record, creative_record, presentation_record, qa_record),
    )


def blueprint_markdown(package: SupervisedBlueprintPackage) -> str:
    model = package.commercial_model
    blueprint = package.blueprint
    lines = [
        f"# {blueprint['title']}",
        "",
        "> FICTIONAL DEMONSTRATION - INTERNAL REVIEW DRAFT - HUMAN APPROVAL REQUIRED",
        "> All commercial figures are modelled scenarios from assumptions. They are not forecasts or promised results.",
        "",
        "## Executive opening",
        "",
    ]
    for number, slide in enumerate(package.presentation.slides[:5], 1):
        lines.extend([f"### {number}. {slide.title}", "", slide.takeaway, "", slide.body, "", f"Classification: **{slide.claim_status}**", ""])
    for chapter in blueprint["chapters"]:
        lines.extend(
            [
                f"## {chapter['title']}",
                "",
                chapter["argument"],
                "",
                f"Classification: **{chapter['classification']}**",
                "",
                f"Decision or validation gate: {chapter['decision']}",
                "",
            ]
        )
        if chapter.get("recommendations"):
            for item in chapter["recommendations"]:
                lines.append(f"- **{item['name']}** - {item['action']} Test: {item['test']} Trade-off: {item['trade_off']}")
            lines.append("")
        if chapter.get("channels"):
            for item in chapter["channels"]:
                lines.append(f"- **{item['channel']}** - {item['role']} Gate: {item['gate']}")
            lines.append("")
        if chapter.get("phases"):
            for item in chapter["phases"]:
                lines.append(f"- **{item['period']}: {item['name']}** - {item['outcome']} Owner: {item['owner']}")
            lines.append("")
    lines.extend(
        [
            "## Commercial scenarios",
            "",
            (
                "| Scenario | Annual revenue | Increment vs baseline | First-year contribution | Net after investment |"
                if "year_one_incremental_contribution" in model["scenarios"][0]
                else "| Scenario | Sessions | Conversion | AOV | Annual revenue | Increment vs baseline |"
            ),
            (
                "| --- | ---: | ---: | ---: | ---: |"
                if "year_one_incremental_contribution" in model["scenarios"][0]
                else "| --- | ---: | ---: | ---: | ---: | ---: |"
            ),
        ]
    )
    for item in model["scenarios"]:
        if "year_one_incremental_contribution" in item:
            lines.append(
                f"| {item['name']} | £{item['annual_revenue']:,} | £{item['incremental_annual_revenue']:,} | "
                f"£{item['year_one_incremental_contribution']:,} | £{item['year_one_net_after_investment']:,} |"
            )
        else:
            lines.append(
                f"| {item['name']} | {item['annual_sessions']:,} | {item['conversion_rate']:.1%} | "
                f"£{item['average_order_value']:,.0f} | £{item['annual_revenue']:,} | £{item['incremental_annual_revenue']:,} |"
            )
    lines.extend(
        [
            "",
            "## Approval",
            "",
            "Status: **PENDING**",
            "",
            "Quality review is advisory. Matt must approve the commercial recommendation and the exact client-facing artefact before release.",
            "",
        ]
    )
    return "\n".join(lines)


def qa_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Independent QA report",
        "",
        f"Status: **{report['status']}**",
        "",
        str(report["independence"]),
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {'PASS' if passed else 'FAIL'} - {name.replace('_', ' ')}" for name, passed in report["checks"].items())
    lines.extend(["", "## Findings and blockers", ""])
    lines.extend(f"- {item}" for item in report["findings"])
    lines.extend(["", "## Recommendation", "", str(report["recommendation"]), ""])
    return "\n".join(lines)
