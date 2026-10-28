"""Read-only structural readiness audit; never a strategy or release approval."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


VERSION = "7.1.0"
ACTS = (
    "case_for_change", "competitive_opportunity", "audience_intelligence",
    "strategic_answer", "commercial_and_creative_opportunity", "make_it_real",
)
CLAIM_STATUSES = {"verified", "interpreted", "modelled", "unverified"}


def audit_fieldwork_v71(package: Mapping[str, Any]) -> dict[str, Any]:
    """Identify missing v7.1 review inputs without trusting a quality-pass flag.

    Source verification, strategic judgement, visual inspection and human
    approval remain separate. A structurally complete register proves none of
    those activities. The caller must bind this report to the immutable package.
    """
    blockers: list[str] = []

    def require(condition: bool, reason: str) -> None:
        if not condition:
            blockers.append(reason)

    def text(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    require(package.get("contract_version") == VERSION, "wrong_contract_version")
    require(text(package.get("artifact_id")), "missing_artifact_identity")
    require(text(package.get("checksum")), "missing_artifact_checksum")
    require(package.get("acts") == list(ACTS), "six_act_argument_missing")
    claims = package.get("evidence_register")
    claims = claims if isinstance(claims, list) else []
    require(bool(claims), "missing_evidence_register")
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in claims:
        if not isinstance(item, Mapping):
            blockers.append("invalid_claim_record")
            continue
        identifier = item.get("claim_id")
        require(text(identifier) and identifier not in by_id, "invalid_or_duplicate_claim_id")
        if text(identifier):
            by_id[identifier] = item
        require(all(text(item.get(key)) for key in ("claim", "source", "date", "method")), "incomplete_claim_provenance")
        require(item.get("status") in CLAIM_STATUSES, "invalid_claim_status")
        require(type(item.get("slide")) is int and item["slide"] > 0, "missing_claim_slide")
        if item.get("status") == "unverified":
            require(text(item.get("validation_request")), "unverified_claim_without_request")

    thesis = package.get("opening_thesis")
    thesis = thesis if isinstance(thesis, Mapping) else {}
    for pillar in ("market", "brand", "audience"):
        refs = thesis.get(pillar)
        require(isinstance(refs, list) and bool(refs) and all(isinstance(ref, str) and ref in by_id for ref in refs), f"missing_{pillar}_thesis_evidence")
    challenged = package.get("challenged_claim_ids")
    require(
        isinstance(challenged, list) and len(challenged) == 5
        and all(isinstance(ref, str) and ref in by_id for ref in challenged)
        and len(set(challenged)) == 5,
        "five_challenged_claims_missing",
    )
    audit = package.get("competitor_ad_audit")
    audit = audit if isinstance(audit, Mapping) else {}
    require(all(text(audit.get(key)) for key in ("period", "sample", "method", "limitations")), "bounded_ad_audit_missing")
    require(isinstance(audit.get("executions"), list) and bool(audit["executions"]), "competitor_executions_missing")
    for execution in audit.get("executions", []) if isinstance(audit.get("executions"), list) else []:
        require(isinstance(execution, Mapping) and all(text(execution.get(key)) for key in ("brand", "asset_reference", "platform", "date", "premise", "format", "coding_rationale")), "incomplete_ad_execution")
    commercial = package.get("commercial_prize")
    commercial = commercial if isinstance(commercial, Mapping) else {}
    levers = commercial.get("levers")
    require(isinstance(levers, list) and 4 <= len(levers) <= 5, "four_to_five_commercial_levers_required")
    for lever in levers if isinstance(levers, list) else []:
        require(isinstance(lever, Mapping) and all(text(lever.get(key)) for key in ("lever", "marketing_mechanism", "modelled_impact", "basis")), "incomplete_commercial_lever")
    require(all(text(commercial.get(key)) for key in ("baseline_or_missing_inputs", "timeframe", "calculation", "sensitivities", "double_counting_control")), "commercial_model_basis_missing")
    require(commercial.get("outcome_type") in {"conditional_scenario", "supported_range", "missing_inputs"}, "commercial_certainty_unclassified")
    media = package.get("media_plan")
    media = media if isinstance(media, Mapping) else {}
    require(all(text(media.get(key)) for key in ("audience", "message", "platforms", "formats", "phasing", "paid_owned_earned", "budget_basis", "success_measures", "ninety_day_sequence")), "concrete_media_plan_missing")
    creative = package.get("creative_direction")
    creative = creative if isinstance(creative, Mapping) else {}
    require(all(text(creative.get(key)) for key in ("territory", "competitive_distinctiveness_basis", "visual_references", "execution_seeds")), "creative_direction_missing")
    require(bool(creative.get("illustrative_assets")) or bool(creative.get("prompts_and_slots")), "creative_visuals_or_honest_slots_missing")
    require(package.get("marketing_remit_only") is True, "marketing_remit_unconfirmed")
    return {
        "contract_version": VERSION,
        "artifact_id": package.get("artifact_id"),
        "checksum": package.get("checksum"),
        "structural_inputs_complete": not blockers,
        "blockers": sorted(set(blockers)),
        "source_verification": "not_performed_by_this_audit",
        "specialist_quality_review": "required_separately",
        "visual_review": "required_separately",
        "human_approval": "required_for_exact_version",
        "client_release_authorised": False,
    }
