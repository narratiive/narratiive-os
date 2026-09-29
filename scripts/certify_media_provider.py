from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.execution_journal import ExecutionJournal
from runtime.media_control import (
    MediaControlService,
    MediaMutationDisabled,
    MediaProvider,
    WRITE_OPERATIONS,
)
from runtime.media_provider_transports import build_configured_media_adapters


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Certify one configured media provider using read-only live API calls.",
    )
    parser.add_argument("provider", choices=tuple(item.value for item in MediaProvider))
    parser.add_argument("--request-id", default="")
    parser.add_argument(
        "--include-inventory",
        action="store_true",
        help="also read and audit campaigns, ad groups/ad sets, ads and creative metadata",
    )
    args = parser.parse_args()

    provider = MediaProvider(args.provider)
    request_id = args.request_id.strip() or (
        f"{provider.value}-live-certification-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    state_root = Path(
        os.getenv(
            "TONY_MEDIA_CONTROL_STATE_ROOT",
            str(REPOSITORY_ROOT / ".runtime" / "media-control"),
        )
    )
    adapters = build_configured_media_adapters(os.environ)
    service = MediaControlService(adapters, ExecutionJournal(state_root))
    result = service.certify_provider(provider, request_id=request_id)
    inventory = None
    if args.include_inventory:
        inventory_result = service.sync_inventory(
            provider,
            request_id=request_id + "-inventory",
        )
        inventory = {
            "provider": provider.value,
            "counts": inventory_result.counts(),
            "synced_at": inventory_result.synced_at,
            "external_write_performed": False,
        }

    adapter = adapters[provider]
    blocked_operations: list[str] = []
    for operation in sorted(WRITE_OPERATIONS):
        try:
            getattr(adapter, operation)({"certification_probe": True})
        except MediaMutationDisabled:
            blocked_operations.append(operation)
        else:
            raise RuntimeError(f"Phase 1 write operation was not blocked: {operation}")

    diagnostic = service.diagnostics()[provider.value]
    print(
        json.dumps(
            {
                "ok": True,
                "certification": result,
                "diagnostic": diagnostic,
                "inventory": inventory,
                "phase_one_write_safety": {
                    "status": "hard_disabled",
                    "blocked_operations": blocked_operations,
                    "external_write_performed": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
