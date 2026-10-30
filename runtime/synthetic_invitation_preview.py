"""Internal, in-memory preparation only; deliberately has no dispatch dependency."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from copy import deepcopy
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from runtime.repositories import WorkflowRunRepository
from runtime.tony_internal_review_delivery import INTERNAL_REVIEW_ADDRESS


PREFIX = "NARRATIIVE_SYNTHETIC_INVITATION_"
INVITATION_SECTIONS = (
    "THE BIGGER AMBITION",
    "THE PEOPLE WHO MATTER",
    "WHAT MAKES YOU UNMISSABLE",
)
FOUNDER_APPROVED_SYNTHETIC_ENTITY = "inbound-d1b96a67"
FOUNDER_APPROVED_SYNTHETIC_COMPANY = "Loom Loft"


class DiscoveryEvidenceResolver:
    """Read verified source lineage from persisted Discovery workflow evidence."""

    def __init__(self, runs: WorkflowRunRepository, artifact_root: str | Path) -> None:
        self.runs = runs
        self.artifact_root = Path(artifact_root).resolve()

    def resolve(
        self, *, workspace_id: str, entity_id: str, discovery_preparation_ref: str
    ) -> Mapping[str, Any]:
        matches = []
        for run_id in self.runs.list_run_ids():
            state = self.runs.load(run_id)
            if (
                state.workspace_id == workspace_id
                and state.entity_id == entity_id
                and state.workflow_id == "blueprint_lite_to_discovery_preparation"
            ):
                for stage in state.stages:
                    if stage.stage_id != "prepare_discovery":
                        continue
                    matches.extend(
                        artifact for artifact in stage.output_artifacts
                        if (
                            artifact.artifact_id == discovery_preparation_ref
                            and artifact.artifact_type == "workflow_step_output"
                            and artifact.metadata.get("workspace_id") == workspace_id
                            and artifact.metadata.get("entity_id") == entity_id
                            and artifact.metadata.get("workflow_id") == state.workflow_id
                            and artifact.metadata.get("run_id") == state.run_id
                            and artifact.metadata.get("stage_id") == "prepare_discovery"
                        )
                    )
        if len(matches) != 1:
            raise ValueError("discovery preparation artefact is not uniquely resolved")
        artifact = matches[0]
        location = Path(artifact.location).resolve()
        if self.artifact_root not in location.parents or location.suffix != ".json":
            raise ValueError("discovery preparation artefact escapes the immutable store")
        content = location.read_bytes()
        if not artifact.checksum or hashlib.sha256(content.rstrip(b"\n")).hexdigest() != artifact.checksum:
            raise ValueError("discovery preparation artefact integrity failed")
        output = json.loads(content)
        if not isinstance(output, Mapping):
            raise ValueError("discovery preparation artefact is invalid")
        source_refs = sorted({
            str(ref)
            for item in output.get("evidence_lineage", ())
            if isinstance(item, Mapping)
            for ref in item.get("source_refs", ())
            if isinstance(ref, str)
        })
        if not source_refs:
            raise ValueError("discovery preparation artefact has no source lineage")
        checksum_material = {
            "workspace_id": workspace_id,
            "entity_id": entity_id,
            "discovery_preparation_ref": discovery_preparation_ref,
            "artifact_checksum": artifact.checksum,
            "source_refs": source_refs,
        }
        return {
            **checksum_material,
            "source_set_checksum": _value_checksum(checksum_material),
        }


def build_invitation_preview(
    *,
    workspace_id: str,
    config: Mapping[str, str] | None = None,
    discovery_evidence_resolver: DiscoveryEvidenceResolver | None = None,
) -> dict[str, Any]:
    """Resolve private configuration at call time, never probe a provider.

    The returned private review copy is not an approval token or executable
    dispatch. Sender and booking authority references are configuration
    assertions; invitation evidence is resolved from the authoritative workflow
    boundary, never asserted in configuration.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", workspace_id):
        raise ValueError("workspace_id must be a safe identifier")
    source = os.environ if config is None else config
    fields = (
        "WORKSPACE_ID", "RECIPIENT", "GMAIL_SENDER", "SENDER_AUTHORITY_REF",
        "BOOKING_URL", "BOOKING_AUTHORITY_REF", "COMPANY_NAME", "ENTITY_ID",
        "DISCOVERY_PREPARATION_REF", "MEETING_DURATION_MINUTES", "INSIGHTS_JSON",
        "FOUNDER_SIGNATURE",
    )
    raw_values = {key: source.get(PREFIX + key, "") for key in fields}
    values = {key: value.strip() for key, value in raw_values.items()}
    blockers = [f"Configure {PREFIX}{key} privately." for key in fields if not values[key]]
    if values["WORKSPACE_ID"] and values["WORKSPACE_ID"] != workspace_id:
        blockers.append("Private configuration belongs to a different workspace.")
    if values["ENTITY_ID"] and not re.fullmatch(r"[A-Za-z0-9_-]+", values["ENTITY_ID"]):
        blockers.append(f"Configure a safe identifier for {PREFIX}ENTITY_ID.")
    if values["MEETING_DURATION_MINUTES"] and values["MEETING_DURATION_MINUTES"] != "30":
        blockers.append(f"Configure {PREFIX}MEETING_DURATION_MINUTES as 30.")
    try:
        insights = json.loads(values["INSIGHTS_JSON"]) if values["INSIGHTS_JSON"] else []
    except json.JSONDecodeError:
        insights = []
        blockers.append(f"Configure valid JSON for {PREFIX}INSIGHTS_JSON.")
    discovery_evidence_refs, discovery_evidence_checksum = _resolve_discovery_evidence(
        resolver=discovery_evidence_resolver,
        workspace_id=workspace_id,
        entity_id=values["ENTITY_ID"],
        discovery_preparation_ref=values["DISCOVERY_PREPARATION_REF"],
        blockers=blockers,
    )
    if not isinstance(insights, list) or not 1 <= len(insights) <= len(INVITATION_SECTIONS):
        blockers.append(
            "Provide one to three validated insight/question pairs for the Discovery invitation."
        )
        insights = []
    for insight in insights:
        if not isinstance(insight, dict) or not all(str(insight.get(key, "")).strip() for key in ("observation", "question", "source_ref")):
            blockers.append("Each insight must retain observation, question and source reference.")
            insights = []
            break
        if str(insight.get("source_ref") or "").strip() not in discovery_evidence_refs:
            blockers.append("Each invitation insight must reference the authoritative Discovery evidence set.")
            insights = []
            break
    for key in ("RECIPIENT", "GMAIL_SENDER"):
        value = values[key]
        if value and not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value):
            blockers.append(f"Configure one plain email address for {PREFIX}{key}.")
    if values["RECIPIENT"].casefold() in {
        INTERNAL_REVIEW_ADDRESS.casefold(), values["GMAIL_SENDER"].casefold()
    } and values["RECIPIENT"]:
        blockers.append("Synthetic recipient must be separate from sender and internal review inbox.")
    for key, value in raw_values.items():
        if any(
            (ord(char) < 32 or ord(char) == 127)
            and not (key == "FOUNDER_SIGNATURE" and char == "\n")
            for char in value
        ):
            blockers.append(f"Remove control characters from {PREFIX}{key}.")
    try:
        url = urlsplit(values["BOOKING_URL"])
        valid_url = (url.scheme == "https" and url.hostname and not url.username
                     and not url.password and not url.query and not url.fragment
                     and not any(char.isspace() for char in values["BOOKING_URL"]))
    except ValueError:
        valid_url = False
    if values["BOOKING_URL"] and not valid_url:
        blockers.append("Configure an HTTPS booking page without credentials, query or fragment.")
    result: dict[str, Any] = {
        "kind": "synthetic_invitation_preview", "visibility": "internal_only",
        "workspace_id": workspace_id, "synthetic": True,
        "status": "blocked" if blockers else "awaiting_approval",
        "approval_required": True, "approval_granted": False,
        "external_action_taken": False, "execution_truth": "not_dispatched",
        "provider_verification": "not_performed", "blockers": blockers,
        "email_preview": None, "approval_digest": None,
    }
    if blockers:
        return result
    email = {
        "from": values["GMAIL_SENDER"], "to": values["RECIPIENT"],
        "cc": [], "bcc": [], "attachments": [],
        "subject": (
            "Loom Loft — what could we build together?"
            if _uses_founder_approved_synthetic_copy(values)
            else f"[SYNTHETIC TEST] {values['COMPANY_NAME']} — a conversation worth having"
        ),
        "body": _render_text(values, insights),
    }
    email["html"] = _render_html(values, insights)
    material = {
        "version": 2, "workspace_id": workspace_id, "email": email,
        "sender_authority_ref": values["SENDER_AUTHORITY_REF"],
        "booking_authority_ref": values["BOOKING_AUTHORITY_REF"],
        "company_name": values["COMPANY_NAME"],
        "entity_id": values["ENTITY_ID"],
        "discovery_preparation_ref": values["DISCOVERY_PREPARATION_REF"],
        "authoritative_discovery_evidence_refs": sorted(discovery_evidence_refs),
        "authoritative_discovery_evidence_checksum": discovery_evidence_checksum,
        "meeting_duration_minutes": 30,
        "meeting_evidence_source": "google_meet_transcript_and_gemini_notes",
        "booking_mechanism": "configured_authorised_booking_page",
        "validated_insights": [
            {key: str(item[key]) for key in ("observation", "question", "source_ref")}
            for item in insights
        ],
    }
    checksum = hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()
    # Editing the display copy must not silently alter the checksummed snapshot.
    result["email_preview"] = deepcopy(email)
    result["approval_digest"] = {
        **material, "checksum": checksum,
        "founder_action": (
            "Confirm the configured Gmail sender authority and that the booking page "
            "offers a 30-minute call. Review the exact From, To, subject and body; "
            f"authorise one external synthetic invitation bound to checksum {checksum} "
            "through the existing authenticated single-use approval boundary. "
            "This preview does not record approval or enable sending."
        ),
    }
    return result


