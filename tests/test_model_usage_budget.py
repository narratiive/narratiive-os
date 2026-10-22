from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from runtime.model_usage_budget import (
    HostedModelBudgetGuard,
    ModelBudgetConfigurationError,
    ModelBudgetExceeded,
    ModelPricing,
    TokenUsage,
    token_usage_from_anthropic,
)


class HostedModelBudgetGuardTests(unittest.TestCase):
    def _guard(self, root: Path, *, hard: str = "25", warning: str = "20") -> HostedModelBudgetGuard:
        (root / "openclaw" / "agents").mkdir(parents=True, exist_ok=True)
        return HostedModelBudgetGuard(
            openclaw_state_dir=root / "openclaw",
            direct_usage_ledger=root / "runtime" / "direct-api.jsonl",
            warning_limit_usd=Decimal(warning),
            hard_limit_usd=Decimal(hard),
            pricing=ModelPricing(Decimal("3"), Decimal("15"), Decimal("0.30"), Decimal("6")),
            now=lambda: datetime(2026, 10, 22, tzinfo=timezone.utc),
        )

    def test_counts_current_month_anthropic_metadata_without_content_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = root / "openclaw" / "agents" / "tony" / "sessions" / "one.jsonl"
            session.parent.mkdir(parents=True)
            event = {
                "timestamp": "2026-10-10T10:00:00Z",
                "message": {
                    "provider": "anthropic",
                    "responseId": "response-1",
                    "content": [{"type": "text", "text": "must never be inspected"}],
                    "usage": {"input": 100, "output": 200, "cacheRead": 300, "cacheWrite": 400},
                },
            }
            session.write_text(json.dumps(event) + "\n" + json.dumps(event) + "\n", encoding="utf-8")
            guard = self._guard(root)

            snapshot = guard.snapshot()

            self.assertEqual(snapshot.usage, TokenUsage(100, 200, 300, 400))
            self.assertEqual(snapshot.period, "2026-10")

    def test_counts_openclaw_retained_deleted_and_reset_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions = root / "openclaw" / "agents" / "tony" / "sessions"
            sessions.mkdir(parents=True)
            for index, suffix in enumerate((".jsonl.deleted.2026-10-20", ".jsonl.reset.2026-10-21"), 1):
                (sessions / f"retained-{index}{suffix}").write_text(
                    json.dumps(
                        {
                            "timestamp": f"2026-10-{10 + index}T10:00:00Z",
                            "message": {
                                "provider": "anthropic",
                                "responseId": f"retained-{index}",
                                "usage": {"input": index, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                            },
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            (sessions / "ignored.trajectory.jsonl").write_text("not transcript metadata\n", encoding="utf-8")

            self.assertEqual(self._guard(root).snapshot().usage.input_tokens, 3)

    def test_direct_usage_is_append_only_private_and_included(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guard = self._guard(root)

            guard.record_direct_usage(
                provider="anthropic",
                model="claude-sonnet-4-6",
                response_id="direct-1",
                usage=TokenUsage(10, 20, 30, 40),
            )

            self.assertEqual(guard.snapshot().usage, TokenUsage(10, 20, 30, 40))
            self.assertEqual(guard.direct_usage_ledger.stat().st_mode & 0o777, 0o600)

    def test_hard_limit_fails_closed_without_weak_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            guard = self._guard(Path(directory), hard="1", warning="0.50")

            with self.assertRaisesRegex(ModelBudgetExceeded, "will not silently fall back"):
                guard.require_capacity(reserve_usd=Decimal("1"))

    def test_capacity_reservations_are_shared_across_guard_instances(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self._guard(root, hard="3", warning="1")
            second = self._guard(root, hard="3", warning="1")

            reservation = first.reserve_capacity(reserve_usd=Decimal("2"))
            with self.assertRaises(ModelBudgetExceeded):
                second.reserve_capacity(reserve_usd=Decimal("1"))

            first.release_reservation(reservation)
            replacement = second.reserve_capacity(reserve_usd=Decimal("1"))
            self.assertEqual(second.snapshot().reserved_cost_usd, Decimal("1"))
            second.release_reservation(replacement)

    def test_settling_direct_usage_atomically_replaces_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            guard = self._guard(Path(directory))
            reservation = guard.reserve_capacity(reserve_usd=Decimal("2"))

            guard.settle_direct_usage(
                reservation,
                provider="anthropic",
                model="claude-sonnet-4-6",
                response_id="settled-1",
                usage=TokenUsage(output_tokens=1000),
            )

            snapshot = guard.snapshot()
            self.assertEqual(snapshot.reserved_cost_usd, Decimal("0"))
            self.assertEqual(snapshot.usage.output_tokens, 1000)

    def test_environment_requires_both_limits(self) -> None:
        with self.assertRaises(ModelBudgetConfigurationError):
            HostedModelBudgetGuard.from_environment({"TONY_HOSTED_MODEL_MONTHLY_LIMIT_USD": "25"})

    def test_environment_resolves_supported_openclaw_state_locations(self) -> None:
        base = {
            "TONY_HOSTED_MODEL_MONTHLY_LIMIT_USD": "25",
            "TONY_HOSTED_MODEL_WARNING_USD": "20",
        }
        self.assertEqual(
            HostedModelBudgetGuard.from_environment(
                {**base, "OPENCLAW_HOME": "/srv/openclaw"}
            ).openclaw_state_dir,
            Path("/srv/openclaw/.openclaw"),
        )
        self.assertEqual(
            HostedModelBudgetGuard.from_environment(
                {**base, "OPENCLAW_CONFIG_PATH": "/srv/state/config.json"}
            ).openclaw_state_dir,
            Path("/srv/state"),
        )
        self.assertEqual(
            HostedModelBudgetGuard.from_environment(
                {
                    **base,
                    "OPENCLAW_HOME": "/ignored",
                    "OPENCLAW_CONFIG_PATH": "/ignored/config.json",
                    "OPENCLAW_STATE_DIR": "/srv/explicit",
                }
            ).openclaw_state_dir,
            Path("/srv/explicit"),
        )

    def test_existing_unreadable_usage_metadata_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "runtime" / "direct-api.jsonl"
            ledger.mkdir(parents=True)
            guard = self._guard(root)

            with self.assertRaisesRegex(ModelBudgetConfigurationError, "usage metadata is unreadable"):
                guard.reserve_capacity()

    def test_malformed_usage_metadata_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = root / "openclaw" / "agents" / "tony" / "sessions" / "one.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text("{incomplete\n", encoding="utf-8")

            with self.assertRaisesRegex(ModelBudgetConfigurationError, "invalid JSON"):
                self._guard(root).reserve_capacity()

    def test_missing_openclaw_usage_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            guard = HostedModelBudgetGuard(
                openclaw_state_dir=root / "missing-openclaw",
                direct_usage_ledger=root / "runtime" / "direct-api.jsonl",
                warning_limit_usd=Decimal("20"),
                hard_limit_usd=Decimal("25"),
                pricing=ModelPricing(Decimal("3"), Decimal("15"), Decimal("0.30"), Decimal("6")),
                now=lambda: datetime(2026, 10, 22, tzinfo=timezone.utc),
            )

            with self.assertRaisesRegex(ModelBudgetConfigurationError, "directory is unavailable"):
                guard.reserve_capacity()

    def test_invalid_anthropic_usage_shape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = root / "openclaw" / "agents" / "tony" / "sessions" / "one.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-10-22T10:00:00Z",
                        "message": {
                            "provider": "anthropic",
                            "responseId": "broken-usage",
                            "usage": "unknown",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ModelBudgetConfigurationError, "usage metadata"):
                self._guard(root).reserve_capacity()

    def test_invalid_openclaw_usage_counters_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = root / "openclaw" / "agents" / "tony" / "sessions" / "one.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-10-22T10:00:00Z",
                        "message": {
                            "provider": "anthropic",
                            "responseId": "broken-counter",
                            "usage": {"input": "invalid", "output": 2, "cacheRead": 0, "cacheWrite": 0},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ModelBudgetConfigurationError, "input is invalid"):
                self._guard(root).reserve_capacity()

    def test_non_finite_budget_values_are_rejected(self) -> None:
        for value in ("Infinity", "NaN", "-Infinity"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ModelBudgetConfigurationError, "finite decimal"):
                    HostedModelBudgetGuard.from_environment(
                        {
                            "TONY_HOSTED_MODEL_MONTHLY_LIMIT_USD": value,
                            "TONY_HOSTED_MODEL_WARNING_USD": "20",
                        }
                    )

    def test_anthropic_usage_conversion(self) -> None:
        usage = token_usage_from_anthropic(
            {
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "cache_read_input_tokens": 3,
                    "cache_creation_input_tokens": 4,
                }
            }
        )
        self.assertEqual(usage, TokenUsage(1, 2, 3, 4))

    def test_anthropic_usage_conversion_rejects_missing_or_invalid_metadata(self) -> None:
        for payload in (
            {},
            {"usage": None},
            {"usage": {"input_tokens": 1}},
            {"usage": {"input_tokens": "invalid", "output_tokens": 2}},
            {"usage": {"input_tokens": 1, "output_tokens": -1}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ModelBudgetConfigurationError):
                    token_usage_from_anthropic(payload)


if __name__ == "__main__":
    unittest.main()
