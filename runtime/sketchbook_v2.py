"""Typed SKETCHBOOK v2 population and Tony handoff contract."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PAGE_TYPES = ("creative_proposition", "audience_profile", "visual_world", "campaign_territory", "campaign_executions")
REQUIRED_MANIFEST = ("client_id", "version", "palette", "display_typeface", "body_typeface", "imagery_rules", "product_rules", "rights_and_provenance")
PAGE_FIELDS = {
    "creative_proposition": ("proposition_line_1", "proposition_line_2", "emotional_payoff", "commercial_role", "hero_image"),
    "audience_profile": ("audience_name", "human_truth", "wants", "hesitates", "moves_when", "validation_status", "portrait", "creative_job"),
    "visual_world": ("art_direction_statement", "hero_reference", "setting_rule", "legibility_rule", "avoid_list"),
    "campaign_territory": ("territory_name", "territory_role", "hero_copy", "repeatable_construction", "evidence_label", "hero_execution", "commercial_objective"),
    "campaign_executions": ("applications", "activation_status"),
}


def _present(value: object) -> bool:
    return bool(str(value).strip()) if not isinstance(value, (list, tuple, dict)) else bool(value)


def validate_sketchbook_v2(value: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(value)
    if data.get("contract_version") != "2.0.0":
        raise ValueError("SKETCHBOOK contract_version must be 2.0.0")
    handoff = data.get("fieldwork_handoff") or {}
    if handoff.get("approval_status") != "approved" or not _present(handoff.get("artifact_id")) or not _present(handoff.get("checksum")):
        raise ValueError("SKETCHBOOK requires an exact approved FIELDWORK handoff")
    manifest = data.get("client_manifest") or {}
    missing = [field for field in REQUIRED_MANIFEST if not _present(manifest.get(field))]
    if missing:
        raise ValueError(f"client manifest missing: {', '.join(missing)}")
    palette = manifest.get("palette") or {}
    if any(not _present(palette.get(role)) for role in ("ink", "paper", "accent", "secondary", "muted", "rule", "white")):
        raise ValueError("client palette must define all canonical roles")
    pages = data.get("pages")
    if not isinstance(pages, list) or tuple(page.get("type") for page in pages if isinstance(page, Mapping)) != PAGE_TYPES:
        raise ValueError("SKETCHBOOK must contain the five canonical page types in order")
    for page in pages:
        missing = [field for field in PAGE_FIELDS[page["type"]] if not _present(page.get(field))]
        if missing:
            raise ValueError(f"{page['type']} missing: {', '.join(missing)}")
        if page.get("type") == "campaign_executions" and len(page["applications"]) != 3:
            raise ValueError("campaign_executions requires exactly three applications")
    raw = json.dumps(data, sort_keys=True).casefold()
    if manifest["client_id"].casefold() != "rave" and any(term in raw for term in ("rave coffee", "anti-snob", "coffee credential")):
        raise ValueError("Rave example content leaked into another client")
    if any(page.get("validation_status") == "verified_customer" and not page.get("verified_source_id") for page in pages):
        raise ValueError("verified audience claims require an authorised source")
    return data


@dataclass(frozen=True)
class SketchbookV2Worker:
    renderer: Callable[[Mapping[str, Any], Path], Mapping[str, Any]]
    native_slides_importer: Callable[[Path, Mapping[str, Any]], Mapping[str, Any]]
    output_root: Path

    def __call__(self, contract: Mapping[str, Any]) -> dict[str, Any]:
        spec = validate_sketchbook_v2(contract)
        checksum = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        output = self.output_root / str(spec["client_manifest"]["client_id"]) / checksum[:12]
        rendered = dict(self.renderer(spec, output))
        pptx, pdf = Path(rendered["pptx"]), Path(rendered["pdf"])
        if not pptx.is_file() or not pdf.is_file() or rendered.get("visual_qa_status") != "passed":
            raise ValueError("SKETCHBOOK rendering or visual QA failed")
        imported = dict(self.native_slides_importer(pptx, spec))
        url = str(imported.get("presentation_url") or imported.get("url") or "")
        if not url.startswith("https://docs.google.com/presentation/d/"):
            raise ValueError("native Google Slides import failed")
        return {
            "contract_version": "2.0.0", "specification_checksum": checksum,
            "fieldwork_handoff": dict(spec["fieldwork_handoff"]),
            "editable_google_slides": {"presentation_url": url, "presentation_id": imported.get("presentation_id"), "mime_type": "application/vnd.google-apps.presentation"},
            "editable_pptx": str(pptx), "review_pdf": str(pdf), "visual_qa": dict(rendered.get("visual_qa") or {}),
            "approval_status": "pending_human_review", "client_release_authorised": False,
        }
