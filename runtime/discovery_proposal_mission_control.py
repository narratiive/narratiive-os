"""Truthful Mission Control states for the Discovery -> proposal journey.

Pure, read-only projection over the existing canonical state files Tony
already writes (discovery-outcome-tracking.json, post-discovery-commercial.json,
proposal-handback.json). It never infers a state from absence or from a
provider's silence, and it never marks `verified_sent` true: no governed
client-sending adapter exists in this runtime, so that state stays false with
an explicit reason until one does.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_STATES = (
    "meeting_booked",
    "awaiting_transcript",
    "transcript_verified",
    "proposal_brief_ready",
    "awaiting_external_proposal",
    "proposal_registered",
    "proposal_awaiting_approval",
    "email_draft_awaiting_approval",
    "approved_but_not_sent",
    "verified_sent",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _matches_lead(record: Any, lead_id: str) -> bool:
    return isinstance(record, dict) and str(record.get("lead_id") or "") == lead_id


def _slot_end(active: dict[str, Any]) -> datetime | None:
    slot = active.get("slot") if isinstance(active.get("slot"), dict) else {}
    raw = str(slot.get("end") or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def project_discovery_proposal_journey(
    lead_id: str,
    *,
    discovery_tracking_path: Path,
    post_discovery_path: Path,
    proposal_handback_path: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute the exact, currently-true states for one lead's Discovery/proposal journey.

    `lead_id` must match the exact identifier used in the underlying stores —
    a booking adopted from an existing Calendar event (rather than one Tony
    created) carries a synthesised `calendar:<event_id>` lead id when no CRM
    lead identity exists yet.
    """

    moment = now or datetime.now(timezone.utc)
    discovery = _read_json(discovery_tracking_path)
    post_discovery = _read_json(post_discovery_path)
    handback = _read_json(proposal_handback_path)

    states: dict[str, bool] = dict.fromkeys(REQUIRED_STATES, False)
    evidence: dict[str, Any] = {}

    active = discovery.get("active") if isinstance(discovery.get("active"), dict) else None
    if _matches_lead(active, lead_id):
        end = _slot_end(active)
        if end is not None and moment < end:
            states["meeting_booked"] = True
            evidence["meeting_booked"] = {"calendar_event_id": active.get("calendar_event_id"), "slot": active.get("slot")}
        else:
            states["awaiting_transcript"] = True
            evidence["awaiting_transcript"] = {"calendar_event_id": active.get("calendar_event_id"), "slot": active.get("slot")}

    last_completed = discovery.get("last_completed") if isinstance(discovery.get("last_completed"), dict) else None
    if _matches_lead(last_completed, lead_id):
        states["transcript_verified"] = True
        evidence["transcript_verified"] = {
            "calendar_event_id": last_completed.get("calendar_event_id"),
            "evidence_source": last_completed.get("evidence_source"),
            "reviewed_at": last_completed.get("reviewed_at"),
        }

    last_prepared = post_discovery.get("last_prepared") if isinstance(post_discovery.get("last_prepared"), dict) else None
    brief = last_prepared.get("commission_brief") if _matches_lead(last_prepared, lead_id) and isinstance(last_prepared.get("commission_brief"), dict) else None
    if brief is not None:
        states["proposal_brief_ready"] = True
        evidence["proposal_brief_ready"] = {"brief_id": brief.get("brief_id"), "prepared_at": brief.get("prepared_at")}

    documents = handback.get("documents") if isinstance(handback.get("documents"), dict) else {}
    registered = None
    if brief is not None:
        registered = next((doc for doc in documents.values() if isinstance(doc, dict) and doc.get("brief_id") == brief.get("brief_id")), None)
        if registered is None:
            states["awaiting_external_proposal"] = True
            evidence["awaiting_external_proposal"] = {"brief_id": brief.get("brief_id")}

    if registered is not None:
        states["proposal_registered"] = True
        evidence["proposal_registered"] = {
            "recovery_id": registered.get("recovery_id"),
            "checksum": registered.get("checksum"),
            "producer": registered.get("producer"),
            "version": registered.get("version"),
            "registered_at": registered.get("registered_at"),
        }
        approvals = handback.get("document_approvals") if isinstance(handback.get("document_approvals"), list) else []
        document_approved = any(
            isinstance(item, dict) and item.get("recovery_id") == registered.get("recovery_id") and item.get("checksum") == registered.get("checksum")
            for item in approvals
        )
        if not document_approved:
            states["proposal_awaiting_approval"] = True
            evidence["proposal_awaiting_approval"] = {"recovery_id": registered.get("recovery_id")}
        else:
            drafts = handback.get("drafts") if isinstance(handback.get("drafts"), dict) else {}
            draft = drafts.get(registered.get("recovery_id")) if isinstance(drafts.get(registered.get("recovery_id")), dict) else None
            if draft is not None:
                email_approvals = handback.get("email_approvals") if isinstance(handback.get("email_approvals"), list) else []
                latest = None
                for item in email_approvals:
                    if isinstance(item, dict) and item.get("recovery_id") == registered.get("recovery_id"):
                        latest = item
                approved_and_current = latest is not None and latest.get("action_digest") == draft.get("action_digest")
                if approved_and_current:
                    states["approved_but_not_sent"] = True
                    evidence["approved_but_not_sent"] = {"recovery_id": registered.get("recovery_id"), "recipient": draft.get("recipient"), "approved_at": latest.get("approved_at")}
                else:
                    states["email_draft_awaiting_approval"] = True
                    evidence["email_draft_awaiting_approval"] = {"recovery_id": registered.get("recovery_id"), "recipient": draft.get("recipient"), "subject": draft.get("subject")}

    evidence["verified_sent"] = "No governed client-sending adapter exists in this runtime; this state cannot be true yet."

    current_stage = next((name for name in reversed(REQUIRED_STATES) if states[name]), "no_active_discovery_or_proposal_work")
    return {
        "lead_id": lead_id,
        "as_of": moment.isoformat(),
        "states": states,
        "evidence": evidence,
        "current_stage": current_stage,
    }
