from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from wsgiref.simple_server import make_server

from openclaw.tony_http_bridge import TonyHTTPBridge, build_app as build_base_app
from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_executive_commands import TonyExecutiveCommandService


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_friday_review_records(root: Path) -> list[dict[str, Any]]:
    """Load only explicit executive-review evidence records from JSON files."""
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            required = {
                "record_id",
                "occurred_at",
                "record_type",
                "summary",
                "evidence",
                "workspace_id",
            }
            if required.issubset(candidate):
                records.append(candidate)
    return records


def build_app() -> TonyHTTPBridge:
    """Build the production bridge with one coherent deterministic command surface."""
    app = build_base_app()
    if app.command_service is None:
        raise RuntimeError("Tony command service is not configured")

    records_root = Path(
        os.getenv(
            "TONY_FRIDAY_REVIEW_RECORDS_ROOT",
            str(REPOSITORY_ROOT / ".runtime" / "executive-review-records"),
        )
    )
    executive_service = TonyExecutiveCommandService(
        app.command_service,
        brief_archive=app.brief_archive,
        friday_record_loader=lambda: load_friday_review_records(records_root),
        workspace_id=(
            os.getenv("TONY_EXECUTIVE_WORKSPACE_ID", "").strip()
            or os.getenv("TONY_GITHUB_WORKSPACE_ID", "").strip()
            or "narratiive"
        ),
    )
    app.command_service = TonyCapabilityCommandService(executive_service)
    return app


def main() -> None:
    host = os.getenv("TONY_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("TONY_BRIDGE_PORT", "8790"))
    with make_server(host, port, build_app()) as server:
        print(f"Tony bridge listening on http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
