from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from runtime.inbound_leads import InboundLead

_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
_INTERNAL_LABEL_RE = re.compile(r"\b(?:company size|lead id|notion id|database id|page id)\s*:\s*", re.IGNORECASE)


def _clean(text: str) -> str:
    value = " ".join(str(text or "").split()).strip()
    value = _UUID_RE.sub("", value)
    value = _INTERNAL_LABEL_RE.sub("", value)
    value = re.sub(r"\s{2,}", " ", value).strip(" -—:;")
    return value


def _signal(lead: InboundLead) -> str:
    summary = _clean(lead.ai_summary)
    if summary:
        # AI summaries sometimes contain several sentences of form metadata. Keep
        # only the first useful sentence for executive scanability.
        first = re.split(r"(?<=[.!?])\s+", summary, maxsplit=1)[0]
        return first[:220].rstrip()
    notes = _clean(lead.notes)
    if notes:
        return notes[:220].rstrip()
    return "New inbound enquiry received."


def _recommendation(leads: tuple[InboundLead, ...]) -> str:
    warm = sum(1 for lead in leads if lead.lead_temperature.casefold() == "warm")
    hot = sum(1 for lead in leads if lead.lead_temperature.casefold() == "hot")
    if hot:
        return f"Priority: review the {hot} hot lead{'s' if hot != 1 else ''} first and decide the next commercial move today."
    if warm:
        return f"Priority: review the {warm} warm lead{'s' if warm != 1 else ''} and decide which warrant a discovery conversation."
    return "Priority: review fit and decide which leads warrant follow-up."


def render_inbound_leads(
    leads: Iterable[InboundLead],
    *,
    scope: str,
    detailed: bool = False,
) -> str:
    items = tuple(leads)
    if not items:
        return f"No inbound leads are recorded for {scope}."

    if detailed:
        lines = [f"Inbound leads — {scope}: {len(items)}"]
        for lead in items[:10]:
            company = f" — {lead.company}" if lead.company else ""
            qualifiers = [value for value in (lead.lead_temperature, lead.pipeline_stage) if value]
            suffix = f" ({', '.join(qualifiers)})" if qualifiers else ""
            lines.append(f"• {lead.contact}{company}{suffix}")
            signal = _signal(lead)
            if signal:
                lines.append(f"  {signal}")
            next_action = _clean(lead.recommended_next_action)
            if next_action:
                lines.append(f"  Next: {next_action}")
        return "\n".join(lines)

    temperatures = Counter(
        lead.lead_temperature.strip().casefold()
        for lead in items
        if lead.lead_temperature.strip()
    )
    temperature_summary = ""
    if temperatures:
        parts = [f"{count} {name}" for name, count in sorted(temperatures.items(), key=lambda item: (-item[1], item[0]))]
        temperature_summary = f" ({', '.join(parts)})"

    lines = [f"{len(items)} inbound lead{'s' if len(items) != 1 else ''} {scope}{temperature_summary}."]
    for lead in items[:7]:
        company = f" — {lead.company}" if lead.company else ""
        lines.append(f"• {lead.contact}{company}: {_signal(lead)}")
    if len(items) > 7:
        lines.append(f"• Plus {len(items) - 7} more.")
    lines.append(_recommendation(items))
    return "\n".join(lines)


def wants_lead_detail(query: str) -> bool:
    lowered = " ".join(query.casefold().split())
    detail_markers = (
        "tell me more",
        "more detail",
        "details",
        "full record",
        "database record",
        "show me the record",
        "raw",
    )
    return any(marker in lowered for marker in detail_markers)