def _render_html(values: Mapping[str, str], insights: list[Mapping[str, Any]]) -> str:
    """Render email-safe, self-contained HTML; source references stay in audit only."""
    if _uses_founder_approved_synthetic_copy(values):
        return _render_founder_approved_synthetic_html(values)
    company = html.escape(values["COMPANY_NAME"])
    booking = html.escape(values["BOOKING_URL"], quote=True)
    signature = html.escape(values["FOUNDER_SIGNATURE"])
    sections = "".join(
        "<tr><td style=\"padding:14px 0;border-bottom:1px solid #dbe4ef\">"
        f"<strong style=\"color:#d96b3b;font-size:12px;letter-spacing:.4px\">{title}</strong>"
        f"<p style=\"color:#10243e;line-height:1.5;margin:7px 0 5px\">{html.escape(str(item['observation']))}</p>"
        f"<p style=\"color:#38506b;line-height:1.5;margin:0\">{html.escape(str(item['question']))}</p>"
        "</td></tr>"
        for title, item in zip(INVITATION_SECTIONS, insights)
    )
    return (
        "<!doctype html><html><body style=\"margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#10243e\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\"><tr><td align=\"center\" style=\"padding:20px\">"
        "<table role=\"presentation\" width=\"600\" cellspacing=\"0\" cellpadding=\"0\" style=\"max-width:600px;width:100%;background:#fff\">"
        "<tr><td style=\"padding:26px 28px 12px;font-size:22px;font-weight:bold;letter-spacing:.5px\">NARRATIIVE</td></tr>"
        f"<tr><td style=\"padding:8px 28px\"><span style=\"font-size:12px;color:#596b80\">SYNTHETIC TEST</span><h1 style=\"font-size:25px;line-height:1.2;margin:8px 0\">{company}: a conversation worth having</h1>"
        f"<p style=\"line-height:1.5;margin:0\">Thanks for reaching out. We've had an interesting look around {company}, and there's something we'd love to explore with you.</p></td></tr>"
        "<tr><td style=\"padding:18px 28px\"><table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f0f5fa\"><tr><td style=\"padding:16px\"><table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\">"
        + sections + "</table></td></tr></table></td></tr>"
        f"<tr><td style=\"padding:8px 28px 26px\"><p style=\"line-height:1.5\">If it feels useful, let's compare notes in a 30-minute Google Meet.</p>"
        f"<a href=\"{booking}\" style=\"display:inline-block;background:#d96b3b;color:#ffffff;padding:13px 18px;text-decoration:none;font-weight:bold\">Book a 30-minute conversation</a>"
        f"<p style=\"font-size:12px;line-height:1.5;color:#596b80;margin:18px 0 0\">This is a clearly labelled synthetic test. No commercial commitment is being requested.</p><p style=\"line-height:1.5;margin:22px 0 0\">{signature}</p></td></tr></table></td></tr></table></body></html>"
    )


