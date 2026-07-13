from __future__ import annotations

import argparse
import os
from pathlib import Path
from wsgiref.simple_server import make_server

from .command_api import WorkspaceCommandAPI
from .composition import compose_local_runtime
from .production_gateway import GatewayConfig, ProductionGateway
from .wsgi_api import RuntimeWSGIApp
from .workspaces import WorkspaceRuntimeManager


def build_app(*, repository_root: str | Path, runtime_root: str | Path, api_key: str) -> ProductionGateway:
    runtime = compose_local_runtime(root=runtime_root, repository_root=repository_root)
    command_api = WorkspaceCommandAPI(
        runtime,
        WorkspaceRuntimeManager(runtime_root, repository_root),
    )
    wsgi = RuntimeWSGIApp(command_api)
    return ProductionGateway(
        wsgi,
        GatewayConfig(
            api_key=api_key,
            idempotency_root=Path(runtime_root) / "idempotency",
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Narratiive OS command gateway")
    parser.add_argument("--host", default=os.getenv("NARRATIIVE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("NARRATIIVE_PORT", "8787")))
    parser.add_argument("--repository-root", default=os.getenv("NARRATIIVE_REPOSITORY_ROOT", "."))
    parser.add_argument("--runtime-root", default=os.getenv("NARRATIIVE_RUNTIME_ROOT", ".runtime"))
    args = parser.parse_args()

    api_key = os.getenv("NARRATIIVE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("NARRATIIVE_API_KEY is required")

    app = build_app(
        repository_root=args.repository_root,
        runtime_root=args.runtime_root,
        api_key=api_key,
    )
    with make_server(args.host, args.port, app) as server:
        print(f"Narratiive OS listening on http://{args.host}:{args.port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
