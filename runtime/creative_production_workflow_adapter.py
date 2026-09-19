from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any


class CreativeProductionWorkflowError(RuntimeError):
    pass


class CreativeProductionWorkflowAdapter:
    """Bind configured provider output to every exact planned Asset Manifest record."""

    def __init__(self, provider: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.provider = provider

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = contract.get("workflow_context")
        if not isinstance(context, Mapping) or context.get("workflow_id") != "creative_bible_to_asset_production":
            raise CreativeProductionWorkflowError("creative production received an unsupported workflow")
        manifest = contract.get("asset_manifest")
        tasks = contract.get("production_tasks")
        if not isinstance(manifest, Mapping) or not isinstance(manifest.get("assets"), list):
            raise CreativeProductionWorkflowError("creative production requires the planned Asset Manifest")
        if not isinstance(tasks, list) or not tasks:
            raise CreativeProductionWorkflowError("creative production requires approved production tasks")
        assets = manifest["assets"]
        planned = {
            (str(item.get("asset_id") or ""), str(item.get("production_job_id") or ""))
            for item in assets
            if isinstance(item, Mapping)
        }
        if len(planned) != len(assets) or any(not asset_id or not job_id for asset_id, job_id in planned):
            raise CreativeProductionWorkflowError("Asset Manifest contains incomplete or duplicate planned records")
        result = self.provider(dict(contract))
        if not isinstance(result, Mapping):
            raise CreativeProductionWorkflowError("creative provider returned a non-object result")
        versions = result.get("asset_versions")
        receipts = result.get("production_receipts")
        if not isinstance(versions, list) or not all(isinstance(item, Mapping) for item in versions):
            raise CreativeProductionWorkflowError("creative provider did not return structured asset versions")
        produced = {
            (str(item.get("asset_id") or ""), str(item.get("production_job_id") or ""))
            for item in versions
        }
        if produced != planned or len(versions) != len(planned):
            raise CreativeProductionWorkflowError("creative provider output does not cover the exact Asset Manifest")
        manifest_checksum = _checksum(manifest)
        if any(item.get("source_manifest_checksum") != manifest_checksum for item in versions):
            raise CreativeProductionWorkflowError("creative provider output does not match the Asset Manifest checksum")
        receipt_version_ids = {
            str(item.get("asset_version_id") or "")
            for item in receipts or []
            if isinstance(item, Mapping)
        }
        version_ids = {str(item.get("asset_version_id") or "") for item in versions}
        if (
            not isinstance(receipts, list)
            or not all(isinstance(item, Mapping) for item in receipts)
            or len(receipts) != len(versions)
            or receipt_version_ids != version_ids
        ):
            raise CreativeProductionWorkflowError("creative provider receipts do not cover every asset version")
        if result.get("external_action_taken") is not True or not isinstance(result.get("external_action_receipt"), Mapping):
            raise CreativeProductionWorkflowError("creative provider execution receipt is missing")
        for field in ("delivery_authorised", "publication_authorised", "media_spend_authorised"):
            if result.get(field) is not False:
                raise CreativeProductionWorkflowError(f"creative provider must explicitly deny {field}")
        return dict(result)


def _checksum(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
