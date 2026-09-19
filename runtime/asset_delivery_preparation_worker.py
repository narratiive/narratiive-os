from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


class AssetDeliveryPreparationError(ValueError):
    pass


class AssetDeliveryPreparationWorker:
    """Assemble an approved asset suite into a non-delivering client package."""

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = contract.get("workflow_context")
        if not isinstance(context, Mapping) or context.get("workflow_id") != "asset_review_to_delivery_preparation":
            raise AssetDeliveryPreparationError("delivery preparation received an unsupported workflow")
        identity = contract.get("campaign_identity")
        assets = contract.get("reviewed_assets")
        manifest = contract.get("asset_manifest")
        approval = contract.get("asset_suite_approval")
        requirements = contract.get("delivery_requirements")
        if not all(isinstance(item, Mapping) for item in (identity, manifest, approval, requirements)):
            raise AssetDeliveryPreparationError("delivery preparation requires identity, manifest, approval and requirements")
        if not isinstance(assets, list) or not assets or not all(isinstance(item, Mapping) for item in assets):
            raise AssetDeliveryPreparationError("delivery preparation requires reviewed asset versions")
        if approval.get("decision") != "asset_suite_approval":
            raise AssetDeliveryPreparationError("delivery preparation requires exact asset-suite approval")
        approved_ids = [str(item) for item in approval.get("asset_version_ids") or []]
        version_ids = [str(item.get("asset_version_id") or "") for item in assets]
        if not approved_ids or len(set(approved_ids)) != len(approved_ids) or set(approved_ids) != set(version_ids):
            raise AssetDeliveryPreparationError("reviewed assets do not match exact approved version IDs")
        suite_checksum = str(approval.get("asset_suite_checksum") or "")
        if any(
            item.get("status") != "approved"
            or item.get("approval_status") != "approved"
            or item.get("source_asset_suite_checksum") != suite_checksum
            for item in assets
        ):
            raise AssetDeliveryPreparationError("reviewed assets are not bound to the approved suite checksum")

        planned_assets = manifest.get("assets")
        if not isinstance(planned_assets, list) or not all(isinstance(item, Mapping) for item in planned_assets):
            raise AssetDeliveryPreparationError("authoritative Asset Manifest is incomplete")
        planned_by_id = {str(item.get("asset_id") or ""): item for item in planned_assets}
        if len(planned_by_id) != len(planned_assets):
            raise AssetDeliveryPreparationError("authoritative Asset Manifest contains duplicate asset IDs")
        if set(planned_by_id) != {str(item.get("asset_id") or "") for item in assets}:
            raise AssetDeliveryPreparationError("approved suite does not cover the exact Asset Manifest")

        delivery_assets = []
        for item in assets:
            planned = planned_by_id[str(item["asset_id"])]
            if str(planned.get("production_job_id") or "") != str(item.get("production_job_id") or ""):
                raise AssetDeliveryPreparationError("asset version production lineage does not match the manifest")
            delivery_assets.append(
                {
                    "asset_version_id": str(item["asset_version_id"]),
                    "asset_id": str(item["asset_id"]),
                    "production_job_id": str(item["production_job_id"]),
                    "file_checksum": str(item.get("file_checksum") or ""),
                    "drive_uri": str(item.get("drive_uri") or ""),
                    "status": "ready_for_delivery_approval",
                    "source_asset_suite_checksum": suite_checksum,
                }
            )
        if any(not item["file_checksum"] or not item["drive_uri"] for item in delivery_assets):
            raise AssetDeliveryPreparationError("delivery asset files require Drive URIs and checksums")

        manifest_checksum = _checksum(manifest)
        package_payload = {
            "campaign_identity": dict(identity),
            "source_asset_manifest_id": str(manifest.get("manifest_id") or ""),
            "source_asset_manifest_checksum": manifest_checksum,
            "source_asset_suite_checksum": suite_checksum,
            "assets": delivery_assets,
            "delivery_requirements": dict(requirements),
        }
        package_checksum = _checksum(package_payload)
        package_id = f"delivery-package-{identity['campaign_id']}-{package_checksum[:12]}"
        destination = str(
            requirements.get("destination")
            or requirements.get("repository")
            or "client Drive delivery folder"
        )
        return {
            "delivery_package": {
                "delivery_package_id": package_id,
                "version": 1,
                "checksum": package_checksum,
                **package_payload,
                "status": "prepared_for_human_approval",
            },
            "delivery_manifest": {
                "delivery_manifest_id": f"delivery-manifest-{package_checksum[:16]}",
                "delivery_package_id": package_id,
                "delivery_package_checksum": package_checksum,
                "asset_count": len(delivery_assets),
                "assets": delivery_assets,
                "status": "pending_human_approval",
            },
            "review_findings": [
                f"All {len(delivery_assets)} exact Matt-approved asset versions are present.",
                "Every file is bound to its checksum, Drive URI, production job and approved suite.",
                "No client delivery, publication or media spend has been authorised or performed.",
            ],
            "proposed_delivery_action": {
                "action_type": "client_asset_delivery",
                "status": "pending_human_approval",
                "destination": destination,
                "delivery_package_id": package_id,
                "delivery_package_checksum": package_checksum,
                "idempotency_key": f"deliver:{package_id}:{package_checksum}",
                "requires_human_approval": True,
                "execution_authorised": False,
            },
            "external_action_taken": False,
            "delivery_authorised": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }


def _checksum(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
