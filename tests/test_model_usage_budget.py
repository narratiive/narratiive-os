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

    def test_environment_requires_both_limits(self) -> None:
        with self.assertRaises(ModelBudgetConfigurationError):
            HostedModelBudgetGuard.from_environment({"TONY_HOSTED_MODEL_MONTHLY_LIMIT_USD": "25"})

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


if __name__ == "__main__":
    unittest.main()
