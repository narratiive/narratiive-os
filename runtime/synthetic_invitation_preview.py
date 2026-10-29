"""Internal, in-memory preparation only; deliberately has no dispatch dependency."""

from __future__ import annotations

import hashlib
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
    for key in ("RECIPIENT", "GMAIL_SENDER"):
        value = values[key]
        if value and not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value):
            blockers.append(f"Configure one plain email address for {PREFIX}{key}.")
    if values["RECIPIENT"].casefold() in {
        INTERNAL_REVIEW_ADDRESS.casefold(), values["GMAIL_SENDER"].casefold()
    } and values["RECIPIENT"]:
        blockers.append("Synthetic recipient must be separate from sender and internal review inbox.")
    for key, value in raw_values.items():
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
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
