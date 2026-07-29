from __future__ import annotations

from runtime.client_lifecycle import ClientLifecycleRecord, ClientLifecycleStage


def deterministic_test_clients() -> tuple[ClientLifecycleRecord, ...]:
    """Stable agency fixture covering commercial, delivery, finance and decision states."""
    return (
        ClientLifecycleRecord(
            client_id="northstar",
            client_name="Northstar Labs",
            stage=ClientLifecycleStage.PROPOSAL,
            owner="Tony",
            next_action="Send the Growth Blueprint proposal.",
            evidence=("proposal:northstar:v1",),
            value_gbp=6000,
        ),
        ClientLifecycleRecord(
            client_id="fieldwork",
            client_name="Fieldwork Foods",
            stage=ClientLifecycleStage.DELIVERY,
            owner="Tony",
            next_action="Complete the audience opportunity synthesis.",
            evidence=("delivery:fieldwork:research-complete",),
            value_gbp=4500,
        ),
        ClientLifecycleRecord(
            client_id="signal-house",
            client_name="Signal House",
            stage=ClientLifecycleStage.INVOICE,
            owner="Matt",
            next_action="Approve and issue the final invoice.",
            evidence=("invoice:signal-house:draft",),
            requires_matt=True,
            value_gbp=3000,
        ),
    )
