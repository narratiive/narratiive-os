from __future__ import annotations

from collections.abc import Iterable

from runtime.inbound_leads import InboundLead
from runtime.models import WorkflowState


HIDDEN_DISPOSITIONS = frozenset({"suppressed", "test", "archived"})
NO_ACTION_LEAD_STATUSES = frozenset({"complete", "completed", "closed", "won", "lost", "disqualified"})


class ExecutiveVisibilityPolicy:
    """Select attention-worthy records without deleting operational history.

    Direct lead and workflow lookup continues to use the underlying stores.  This
    policy is only for executive projections and brief inputs.
    """

    def visible_leads(self, leads: Iterable[InboundLead]) -> tuple[InboundLead, ...]:
        return tuple(
            lead
            for lead in leads
            if lead.disposition not in HIDDEN_DISPOSITIONS
            and lead.status.strip().casefold() not in NO_ACTION_LEAD_STATUSES
        )

    def visible_workflows(
        self,
        states: Iterable[WorkflowState],
        leads: Iterable[InboundLead],
    ) -> tuple[WorkflowState, ...]:
        hidden_ids = {
            lead.lead_id.strip().casefold()
            for lead in leads
            if lead.disposition in HIDDEN_DISPOSITIONS
        }
        return tuple(
            state
            for state in states
            if not hidden_ids.intersection(
                {
                    state.client_id.strip().casefold(),
                    state.entity_id.strip().casefold(),
                }
            )
        )
