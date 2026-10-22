from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from runtime.inbound_leads import FileInboundLeadStore, InboundLead
from runtime.agency_state import AgencyItem
from runtime.executive_visibility import ExecutiveVisibilityPolicy
from runtime.briefing_intelligence import (
    BriefingDecision,
    BriefingDecisionType,
    FileBriefingDecisionRegister,
)

VALID_DISPOSITIONS = {
    "active", "watching", "needs_human_attention", "suppressed", "test", "archived",
    "spam", "internal", "duplicate", "deferred",
}


class LeadAttentionService:
    """Durable, reversible attention state; never deletes or performs external effects."""
    def __init__(self, store: FileInboundLeadStore, events_path: Path, *, actor: str = "openclaw", clock: Callable[[], datetime] | None = None, decision_register: FileBriefingDecisionRegister | None = None, entity_loader: Callable[[], tuple[AgencyItem, ...]] | None = None):
        self.store, self.events_path, self.actor, self.clock = store, events_path, actor, clock or (lambda: datetime.now(timezone.utc))
        self.decision_register = decision_register
        self.entity_loader = entity_loader

    def list(self, scope: str = "visible") -> tuple[InboundLead, ...]:
        leads = self.store.read()
        if scope == "all": return leads
        if scope in {"suppressed", "test", "archived", "spam", "internal", "duplicate", "deferred"}: return tuple(x for x in leads if x.disposition == scope)
        return ExecutiveVisibilityPolicy().visible_leads(leads)

    def mutate(self, reference: str, disposition: str, reason: str = "", actor: str | None = None, decision_type: str = "", classification: str = "") -> dict:
        disposition = disposition.casefold().replace("-", "_")
        if disposition == "restore": disposition = "active"
        if disposition not in VALID_DISPOSITIONS: return {"ok": False, "error": "invalid_disposition"}
        matches = [x for x in self.store.read() if self._matches(x, reference)]
        if len(matches) != 1:
            if matches:
                return {"ok": False, "error": "ambiguous_lead_reference", "matches": [x.lead_id for x in matches]}
            entity_result = self._mutate_briefing_entity(
                reference, disposition, reason, actor or self.actor, decision_type, classification
            )
            if entity_result is not None:
                return entity_result
            return {"ok": False, "error": "lead_or_briefing_entity_not_found", "matches": []}
        lead = matches[0]; now = self.clock().isoformat(); who = actor or self.actor
        updated = replace(lead, disposition=disposition, disposition_reason=reason.strip(), disposition_actor=who, disposition_at=now,
                          disposition_evidence=lead.disposition_evidence + (f"attention:{lead.disposition}->{disposition}",))
        self._event(lead, updated, reason, who); self.store.upsert(updated)
        if self.decision_register is not None:
            decision_name = decision_type or {
                "active": "restore", "suppressed": "suppress", "test": "test",
                "archived": "archive", "spam": "spam", "internal": "internal",
                "duplicate": "duplicate", "deferred": "defer",
            }.get(disposition, "reclassify")
            try:
                register_type = BriefingDecisionType(decision_name)
            except ValueError:
                register_type = BriefingDecisionType.RECLASSIFY
            self.decision_register.append(
                BriefingDecision.create(
                    entity_id=lead.lead_id,
                    aliases=(lead.contact, lead.company, lead.email, lead.notion_url),
                    decision_type=register_type,
                    classification=(classification.strip() or (disposition if disposition not in {"active", "watching"} else "")),
                    reason=reason,
                    source=who,
                    timestamp=now,
                )
            )
        return {"ok": True, "lead_id": lead.lead_id, "disposition": disposition, "external_action_taken": False, "audit": updated.disposition_evidence}

    def _mutate_briefing_entity(self, reference: str, disposition: str, reason: str, actor: str, decision_type: str, classification: str) -> dict | None:
        if self.entity_loader is None or self.decision_register is None:
            return None
        needle = self._normalise(reference)
        matches = [
            item for item in self.entity_loader()
            if needle in {
                self._normalise(item.entity_id), self._normalise(item.item_id),
                self._normalise(item.title), *(self._normalise(alias) for alias in item.aliases),
            }
        ]
        if len(matches) != 1:
            if matches:
                return {"ok": False, "error": "ambiguous_briefing_entity_reference", "matches": [item.entity_id or item.item_id for item in matches]}
            return None
        item = matches[0]
        decision_name = decision_type or {
            "active": "restore", "suppressed": "suppress", "test": "test",
            "archived": "archive", "spam": "spam", "internal": "internal",
            "duplicate": "duplicate", "deferred": "defer",
        }.get(disposition, "reclassify")
        try:
            register_type = BriefingDecisionType(decision_name)
        except ValueError:
            register_type = BriefingDecisionType.RECLASSIFY
        decision = self.decision_register.append(BriefingDecision.create(
            entity_id=item.entity_id or item.item_id,
            aliases=(item.item_id, item.title, *item.aliases),
            decision_type=register_type,
            classification=classification.strip() or item.classification,
            reason=reason,
            source=actor,
            timestamp=self.clock().isoformat(),
        ))
        return {
            "ok": True,
            "entity_id": decision.entity_id,
            "reporting_status": decision.reporting_status,
            "external_action_taken": False,
            "source_record_mutated": False,
        }

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
    def _normalise(value: str) -> str:
        return " ".join(str(value).casefold().split())

    @staticmethod
    def _safe(lead: InboundLead) -> bool:
        text = " ".join((lead.lead_id, lead.contact, lead.company, lead.email, lead.source, lead.status)).casefold()
        return lead.disposition == "test" or ".invalid" in text or any(token in text for token in ("safe", "synthetic", "test"))

    def _event(self, old: InboundLead, new: InboundLead, reason: str, actor: str) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"event_id": str(uuid4()), "type": "lead_disposition_changed", "lead_id": old.lead_id, "from": old.disposition,
                 "to": new.disposition, "reason": reason, "actor": actor, "occurred_at": new.disposition_at, "external_action_taken": False}
        with self.events_path.open("a", encoding="utf-8") as fh: fh.write(json.dumps(event, sort_keys=True) + "\n")
