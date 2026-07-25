from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from wsgiref.simple_server import make_server

from openclaw.tony_http_bridge import TonyHTTPBridge, build_app as build_base_app
from runtime.tony_capability_commands import TonyCapabilityCommandService
from runtime.tony_executive_commands import TonyExecutiveCommandService
from runtime.tony_terminology_commands import TonyTerminologyCommandService


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REQUIRED_FRIDAY_FIELDS = {
    "record_id",
    "occurred_at",
    "record_type",
    "summary",
    "evidence",
    "workspace_id",
}


def load_friday_review_records(root: Path) -> list[dict[str, Any]]:
    """Load a complete trusted Friday evidence store or fail closed."""
    if not root.is_dir():
        raise FileNotFoundError("Friday Review evidence store is unavailable")

    paths = sorted(root.rglob("*.json"))
    if not paths:
        raise ValueError("Friday Review evidence store contains no JSON records")

    records: list[dict[str, Any]] = []
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Friday Review evidence file is unreadable: {path.name}"
            ) from exc

        candidates = value if isinstance(value, list) else [value]
        if not candidates:
            raise ValueError(f"Friday Review evidence file is empty: {path.name}")
        for candidate in candidates:
            if not isinstance(candidate, dict) or not _REQUIRED_FRIDAY_FIELDS.issubset(candidate):
                raise ValueError(
                    f"Friday Review evidence record is invalid: {path.name}"
                )
            records.append(candidate)

    if not records:
        raise ValueError("Friday Review evidence store contains no records")
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
    capability_service = TonyCapabilityCommandService(executive_service)
    app.command_service = TonyTerminologyCommandService(capability_service)
    return app


def main() -> None:
    host = os.getenv("TONY_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("TONY_BRIDGE_PORT", "8790"))
    with make_server(host, port, build_app()) as server:
        print(f"Tony bridge listening on http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
