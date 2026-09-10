from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from runtime.inbound_leads import FileInboundLeadStore, InboundLead

VALID_DISPOSITIONS = {"active", "watching", "needs_human_attention", "suppressed", "test", "archived"}


class LeadAttentionService:
    """Durable, reversible attention state; never deletes or performs external effects."""
    def __init__(self, store: FileInboundLeadStore, events_path: Path, *, actor: str = "openclaw", clock: Callable[[], datetime] | None = None):
        self.store, self.events_path, self.actor, self.clock = store, events_path, actor, clock or (lambda: datetime.now(timezone.utc))

    def list(self, scope: str = "visible") -> tuple[InboundLead, ...]:
        leads = self.store.read()
        if scope == "all": return leads
        if scope in {"suppressed", "test", "archived"}: return tuple(x for x in leads if x.disposition == scope)
        return tuple(x for x in leads if x.disposition not in {"suppressed", "test", "archived"} and x.status.casefold() != "complete")

    def mutate(self, reference: str, disposition: str, reason: str = "", actor: str | None = None) -> dict:
        disposition = disposition.casefold().replace("-", "_")
        if disposition == "restore": disposition = "active"
        if disposition not in VALID_DISPOSITIONS: return {"ok": False, "error": "invalid_disposition"}
        matches = [x for x in self.store.read() if self._matches(x, reference)]
        if len(matches) != 1:
            return {"ok": False, "error": "lead_not_found" if not matches else "ambiguous_lead_reference", "matches": [x.lead_id for x in matches]}
        lead = matches[0]; now = self.clock().isoformat(); who = actor or self.actor
        updated = replace(lead, disposition=disposition, disposition_reason=reason.strip(), disposition_actor=who, disposition_at=now,
                          disposition_evidence=lead.disposition_evidence + (f"attention:{lead.disposition}->{disposition}",))
        self._event(lead, updated, reason, who); self.store.upsert(updated)
        return {"ok": True, "lead_id": lead.lead_id, "disposition": disposition, "external_action_taken": False, "audit": updated.disposition_evidence}

    def batch_safe(self, disposition: str = "archived", reason: str = "SAFE/test record", actor: str | None = None) -> dict:
        changed = []
        for lead in self.store.read():
            if self._safe(lead) and lead.disposition != disposition:
                result = self.mutate(lead.lead_id, disposition, reason, actor)
                if result.get("ok"): changed.append(lead.lead_id)
        return {"ok": True, "changed": changed, "count": len(changed), "external_action_taken": False}

    @staticmethod
    def _matches(lead: InboundLead, ref: str) -> bool:
        needle = ref.strip().casefold()
        return needle and needle in {lead.lead_id.casefold(), lead.contact.casefold(), lead.company.casefold(), lead.email.casefold(), lead.notion_url.casefold()}

    @staticmethod
    def _safe(lead: InboundLead) -> bool:
        text = " ".join((lead.lead_id, lead.contact, lead.company, lead.email, lead.source, lead.status)).casefold()
        return lead.disposition == "test" or ".invalid" in text or any(token in text for token in ("safe", "synthetic", "test"))

    def _event(self, old: InboundLead, new: InboundLead, reason: str, actor: str) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"event_id": str(uuid4()), "type": "lead_disposition_changed", "lead_id": old.lead_id, "from": old.disposition,
                 "to": new.disposition, "reason": reason, "actor": actor, "occurred_at": new.disposition_at, "external_action_taken": False}
        with self.events_path.open("a", encoding="utf-8") as fh: fh.write(json.dumps(event, sort_keys=True) + "\n")
