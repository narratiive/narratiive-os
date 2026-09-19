from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any


class CampaignProductionPlanningError(ValueError):
    pass


class CampaignProductionPlanningWorker:
    """Derive a versioned, non-executing Production Pack from an approved Bible."""

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = contract.get("workflow_context")
        if not isinstance(context, Mapping) or context.get("workflow_id") != "creative_bible_to_asset_production":
            raise CampaignProductionPlanningError("production planning received an unsupported workflow")
        identity = contract.get("campaign_identity")
        bible = contract.get("approved_creative_bible")
        approval = contract.get("creative_bible_approval")
        constraints = contract.get("production_constraints")
        if not isinstance(identity, Mapping) or not isinstance(bible, Mapping):
            raise CampaignProductionPlanningError("production planning requires campaign identity and approved Bible")
        if not isinstance(approval, Mapping) or approval.get("decision") != "creative_bible_approval":
            raise CampaignProductionPlanningError("production planning requires the exact Creative Bible approval")
        bible_checksum = _checksum(bible)
        if approval.get("creative_bible_checksum") != bible_checksum:
            raise CampaignProductionPlanningError("Creative Bible approval checksum does not match production input")
        matrix = bible.get("campaign_asset_matrix")
        if not isinstance(matrix, list) or not matrix:
            raise CampaignProductionPlanningError("Creative Bible campaign asset matrix is required")
        if not isinstance(constraints, list):
            raise CampaignProductionPlanningError("production constraints must be explicit")

        bible_id = f"creative-bible-{bible_checksum[:16]}"
        north_star = bible.get("creative_north_star")
        bible_version = str(north_star.get("version") or "1") if isinstance(north_star, Mapping) else "1"
        market_ids = [str(item) for item in identity.get("market_ids") or []]
        specifications = []
        tasks = []
        assets = []
        for index, row in enumerate(matrix, start=1):
            if not isinstance(row, Mapping):
                raise CampaignProductionPlanningError("campaign asset matrix rows must be structured")
            asset_type = str(row.get("asset_type") or "").strip()
            if not asset_type:
                raise CampaignProductionPlanningError("campaign asset matrix rows require asset_type")
            key = _slug(asset_type)
            channel, placement, file_format, width, height, duration, capability = _technical_profile(key)
            specification_id = f"spec-{index:03d}-{key}"
            job_id = f"job-{index:03d}-{key}"
            asset_id = f"asset-{identity['campaign_id']}-{index:03d}-{key}"
            specification = {
                "specification_id": specification_id,
                "channel": channel,
                "placement": placement,
                "market": market_ids[0] if market_ids else "unspecified",
                "language": "en",
                "asset_type": asset_type,
                "file_format": file_format,
                "aspect_ratio": f"{width}:{height}",
                "width_px": width,
                "height_px": height,
                "duration_seconds": duration,
                "constraints": [str(item) for item in constraints],
                "source_bible_id": bible_id,
                "source_bible_version": bible_version,
                "source_bible_checksum": bible_checksum,
                "platform_requirements_version": "narratiive-channel-spec-v1",
                "creative_direction": {
                    field: row.get(field)
                    for field in ("role", "audience", "message", "visual_direction", "format_notes", "production_notes")
                },
            }
            task = {
                "job_id": job_id,
                "specification_id": specification_id,
                "production_method": "ai_assisted_production",
                "required_capability": capability,
                "source_bible_checksum": bible_checksum,
                "expected_variants": 1,
                "human_review_required": True,
                "route_status": "unrouted",
                "execution_authorised": False,
            }
            asset = {
                "asset_id": asset_id,
                "asset_key": f"{identity['campaign_id']}:{key}:{index}",
                "production_job_id": job_id,
                "specification_id": specification_id,
                "planned_version": 1,
                "status": "planned",
                "file_checksum": "",
                "drive_uri": "",
                "human_review_required": True,
                "approval_status": "pending",
                "delivery_authorised": False,
                "publication_authorised": False,
                "media_spend_authorised": False,
            }
            specifications.append(specification)
            tasks.append(task)
            assets.append(asset)

        pack_payload = {
            "campaign_identity": dict(identity),
            "source_bible_id": bible_id,
            "source_bible_version": bible_version,
            "source_bible_checksum": bible_checksum,
            "channel_asset_specifications": specifications,
            "production_tasks": tasks,
        }
        pack_checksum = _checksum(pack_payload)
        manifest_payload = {
            "manifest_id": f"manifest-{identity['campaign_id']}-{pack_checksum[:12]}",
            "version": 1,
            "source_production_pack_checksum": pack_checksum,
            "source_bible_checksum": bible_checksum,
            "assets": assets,
            "status": "planned",
            "delivery_authorised": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }
        return {
            "production_pack": {
                "production_pack_id": f"production-pack-{identity['campaign_id']}-{pack_checksum[:12]}",
                "version": 1,
                "checksum": pack_checksum,
                **pack_payload,
            },
            "channel_asset_specifications": specifications,
            "production_tasks": tasks,
            "asset_manifest": manifest_payload,
            "production_constraints": [str(item) for item in constraints],
            "production_gaps": [
                "Every task remains unrouted until an eligible creative-tool adapter is configured and selected.",
                "Each exact provider payload requires separate human approval before production execution.",
            ],
            "external_action_taken": False,
            "production_executed": False,
            "delivery_authorised": False,
            "publication_authorised": False,
            "media_spend_authorised": False,
        }


def _checksum(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "asset"


def _technical_profile(asset_type: str) -> tuple[str, str, str, int, int, float | None, str]:
    if any(marker in asset_type for marker in ("film", "advert", "cutdown", "tiktok", "youtube")):
        duration = 6.0 if "six" in asset_type else 15.0 if "fifteen" in asset_type else 30.0
        return "social_video", "feed", "mp4", 1080, 1920, duration, "short_form_video_production"
    if "podcast" in asset_type:
        return "audio", "podcast", "wav", 1, 1, 30.0, "audio_production"
    if "outdoor" in asset_type:
        return "out_of_home", "display", "pdf", 1920, 1080, None, "layout_design"
    if "email" in asset_type:
        return "email", "body", "png", 1200, 1500, None, "image_generation"
    return "digital", "feed", "png", 1080, 1080, None, "image_generation"
