from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.model_usage_budget import HostedModelBudgetGuard


def main() -> int:
    guard = HostedModelBudgetGuard.from_environment(
        os.environ,
        repository_root=ROOT,
    )
    if guard is None:
        print(json.dumps({"configured": False, "status": "spending_limits_not_configured"}, sort_keys=True))
        return 2
    snapshot = guard.snapshot()
    payload = {
        "configured": True,
        "period": snapshot.period,
        "estimated_cost_usd": str(snapshot.estimated_cost_usd.quantize(Decimal("0.01"))),
        "reserved_cost_usd": str(snapshot.reserved_cost_usd.quantize(Decimal("0.01"))),
        "warning_limit_usd": str(snapshot.warning_limit_usd),
        "hard_limit_usd": str(snapshot.hard_limit_usd),
        "warning_reached": snapshot.warning_reached,
        "hard_limit_reached": snapshot.hard_limit_reached,
        "tokens": {
            "input": snapshot.usage.input_tokens,
            "output": snapshot.usage.output_tokens,
            "cache_read": snapshot.usage.cache_read_tokens,
            "cache_write": snapshot.usage.cache_write_tokens,
        },
    }
    print(json.dumps(payload, sort_keys=True))
    return 1 if snapshot.warning_reached else 0


if __name__ == "__main__":
    raise SystemExit(main())
