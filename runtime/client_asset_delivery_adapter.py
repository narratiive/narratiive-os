from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


class ClientAssetDeliveryError(RuntimeError):
    pass


class ClientAssetDeliveryAdapter:
    """Execute one explicitly approved delivery package and verify its receipt."""

    def __init__(self, provider: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.provider = provider

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = contract.get("workflow_context")
        if not isinstance(context, Mapping) or context.get("workflow_id") != "asset_review_to_delivery_preparation":
            raise ClientAssetDeliveryError("client delivery received an unsupported workflow")
        package = contract.get("delivery_package")
        manifest = contract.get("delivery_manifest")
        action = contract.get("proposed_delivery_action")
        if not all(isinstance(item, Mapping) for item in (package, manifest, action)):
            raise ClientAssetDeliveryError("client delivery requires the exact prepared package and action")
        package_checksum = str(package.get("checksum") or "")
        if (
            not package_checksum
            or manifest.get("delivery_package_checksum") != package_checksum
            or action.get("delivery_package_checksum") != package_checksum
            or action.get("requires_human_approval") is not True
            or action.get("execution_authorised") is not False
        ):
            raise ClientAssetDeliveryError("client delivery package binding is incomplete or stale")
        package_assets = package.get("assets")
        if not isinstance(package_assets, list) or not package_assets:
            raise ClientAssetDeliveryError("client delivery package contains no assets")
        expected_ids = {str(item.get("asset_version_id") or "") for item in package_assets if isinstance(item, Mapping)}
        if len(expected_ids) != len(package_assets) or "" in expected_ids:
            raise ClientAssetDeliveryError("client delivery package contains invalid asset versions")

        result = self.provider(dict(contract))
        if not isinstance(result, Mapping):
            raise ClientAssetDeliveryError("client delivery provider returned a non-object result")
        evidence = result.get("verified_delivery_evidence")
        receipt = result.get("delivery_receipt")
        external_receipt = result.get("external_action_receipt")
        if (
            not isinstance(evidence, Mapping)
            or not isinstance(receipt, Mapping)
            or not isinstance(external_receipt, Mapping)
        ):
            raise ClientAssetDeliveryError("client delivery provider did not return verified evidence and receipt")
        delivered_ids = {str(item) for item in evidence.get("delivered_asset_version_ids") or []}
        if delivered_ids != expected_ids or len(delivered_ids) != len(expected_ids):
            raise ClientAssetDeliveryError("client delivery evidence does not cover the exact approved package")
        if evidence.get("delivery_package_checksum") != package_checksum:
            raise ClientAssetDeliveryError("client delivery evidence does not match the package checksum")
        if result.get("external_action_taken") is not True or result.get("delivery_authorised") is not True:
            raise ClientAssetDeliveryError("client delivery result does not truthfully record execution")
        for field in ("publication_authorised", "media_spend_authorised"):
            if result.get(field) is not False:
                raise ClientAssetDeliveryError(f"client delivery must explicitly deny {field}")
        return dict(result)
