from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from runtime.agency_state import AgencyArea, AgencyItem

CANONICAL_NOTION_LEADS_DATABASE_ID = "34b0c9cf-a8f2-80aa-9862-f05f4a65c676"
CANONICAL_NOTION_LEADS_DATA_SOURCE_ID = "34b0c9cf-a8f2-80af-98e4-000b95243de6"


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

    def __post_init__(self) -> None:
        if not self.lead_id.strip():
            raise ValueError("lead_id is required")
        if not self.contact.strip():
            raise ValueError("contact is required")
        if not self.recommended_next_action.strip():
            raise ValueError("recommended_next_action is required")

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "InboundLead":
        return cls(
            lead_id=str(value.get("lead_id") or value.get("id") or value.get("notion_url") or "").strip(),
            contact=str(value.get("contact") or value.get("Contact") or value.get("name") or "").strip(),
            company=str(value.get("company") or value.get("Company") or "").strip(),
            email=str(value.get("email") or value.get("Email") or "").strip(),
            source=str(value.get("source") or value.get("Source") or "Unknown").strip() or "Unknown",
            status=str(value.get("status") or value.get("Status") or "New").strip() or "New",
            pipeline_stage=str(value.get("pipeline_stage") or value.get("Pipeline Stage") or "").strip(),
            lead_temperature=str(value.get("lead_temperature") or value.get("Lead Temperature") or "").strip(),
            recommended_next_action=str(
                value.get("recommended_next_action")
                or value.get("Recommended Next Action")
                or "Review the lead and decide the next commercial action."
            ).strip(),
            created_at=str(value.get("created_at") or value.get("createdTime") or "").strip(),
            notion_url=str(value.get("notion_url") or value.get("url") or "").strip(),
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
            f"source:{self.source}",
            f"status:{self.status}",
            f"pipeline_stage:{self.pipeline_stage}" if self.pipeline_stage else "",
            f"lead_temperature:{self.lead_temperature}" if self.lead_temperature else "",
            f"notion:{self.notion_url}" if self.notion_url else "",
        )))
        return AgencyItem(
            item_id=f"lead-{self.lead_id}",
            area=AgencyArea.COMMERCIAL,
            title=f"New lead: {label} ({' / '.join(qualifiers)})",
            status=self.status.casefold().replace(" ", "_") or "new",
            next_action=self.recommended_next_action,
            owner="Tony",
            evidence=evidence,
            requires_matt=False,
        )


class FileInboundLeadStore:
    """Durable synchronized view of inbound leads for Tony's executive runtime.

    Notion remains the commercial source of truth. This store is a local projection
    fed by the same n8n capture flow so Tony can reason about live leads without
    treating repository workstreams as a proxy for the sales pipeline.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def upsert(self, lead: InboundLead) -> None:
        items = {item.lead_id: item for item in self.read()}
        items[lead.lead_id] = lead
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
