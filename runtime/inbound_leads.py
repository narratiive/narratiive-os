from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from runtime.agency_state import AgencyArea, AgencyItem

CANONICAL_NOTION_LEADS_DATABASE_ID = "34b0c9cf-a8f2-80aa-9862-f05f4a65c676"
CANONICAL_NOTION_LEADS_DATA_SOURCE_ID = "34b0c9cf-a8f2-80af-98e4-000b95243de6"


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        parts = [_plain_text(item) for item in value]
        return " ".join(part for part in parts if part).strip()
    if not isinstance(value, dict):
        return ""

    for key in ("plain_text", "content", "name", "email", "url"):
        if value.get(key):
            return _plain_text(value[key])
    for key in ("title", "rich_text", "select", "status", "email", "url", "number"):
        if key in value:
            return _plain_text(value[key])
    return ""


def _property(properties: dict[str, Any], name: str) -> str:
    return _plain_text(properties.get(name))


def _default_summary(contact: str, company: str, notes: str) -> str:
    notes = " ".join(notes.split()).strip()
    if not notes:
        return ""
    subject = company or contact or "This lead"
    return f"{subject} submitted an inbound growth enquiry: {notes}"


def _default_inbound_next_action(contact: str, company: str) -> str:
    subject = company or contact or "this lead"
    return (
        f"Research {subject} and the stated growth challenge using available verified sources. "
        "Return the source-backed evidence, assess fit for Narratiive, identify the clearest strategic growth opportunity, "
        "and prepare a first-pass Growth Blueprint grounded only in that evidence. Mark assumptions and evidence gaps explicitly, "
        "and recommend whether Tony should advance, revise, or stop the opportunity. Do not send anything or change external state."
    )


@dataclass(frozen=True, slots=True)
class InboundLead:
    lead_id: str
    contact: str
    company: str = ""
    email: str = ""
    source: str = "Unknown"
    status: str = "New"
    pipeline_stage: str = ""
    lead_temperature: str = ""
    recommended_next_action: str = "Review the lead and decide the next commercial action."
    created_at: str = ""
    notion_url: str = ""
    notes: str = ""
    ai_summary: str = ""

    def __post_init__(self) -> None:
        if not self.lead_id.strip():
            raise ValueError("lead_id is required")
        if not self.contact.strip():
            raise ValueError("contact is required")
        if not self.recommended_next_action.strip():
            raise ValueError("recommended_next_action is required")

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "InboundLead":
        properties = value.get("properties") if isinstance(value.get("properties"), dict) else {}

        def choose(*names: str, default: str = "") -> str:
            for name in names:
                raw = value.get(name)
                text = _plain_text(raw)
                if text:
                    return text
                if properties:
                    text = _property(properties, name)
                    if text:
                        return text
            return default

        notion_url = choose("notion_url", "url")
        lead_id = choose("lead_id", "id") or notion_url
        contact = choose("contact", "Contact", "name")
        company = choose("company", "Company")
        email = choose("email", "Email")
        source = choose("source", "Source", default="Unknown") or "Unknown"
        status = choose("status", "Status", default="New") or "New"
        notes = choose("notes", "Notes")
        pipeline_stage = choose("pipeline_stage", "Pipeline Stage")
        lead_temperature = choose("lead_temperature", "Lead Temperature")
        recommended_next_action = choose("recommended_next_action", "Recommended Next Action")
        ai_summary = choose("ai_summary", "AI Summary")
        created_at = choose("created_at", "createdTime", "created_time")

        if source.casefold() in {"tally", "growth diagnostic", "website"}:
            if not pipeline_stage:
                pipeline_stage = "New Diagnostic"
            if not lead_temperature:
                lead_temperature = "Warm"
            if not recommended_next_action:
                recommended_next_action = _default_inbound_next_action(contact, company)
            if not ai_summary:
                ai_summary = _default_summary(contact, company, notes)

        return cls(
            lead_id=lead_id.strip(), contact=contact.strip(), company=company.strip(), email=email.strip(),
            source=source.strip() or "Unknown", status=status.strip() or "New", pipeline_stage=pipeline_stage.strip(),
            lead_temperature=lead_temperature.strip(),
            recommended_next_action=(recommended_next_action.strip() or "Review the lead and decide the next commercial action."),
            created_at=created_at.strip(), notion_url=notion_url.strip(), notes=notes.strip(), ai_summary=ai_summary.strip(),
        )

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def to_agency_item(self) -> AgencyItem:
        label = self.contact
        if self.company:
            label = f"{self.contact} — {self.company}"
        qualifiers = [self.source]
        if self.lead_temperature:
            qualifiers.append(self.lead_temperature)
        if self.pipeline_stage:
            qualifiers.append(self.pipeline_stage)
        evidence = tuple(filter(None, (
            f"source:{self.source}", f"status:{self.status}",
            f"pipeline_stage:{self.pipeline_stage}" if self.pipeline_stage else "",
            f"lead_temperature:{self.lead_temperature}" if self.lead_temperature else "",
            f"notion:{self.notion_url}" if self.notion_url else "",
        )))
        return AgencyItem(
            item_id=f"lead-{self.lead_id}", area=AgencyArea.COMMERCIAL,
            title=f"New lead: {label} ({' / '.join(qualifiers)})",
            status=self.status.casefold().replace(" ", "_") or "new", next_action=self.recommended_next_action,
            owner="Tony", evidence=evidence, requires_matt=False,
        )


class FileInboundLeadStore:
    """Durable synchronized view of inbound leads for Tony's executive runtime.

    Notion remains the commercial source of truth. This store is a local projection
    fed by the same capture flow so Tony can reason about live leads without
    treating repository workstreams as a proxy for the sales pipeline.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def upsert(self, lead: InboundLead) -> None:
        items = {item.lead_id: item for item in self.read()}
        items[lead.lead_id] = lead
        self._write(tuple(items.values()))

    def replace(self, leads: Iterable[InboundLead]) -> None:
        """Replace the cache with one complete authoritative snapshot."""
        items = {item.lead_id: item for item in leads}
        self._write(tuple(items.values()))

    def read(self) -> tuple[InboundLead, ...]:
        if not self.path.exists():
            return ()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"inbound lead state is unreadable: {exc}") from exc
        if not isinstance(raw, list):
            raise RuntimeError("inbound lead state must be a JSON list")
        items = tuple(InboundLead.from_mapping(item) for item in raw if isinstance(item, dict))
        return tuple(sorted(items, key=lambda item: (item.created_at, item.lead_id), reverse=True))

    def _write(self, leads: Iterable[InboundLead]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = [item.to_dict() for item in sorted(leads, key=lambda item: item.lead_id)]
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)
