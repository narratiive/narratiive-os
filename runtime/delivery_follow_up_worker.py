from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class DeliveryFollowUpPreparationError(ValueError):
    pass


class DeliveryFollowUpPreparationWorker:
    """Prepare the post-delivery measurement loop without changing external state."""

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = contract.get("workflow_context")
        if not isinstance(context, Mapping) or context.get("workflow_id") != "delivery_to_follow_up_next_action":
            raise DeliveryFollowUpPreparationError("follow-up preparation received an unsupported workflow")
        identity = contract.get("campaign_identity")
        evidence = contract.get("verified_delivery_evidence")
        client = contract.get("client_context")
        measurement = contract.get("measurement_context")
        if not all(isinstance(item, Mapping) for item in (identity, evidence, client, measurement)):
            raise DeliveryFollowUpPreparationError("follow-up preparation requires campaign, delivery, client and measurement context")
        if not evidence.get("delivery_package_checksum") or not evidence.get("delivered_asset_version_ids"):
            raise DeliveryFollowUpPreparationError("follow-up preparation requires exact verified delivery evidence")
        client_name = str(
            client.get("brand_name")
            or client.get("company_name")
            or client.get("company")
            or client.get("name")
            or "the client"
        )
        campaign_id = str(identity.get("campaign_id") or "")
        delivered_ids = [str(item) for item in evidence["delivered_asset_version_ids"]]
        review_window = str(measurement.get("review_window") or "after the agreed observation window")
        return {
            "recommended_follow_up": (
                f"Confirm {client_name} can access all {len(delivered_ids)} delivered versions, then review "
                f"campaign {campaign_id} performance {review_window}."
            ),
            "measurement_actions": [
                "Confirm tracking health before interpreting outcomes.",
                "Ingest Meta, TikTok and Google performance through read-only normalisation when mappings exist.",
                "Compare asset-level outcomes only where provider creative IDs map to exact Narratiive asset versions.",
                "Prepare evidence-graded insights and a human-reviewed creative iteration brief; do not alter spend or publish.",
            ],
            "draft_client_communication": (
                f"The approved asset suite for campaign {campaign_id} has been delivered. Please confirm access. "
                f"Once the agreed observation window has passed, we will review verified performance evidence and "
                "bring any proposed creative iteration back for approval before production or publication."
            ),
            "performance_ingestion_plan": {
                "campaign_id": campaign_id,
                "asset_version_ids": delivered_ids,
                "providers": ["meta", "tiktok", "google"],
                "mode": "read_only_normalised_ingestion",
                "tracking_must_be_verified": True,
                "provider_mapping_required": True,
            },
            "iteration_control": {
                "tony_role": "orchestrate_monitor_and_quality_check",
                "strategy_authority": "human",
                "insight_requires_evidence": True,
                "creative_iteration_requires_human_approval": True,
                "autonomous_publication_authorised": False,
                "autonomous_media_spend_authorised": False,
            },
            "external_action_taken": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }
