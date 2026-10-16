from __future__ import annotations


FIELDWORK_PILOT_POLICY_VERSION = "2026-10-16"
FIELDWORK_PILOT_FEE_GBP = 5_000
FIELDWORK_PILOT_POLICY = {
    "product": "FIELDWORK pilot",
    "fee_gbp": FIELDWORK_PILOT_FEE_GBP,
    "deposit_percent": 50,
    "balance_percent": 50,
    "balance_due": "before final delivery",
    "included_revisions": 1,
    "revision_shape": "one consolidated revision",
    "vat": "added only when applicable to Narratiive's registration status",
    "production_scope": "separate",
    "activation_scope": "separate",
    "version": FIELDWORK_PILOT_POLICY_VERSION,
}


def fieldwork_pilot_policy() -> dict[str, object]:
    """Return the exact human-approved commercial policy for proposal preparation."""

    return dict(FIELDWORK_PILOT_POLICY)
