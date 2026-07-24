from __future__ import annotations

import os
from wsgiref.simple_server import make_server

from openclaw.tony_http_bridge import TonyHTTPBridge, build_app as build_base_app
from runtime.tony_executive_commands import TonyExecutiveCommandService


def build_app() -> TonyHTTPBridge:
    """Build the production bridge with evidence-backed executive commands enabled."""
    app = build_base_app()
    if app.command_service is None:
        raise RuntimeError("Tony command service is not configured")
    app.command_service = TonyExecutiveCommandService(app.command_service)
    return app


def main() -> None:
    host = os.getenv("TONY_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("TONY_BRIDGE_PORT", "8790"))
    with make_server(host, port, build_app()) as server:
        print(f"Tony bridge listening on http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
