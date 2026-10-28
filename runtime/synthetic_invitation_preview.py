"""Internal, in-memory preparation only; deliberately has no dispatch dependency."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
    fields = ("WORKSPACE_ID", "RECIPIENT", "GMAIL_SENDER", "SENDER_AUTHORITY_REF",
              "BOOKING_URL", "BOOKING_AUTHORITY_REF")
    values = {key: source.get(PREFIX + key, "").strip() for key in fields}
    blockers = [f"Configure {PREFIX}{key} privately." for key in fields if not values[key]]
    if values["WORKSPACE_ID"] and values["WORKSPACE_ID"] != workspace_id:
        blockers.append("Private configuration belongs to a different workspace.")
    for key in ("RECIPIENT", "GMAIL_SENDER"):
        value = values[key]
        if value and not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value):
            blockers.append(f"Configure one plain email address for {PREFIX}{key}.")
    if values["RECIPIENT"].casefold() in {
        INTERNAL_REVIEW_ADDRESS.casefold(), values["GMAIL_SENDER"].casefold()
    } and values["RECIPIENT"]:
        blockers.append("Synthetic recipient must be separate from sender and internal review inbox.")
    for key, value in values.items():
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
        "subject": "[SYNTHETIC TEST] Narratiive discovery — 10-minute simulated call",
        "body": (
            "Hello,\n\nThis is test correspondence only for a synthetic Narratiive "
            "discovery journey. Please book a 10-minute simulated call using this page:\n"
            f"{values['BOOKING_URL']}\n\n"
            "We will discuss a fictional brief. Fireflies recording and transcription "
            "will only be enabled with all participants' informed consent. "
            "No real client work or purchase is being commissioned.\n\nNarratiive"
        ),
    }
    material = {
        "version": 1, "workspace_id": workspace_id, "email": email,
        "sender_authority_ref": values["SENDER_AUTHORITY_REF"],
        "booking_authority_ref": values["BOOKING_AUTHORITY_REF"],
        "booking_mechanism": "configured_authorised_booking_page",
    }
    checksum = hashlib.sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()
    result["email_preview"] = email
    result["approval_digest"] = {
        **material, "checksum": checksum,
        "founder_action": (
            "Confirm the configured Gmail sender authority and that the booking page "
            "offers a 10-minute call. Review the exact From, To, subject and body; "
            f"authorise one external synthetic invitation bound to checksum {checksum} "
            "through the existing authenticated single-use approval boundary. "
            "This preview does not record approval or enable sending."
        ),
    }
    return result
