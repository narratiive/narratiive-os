"""Internal, in-memory preparation only; deliberately has no dispatch dependency."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from copy import deepcopy
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from runtime.tony_internal_review_delivery import INTERNAL_REVIEW_ADDRESS


PREFIX = "NARRATIIVE_SYNTHETIC_INVITATION_"


def build_invitation_preview(
    *, workspace_id: str, config: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Resolve private configuration at call time, never probe a provider.

    The returned private review copy is not an approval token or executable
    dispatch. Configured authority references are assertions, not live evidence.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", workspace_id):
        raise ValueError("workspace_id must be a safe identifier")
    source = os.environ if config is None else config
    fields = (
        "WORKSPACE_ID", "RECIPIENT", "GMAIL_SENDER", "SENDER_AUTHORITY_REF",
        "BOOKING_URL", "BOOKING_AUTHORITY_REF", "COMPANY_NAME", "ENTITY_ID",
        "DISCOVERY_PREPARATION_REF", "MEETING_DURATION_MINUTES",
        "INSIGHTS_JSON", "FOUNDER_SIGNATURE",
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
    if not isinstance(insights, list) or not 1 <= len(insights) <= 3:
        blockers.append("Provide one to three validated insight/question pairs.")
        insights = []
    for insight in insights:
        if not isinstance(insight, dict) or not all(str(insight.get(key, "")).strip() for key in ("observation", "question", "source_ref")):
            blockers.append("Each insight must retain observation, question and source reference.")
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
        "subject": f"[SYNTHETIC TEST] {values['COMPANY_NAME']} — 30-minute Discovery conversation",
        "body": (
            "Hello,\n\nThis is test correspondence only for Narratiive's synthetic "
            f"Discovery journey for {values['COMPANY_NAME']}. Following the completed "
            "internal Discovery Preparation, please book a 30-minute simulated Discovery "
            "conversation using this page:\n"
            f"{values['BOOKING_URL']}\n\n"
            "The preferred meeting platform is Google Meet. If the test is booked, its "
            "Google Meet transcript and Gemini notes are the intended evidence source; "
            "Fireflies is only an optional fallback. No real client work, commercial "
            "commitment, or purchase is being commissioned.\n\nNarratiive"
        ),
    }
    email["html"] = _render_html(values, insights)
    material = {
        "version": 1, "workspace_id": workspace_id, "email": email,
        "sender_authority_ref": values["SENDER_AUTHORITY_REF"],
        "booking_authority_ref": values["BOOKING_AUTHORITY_REF"],
        "company_name": values["COMPANY_NAME"],
        "entity_id": values["ENTITY_ID"],
        "discovery_preparation_ref": values["DISCOVERY_PREPARATION_REF"],
        "meeting_duration_minutes": 30,
        "meeting_evidence_source": "google_meet_transcript_and_gemini_notes",
        "booking_mechanism": "configured_authorised_booking_page",
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
    company = html.escape(values["COMPANY_NAME"])
    booking = html.escape(values["BOOKING_URL"], quote=True)
    signature = html.escape(values["FOUNDER_SIGNATURE"])
    rows = "".join(
        "<tr><td style=\"padding:14px 0;border-bottom:1px solid #dbe4ef\">"
        f"<strong style=\"color:#10243e\">{index}. {html.escape(str(item['observation']))}</strong>"
        f"<br><span style=\"color:#38506b\">{html.escape(str(item['question']))}</span></td></tr>"
        for index, item in enumerate(insights, 1)
    )
    return (
        "<!doctype html><html><body style=\"margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#10243e\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\"><tr><td align=\"center\" style=\"padding:20px\">"
        "<table role=\"presentation\" width=\"600\" cellspacing=\"0\" cellpadding=\"0\" style=\"max-width:600px;width:100%;background:#fff\">"
        "<tr><td style=\"padding:26px 28px 12px;font-size:22px;font-weight:bold;letter-spacing:.5px\">NARRATIIVE</td></tr>"
        f"<tr><td style=\"padding:8px 28px\"><span style=\"font-size:12px;color:#596b80\">SYNTHETIC TEST</span><h1 style=\"font-size:25px;line-height:1.2;margin:8px 0\">{company}: a few things worth comparing notes on</h1>"
        f"<p style=\"line-height:1.5;margin:0\">We have reviewed the submitted Growth Diagnostic and completed internal GROUNDWORK. These are questions to test together, not conclusions about your business.</p></td></tr>"
        "<tr><td style=\"padding:18px 28px\"><table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f0f5fa\"><tr><td style=\"padding:16px\"><strong>WHAT WE'RE SEEING</strong><table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\">"
        + rows + "</table></td></tr></table></td></tr>"
        f"<tr><td style=\"padding:8px 28px 26px\"><strong>LET'S COMPARE NOTES</strong><p style=\"line-height:1.5\">A 30-minute Google Meet conversation will help us test these observations against your experience.</p>"
        f"<a href=\"{booking}\" style=\"display:inline-block;background:#d96b3b;color:#ffffff;padding:13px 18px;text-decoration:none;font-weight:bold\">Book a 30-minute conversation</a>"
        f"<p style=\"line-height:1.5;margin:22px 0 0\">{signature}</p></td></tr></table></td></tr></table></body></html>"
    )