def _render_text(values: Mapping[str, str], insights: list[Mapping[str, Any]]) -> str:
    """Plain-text equivalent of the permanent evidence-bound invitation voice."""
    if _uses_founder_approved_synthetic_copy(values):
        return _founder_approved_synthetic_text(values["BOOKING_URL"])
    sections = "\n\n".join(
        f"{title}\n{item['observation']}\n{item['question']}"
        for title, item in zip(INVITATION_SECTIONS, insights)
    )
    return (
        "Hello,\n\n"
        f"Thanks for reaching out. We've had an interesting look around {values['COMPANY_NAME']}, "
        "and there's something we'd love to explore with you.\n\n"
        f"{sections}\n\n"
        "If it feels useful, let's compare notes in a 30-minute Google Meet.\n"
        f"{values['BOOKING_URL']}\n\n"
        "This is a clearly labelled synthetic test. No commercial commitment is being requested. "
        "If the test is booked, Google Meet transcript and Gemini notes are the intended evidence "
        "source; Fireflies is only an optional fallback.\n\n"
        f"{values['FOUNDER_SIGNATURE']}"
    )


def _resolve_discovery_evidence(
    *,
    resolver: DiscoveryEvidenceResolver | None,
    workspace_id: str,
    entity_id: str,
    discovery_preparation_ref: str,
    blockers: list[str],
) -> tuple[list[str], str]:
    """Accept evidence only from an immutable, correctly scoped preparation record."""
    if not entity_id or not discovery_preparation_ref:
        return [], ""
    if resolver is None:
        blockers.append("Resolve Discovery evidence through the authoritative workflow record.")
        return [], ""
    try:
        if not isinstance(resolver, DiscoveryEvidenceResolver):
            raise ValueError("an authoritative Discovery evidence resolver is required")
        record = resolver.resolve(
            workspace_id=workspace_id,
            entity_id=entity_id,
            discovery_preparation_ref=discovery_preparation_ref,
        )
    except Exception:
        blockers.append("The authoritative Discovery evidence record could not be resolved.")
        return [], ""
    if not isinstance(record, Mapping):
        blockers.append("The authoritative Discovery evidence record is invalid.")
        return [], ""
    if (
        record.get("workspace_id") != workspace_id
        or record.get("entity_id") != entity_id
        or record.get("discovery_preparation_ref") != discovery_preparation_ref
    ):
        blockers.append("Discovery evidence does not match the requested workspace, entity and preparation.")
        return [], ""
    source_refs = record.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs or not all(
        isinstance(ref, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", ref)
        for ref in source_refs
    ):
        blockers.append("The authoritative Discovery evidence source set is invalid.")
        return [], ""
    if len(source_refs) != len(set(source_refs)):
        blockers.append("The authoritative Discovery evidence source set is ambiguous.")
        return [], ""
    checksum_material = {
        "workspace_id": workspace_id,
        "entity_id": entity_id,
        "discovery_preparation_ref": discovery_preparation_ref,
        "artifact_checksum": record.get("artifact_checksum"),
        "source_refs": sorted(source_refs),
    }
    checksum = _value_checksum(checksum_material)
    if record.get("source_set_checksum") != checksum:
        blockers.append("The authoritative Discovery evidence source set failed integrity validation.")
        return [], ""
    return list(source_refs), checksum


def _value_checksum(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


def _uses_founder_approved_synthetic_copy(values: Mapping[str, str]) -> bool:
    """Keep the founder-approved fictional Loom Loft copy out of real-prospect paths."""
    return (
        values["ENTITY_ID"] == FOUNDER_APPROVED_SYNTHETIC_ENTITY
        and values["COMPANY_NAME"] == FOUNDER_APPROVED_SYNTHETIC_COMPANY
    )


def _founder_approved_synthetic_text(booking_url: str) -> str:
    """Exact founder-approved fictional copy for the authorised Loom Loft rehearsal."""
    return (
        "Hi [First Name],\n\n"
        "Thanks for getting in touch. We've been having a look around Loom Loft, and we're intrigued.\n\n"
        "Furniture is an interesting business. People might come looking for a sofa, but what they're really imagining is a different version of home. And that creates some exciting possibilities for a brand with ambition.\n\n"
        "We've got a few thoughts. But we'd much rather explore them with you than jump to conclusions.\n\n"
        "THREE THINGS WE'D LOVE TO EXPLORE\n\n"
        "01 / HOW BIG COULD THIS GET?\n"
        "Forget next quarter's targets for a moment. Where do you really want to take Loom Loft? And what's stopping you getting there faster?\n\n"
        "02 / WHO COULD FALL IN LOVE WITH IT?\n"
        "There's a difference between reaching more people and becoming the brand that the right people actively seek out. Who are those people for Loom Loft?\n\n"
        "03 / WHAT COULD MAKE YOU FAMOUS?\n"
        "Not just another furniture retailer. A brand people recognise, remember and recommend. What could Loom Loft become known for?\n\n"
        "LET'S FIND OUT TOGETHER.\n\n"
        "I'd love to spend 30 minutes exploring what's possible. We'll bring an outside perspective, you bring the inside story, and we'll see where the interesting opportunities emerge.\n\n"
        "No pitch deck. No obligation. Just a good conversation.\n\n"
        f"→ Book a 30-minute conversation\n{booking_url}\n\n"
        "Looking forward to meeting you.\n\n"
        "Matt Franks\nFounder, Narratiive"
    )


def _render_founder_approved_synthetic_html(values: Mapping[str, str]) -> str:
    """Render the supplied fictional copy verbatim, inside the existing email shell."""
    booking = html.escape(values["BOOKING_URL"], quote=True)
    return (
        "<!doctype html><html><head><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><style>"
        "@media screen and (max-width:620px){.shell{width:100%!important}.pad{padding-left:22px!important;padding-right:22px!important}.intro-copy,.intro-image{display:block!important;width:100%!important}.intro-image{padding-top:18px!important}.headline{font-size:40px!important;line-height:1.04!important}.circle{width:42px!important;height:42px!important;font-size:16px!important}.question-copy{padding-left:14px!important}}"
        "</style></head><body style=\"margin:0;background:#f3efe8;font-family:Arial,Helvetica,sans-serif;color:#10243e\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f3efe8\"><tr><td align=\"center\" style=\"padding:16px\">"
        "<table class=\"shell\" role=\"presentation\" width=\"860\" cellspacing=\"0\" cellpadding=\"0\" style=\"max-width:860px;width:100%;background:#fffdf9;border-radius:12px\">"
        "<tr><td class=\"pad\" style=\"padding:30px 44px 16px\"><table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\"><tr><td style=\"font-size:24px;font-weight:bold;letter-spacing:5px\">NARRATIIVE</td><td align=\"right\" style=\"font-size:10px;letter-spacing:2px;color:#78818c\">STRATEGY&nbsp;&nbsp; / &nbsp;&nbsp;CREATIVE&nbsp;&nbsp; / &nbsp;&nbsp;GROWTH</td></tr></table></td></tr>"
        "<tr><td class=\"pad\" style=\"padding:22px 44px 26px\"><span style=\"font-size:10px;color:#78818c;letter-spacing:1.5px\">SYNTHETIC TEST</span><table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\"><tr>"
        "<td class=\"intro-copy\" valign=\"top\" style=\"width:61%;padding-right:26px\"><h1 class=\"headline\" style=\"font-family:Georgia,'Times New Roman',serif;font-size:50px;line-height:1.03;letter-spacing:-1.5px;margin:14px 0 20px;color:#10243e\">Loom Loft —<br>what could we<br>build together?</h1>"
        "<p style=\"font-size:16px;line-height:1.52;margin:0 0 14px\">Hi [First Name],</p>"
        "<p style=\"font-size:16px;line-height:1.52;margin:0 0 14px\">Thanks for getting in touch. We've been having a look around Loom Loft, and we're intrigued.</p>"
        "<p style=\"font-size:16px;line-height:1.52;margin:0 0 14px\">Furniture is an interesting business. People might come looking for a sofa, but what they're really imagining is a different version of home. And that creates some exciting possibilities for a brand with ambition.</p>"
        "<p style=\"font-size:16px;line-height:1.52;margin:0\">We've got a few thoughts. But we'd much rather explore them with you than jump to conclusions.</p></td>"
        "<td class=\"intro-image\" valign=\"top\" style=\"width:39%\"><div role=\"img\" aria-label=\"Furniture image placeholder\" style=\"height:302px;border-radius:9px;background:#d8c4ad;box-shadow:inset 0 0 0 1px #c0a98d;color:#fffdf9;text-align:center;font-family:Georgia,'Times New Roman',serif;font-size:19px;line-height:302px\">LOOM LOFT</div></td>"
        "</tr></table></td></tr>"
        "<tr><td class=\"pad\" style=\"padding:0 28px 26px\"><table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#faf0ea;border-radius:9px\"><tr><td style=\"padding:23px 18px\"><table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\"><tr><td style=\"color:#e4602e;font-size:13px;font-weight:bold;letter-spacing:1.4px\">THREE THINGS WE'D LOVE TO EXPLORE</td><td style=\"border-bottom:1px solid #a8a8a5\">&nbsp;</td></tr></table>"
        + _render_founder_question("01", "HOW BIG COULD THIS GET?", "Forget next quarter's targets for a moment. Where do you really want to take Loom Loft? And what's stopping you getting there faster?", True)
        + _render_founder_question("02", "WHO COULD FALL IN LOVE WITH IT?", "There's a difference between reaching more people and becoming the brand that the right people actively seek out. Who are those people for Loom Loft?", True)
        + _render_founder_question("03", "WHAT COULD MAKE YOU FAMOUS?", "Not just another furniture retailer. A brand people recognise, remember and recommend. What could Loom Loft become known for?", False)
        + "</td></tr></table></td></tr>"
        "<tr><td class=\"pad\" style=\"padding:0 44px 36px\"><table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\"><tr><td style=\"color:#e4602e;font-size:13px;font-weight:bold;letter-spacing:1.4px;white-space:nowrap\">LET'S FIND OUT TOGETHER.</td><td style=\"border-bottom:1px solid #a8a8a5\">&nbsp;</td></tr></table>"
        "<p style=\"font-size:17px;line-height:1.5;margin:20px 0 10px\">I'd love to spend 30 minutes exploring what's possible. We'll bring an outside perspective, you bring the inside story, and we'll see where the interesting opportunities emerge.</p>"
        "<p style=\"font-size:17px;line-height:1.5;margin:0 0 20px\">No pitch deck. No obligation. Just a good conversation.</p>"
        f"<a href=\"{booking}\" style=\"display:inline-block;background:#e4602e;border-radius:7px;color:#fffdf9;font-size:17px;font-weight:bold;padding:16px 25px;text-decoration:none\">Book a 30-minute conversation&nbsp; →</a>"
        "<p style=\"font-size:16px;line-height:1.5;margin:26px 0 10px\">Looking forward to meeting you.</p><p style=\"font-family:cursive;font-size:34px;font-style:italic;line-height:1;margin:0 0 8px\">Matt</p><p style=\"font-size:15px;line-height:1.45;margin:0\">Matt Franks<br>Founder, Narratiive</p></td></tr>"
        "</table></td></tr></table></body></html>"
    )


def _render_founder_question(
    number: str, heading: str, body: str, divider: bool
) -> str:
    """Email-safe numbered row used only by the founder-approved synthetic fixture."""
    border = "border-bottom:1px solid #c8c2bc;" if divider else ""
    return (
        f"<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"{border}\"><tr>"
        f"<td valign=\"top\" style=\"padding:20px 14px 20px 0;width:60px\"><div class=\"circle\" style=\"background:#e4602e;border-radius:50%;color:#fffdf9;font-size:17px;font-weight:bold;height:50px;line-height:50px;text-align:center;width:50px\">{number}</div></td>"
        f"<td class=\"question-copy\" style=\"padding:20px 0\"><strong style=\"font-size:16px;letter-spacing:.3px\">{heading}</strong><p style=\"font-size:16px;line-height:1.45;margin:5px 0 0\">{body}</p></td>"
        "</tr></table>"
    )
