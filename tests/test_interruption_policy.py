from datetime import datetime, timedelta, timezone
from unittest import TestCase

from runtime.interruption_policy import (
    FixedCooldownInterruptionPolicy,
    InterruptionContext,
)


_ASSERTIONS = TestCase()


def _context(
    *,
    material_ids: tuple[str, ...] = ("blocker:1",),
    now: datetime | None = None,
    last_sent_at: datetime | None = None,
    workspace_id: str = "narratiive",
    recipient_id: str = "matt",
) -> InterruptionContext:
    return InterruptionContext(
        workspace_id=workspace_id,
        recipient_id=recipient_id,
        material_ids=material_ids,
        now=now or datetime(2026, 7, 27, 17, 0, tzinfo=timezone.utc),
        last_sent_at=last_sent_at,
    )


def test_suppresses_when_there_is_no_material() -> None:
    decision = FixedCooldownInterruptionPolicy().evaluate(
        _context(material_ids=())
    )

    assert decision.action == "suppress"
    assert decision.reason == "no_material"
    assert decision.retry_at is None


def test_sends_when_no_prior_interruption_exists() -> None:
    decision = FixedCooldownInterruptionPolicy().evaluate(_context())

    assert decision.action == "send_now"
    assert decision.reason == "material_available"
    assert decision.retry_at is None


def test_defers_with_explicit_retry_time_inside_cooldown() -> None:
    now = datetime(2026, 7, 27, 17, 0, tzinfo=timezone.utc)
    last_sent = now - timedelta(minutes=10)

    decision = FixedCooldownInterruptionPolicy(min_interval_seconds=1800).evaluate(
        _context(now=now, last_sent_at=last_sent)
    )

    assert decision.action == "defer"
    assert decision.reason == "cooldown_active"
    assert decision.retry_at == last_sent + timedelta(seconds=1800)


def test_sends_at_exact_cooldown_boundary() -> None:
    now = datetime(2026, 7, 27, 17, 0, tzinfo=timezone.utc)
    last_sent = now - timedelta(minutes=30)

    decision = FixedCooldownInterruptionPolicy(min_interval_seconds=1800).evaluate(
        _context(now=now, last_sent_at=last_sent)
    )

    assert decision.action == "send_now"
    assert decision.reason == "cooldown_elapsed"


def test_zero_cooldown_sends_immediately() -> None:
    now = datetime(2026, 7, 27, 17, 0, tzinfo=timezone.utc)

    decision = FixedCooldownInterruptionPolicy(min_interval_seconds=0).evaluate(
        _context(now=now, last_sent_at=now)
    )

    assert decision.action == "send_now"


def test_rejects_incompatible_datetime_awareness() -> None:
    with _ASSERTIONS.assertRaisesRegex(ValueError, "compatible timezone awareness"):
        _context(
            now=datetime(2026, 7, 27, 17, 0, tzinfo=timezone.utc),
            last_sent_at=datetime(2026, 7, 27, 16, 30),
        )


def test_rejects_blank_material_identity() -> None:
    with _ASSERTIONS.assertRaisesRegex(ValueError, "material_ids"):
        _context(material_ids=("blocker:1", " "))


def test_canonicalises_identity_fields_and_material_evidence() -> None:
    context = _context(
        workspace_id=" narratiive ",
        recipient_id=" matt ",
        material_ids=(
            " approval:PR-95 ",
            "blocker:runtime   validation",
            "approval:PR-95",
        ),
    )

    assert context.workspace_id == "narratiive"
    assert context.recipient_id == "matt"
    assert context.material_ids == (
        "approval:PR-95",
        "blocker:runtime validation",
    )


def test_equivalent_material_sets_produce_identical_policy_inputs() -> None:
    first = _context(material_ids=("blocker:2", "approval:1", "blocker:2"))
    second = _context(material_ids=(" approval:1 ", "blocker:2"))

    assert first.material_ids == second.material_ids


def test_rejects_negative_cooldown() -> None:
    with _ASSERTIONS.assertRaisesRegex(ValueError, "must not be negative"):
        FixedCooldownInterruptionPolicy(min_interval_seconds=-1)
