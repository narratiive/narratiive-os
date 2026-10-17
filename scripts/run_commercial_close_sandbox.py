from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.commercial_close_boundary import (  # noqa: E402
    CommercialCloseBoundary,
    CommercialClosePolicy,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise the isolated contract/payment sandbox boundary")
    parser.add_argument("--opportunity-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    policy = CommercialClosePolicy(
        opportunity_id=args.opportunity_id,
        total_amount_minor=500_000,
        deposit_amount_minor=250_000,
        currency="GBP",
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    contract, payment = CommercialCloseBoundary.sandbox_receipts(policy, occurred_at=timestamp)
    result = {
        "schema_version": 1,
        "tested_at": timestamp,
        "policy": {
            "total_amount_minor": policy.total_amount_minor,
            "deposit_amount_minor": policy.deposit_amount_minor,
            "currency": policy.currency,
            "terms": "50% upfront / 50% before final delivery",
        },
        "contract_receipt": contract,
        "payment_receipt": payment,
        "boundary_result": CommercialCloseBoundary.evaluate(
            policy,
            contract,
            payment,
            environment="sandbox",
        ),
        "money_moved": False,
        "external_provider_called": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.output)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

