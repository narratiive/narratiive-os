from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid4
from wsgiref.simple_server import make_server

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.executive_brief import ExecutiveBriefArchive
from runtime.github_work import (
    GitHubConfig,
    GitHubRESTClient,
    GitHubWorkService,
    GitHubWorkSnapshot,
)
from runtime.mission_control import MissionControlBuilder, MissionControlSnapshot
from runtime.progress_engine import RepositoryProgressEngine
from runtime.repository_validator import GrowthObjectValidator
from runtime.tony_command_service import CommandResponse, TonyCommandService
from runtime.tony_orchestration import (
    HttpGatewayTransport,
    TonyCommand,
    TonyGatewayError,
    TonyOrchestrationAdapter,
)
from runtime.workspaces import WorkspaceRuntimeManager
from scripts.service_doctor import ServiceDoctor


ObjectLoader = Callable[[], Iterable[dict[str, Any]]]
DiagnosticsRunner = Callable[[], dict[str, Any]]
MissionControlLoader = Callable[[], MissionControlSnapshot]
GitHubWorkLoader = Callable[[], GitHubWorkSnapshot]


class TonyHTTPBridge:
    """Small authenticated HTTP boundary for OpenClaw, Telegram and n8n.

    Telegram slash commands are deliberately handled by deterministic services.
    They never depend on a managerial LLM, so operational status remains
    available even when a language-model provider is slow or offline.
    """

    def __init__(
        self,
        adapter: TonyOrchestrationAdapter,
        bridge_token: str = "",
        *,
        command_service: TonyCommandService | None = None,
        object_loader: ObjectLoader | None = None,
        diagnostics_runner: DiagnosticsRunner | None = None,
        brief_archive: ExecutiveBriefArchive | None = None,
    ) -> None:
        self.adapter = adapter
        self.bridge_token = bridge_token.strip()
        self.command_service = command_service
        self.object_loader = object_loader
        self.diagnostics_runner = diagnostics_runner
        self.brief_archive = brief_archive

    def __call__(self, environ, start_response):
        try:
            status, payload = self.handle(environ)
        except Exception:
            status, payload = HTTPStatus.INTERNAL_SERVER_ERROR, {
                "ok": False,
                "error": {"code": "bridge_error", "message": "Tony bridge failed"},
            }
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        start_response(
            f"{status.value} {status.phrase}",
            [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
        )
        return [body]

    def handle(self, environ):
        method = str(environ.get("REQUEST_METHOD", "")).upper()
        path = str(environ.get("PATH_INFO", "/")) or "/"

        if method == "GET" and path == "/health":
            mission_control = False
            if self.command_service is not None:
                mission_control = self.command_service.mission_control_loader is not None
            return HTTPStatus.OK, {
                "ok": True,
                "service": "tony-http-bridge",
                "status": "alive",
                "deterministic_commands": self.command_service is not None,
                "diagnostics": self.diagnostics_runner is not None,
                "mission_control": mission_control,
                "github": bool(
                    self.command_service is not None
                    and getattr(self.command_service, "github_configured", False)
                ),
            }

        if method != "POST":
            return HTTPStatus.METHOD_NOT_ALLOWED, self._error("method_not_allowed", "POST required")
        if self.bridge_token:
            supplied = str(environ.get("HTTP_AUTHORIZATION", ""))
            if supplied != f"Bearer {self.bridge_token}":
                return HTTPStatus.UNAUTHORIZED, self._error("unauthorized", "Invalid bridge token")
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
            raw = environ["wsgi.input"].read(length).decode("utf-8")
            request = json.loads(raw or "{}")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return HTTPStatus.BAD_REQUEST, self._error("invalid_json", "Request must be valid JSON")
        if not isinstance(request, dict):
            return HTTPStatus.BAD_REQUEST, self._error("invalid_request", "Request must be an object")

        telegram_command = self._extract_telegram_command(request)
        if telegram_command is not None:
            return self._handle_telegram_command(telegram_command)

        required = ("action", "workspace_id", "client_id")
        missing = [name for name in required if not str(request.get(name, "")).strip()]
        if missing:
            return HTTPStatus.BAD_REQUEST, self._error("missing_fields", ", ".join(missing))
        command_id = str(request.get("command_id", "")).strip() or f"bridge-{uuid4().hex}"
        try:
            response = self.adapter.execute(
                TonyCommand(
                    action=str(request["action"]),
                    workspace_id=str(request["workspace_id"]),
                    client_id=str(request["client_id"]),
                    command_id=command_id,
                    reviewer_id=str(request.get("reviewer_id", "")),
                    rationale=str(request.get("rationale", "")),
                    payload=request.get("payload") if isinstance(request.get("payload"), dict) else {},
                )
            )
        except TonyGatewayError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if exc.retryable else HTTPStatus.BAD_REQUEST
            return status, {
                "ok": False,
                "command_id": command_id,
                "error": {"code": exc.code, "message": str(exc), "retryable": exc.retryable},
            }
        return HTTPStatus.OK, {
            "ok": True,
            "message": response.message,
            "reply": response.message,
            "command": response.command,
            "command_id": command_id,
            "correlation_id": response.correlation_id,
            "data": response.data,
        }

    def _handle_telegram_command(self, command: str):
        name = command.strip().split(" ", 1)[0].lower().lstrip("/")
        if name in {"diagnostics", "doctor"}:
            return self._handle_diagnostics()
        if self.command_service is None or self.object_loader is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, self._error(
                "command_service_unavailable",
                "Repository-backed Tony commands are not configured",
            )
        try:
            objects = list(self.object_loader())
            response = self.command_service.execute(command, objects)
        except Exception:
            return HTTPStatus.SERVICE_UNAVAILABLE, self._error(
                "repository_state_unavailable",
                "Tony could not read repository state",
            )
        payload = response.to_dict()
        reply = self._format_telegram_reply(response)
        return HTTPStatus.OK, {
            "ok": response.status != "error",
            "reply": reply,
            "message": reply,
            **payload,
        }

    def _handle_diagnostics(self):
        if self.diagnostics_runner is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, self._error(
                "diagnostics_unavailable",
                "Tony diagnostics are not configured",
            )
        try:
            report = self.diagnostics_runner()
        except Exception:
            return HTTPStatus.SERVICE_UNAVAILABLE, self._error(
                "diagnostics_failed",
                "Tony diagnostics could not complete",
            )
        checks = report.get("checks", []) if isinstance(report, dict) else []
        failed = [check for check in checks if isinstance(check, dict) and not check.get("healthy")]
        lines = ["Tony diagnostics: healthy." if not failed else "Tony diagnostics: degraded."]
        for check in checks:
            if not isinstance(check, dict):
                continue
            marker = "OK" if check.get("healthy") else "FAIL"
            line = f"{marker} — {check.get('name', 'unknown')}"
            if check.get("error"):
                line += f": {check['error']}"
            lines.append(line)
        reply = "\n".join(lines)[:3500]
        return HTTPStatus.OK, {
            "ok": not failed,
            "command": "diagnostics",
            "status": "healthy" if not failed else "degraded",
            "reply": reply,
            "message": reply,
            "data": report,
        }

    @staticmethod
    def _extract_telegram_command(request: dict[str, Any]) -> str | None:
        candidates: list[Any] = [request.get("text"), request.get("message")]
        body = request.get("body")
        if isinstance(body, dict):
            candidates.extend([body.get("text"), body.get("message")])
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate = candidate.get("text")
            if isinstance(candidate, str):
                normalized = candidate.strip()
                if normalized.startswith("/"):
                    return normalized
        return None

    @staticmethod
    def _format_telegram_reply(response: CommandResponse) -> str:
        lines = [response.message]
        data = response.data
        if response.command in {"mission", "mission_control", "brief"}:
            blockers = data.get("blockers", [])
            approvals = data.get("approvals_required", [])
            workstreams = data.get("workstreams", [])
            if blockers:
                lines.append("Blockers:")
                lines.extend(f"- {item}" for item in blockers[:5])
            if approvals:
                lines.append("Approvals:")
                lines.extend(f"- {item}" for item in approvals[:5])
            actionable = [
                item for item in workstreams
                if isinstance(item, dict) and item.get("state") not in {"used", "unknown"}
            ]
            if actionable:
                lines.append("Next work:")
                for item in actionable[:5]:
                    suffix = f" — BLOCKED: {item.get('blocker')}" if item.get("blocker") else ""
                    lines.append(f"- {item.get('title', 'Untitled')}: {item.get('next_action', 'No action')}{suffix}")
        elif response.command in {"status", "progress", "progress_update"}:
            lines.append(f"Campaigns: {data.get('campaign_count', 0)}")
            lines.append(f"Blocked: {data.get('blocked_count', 0)}")
        elif response.command == "github":
            pulls = data.get("open_pull_requests", [])
            issues = data.get("active_issues", [])
            blocked = data.get("blocked", [])
            reviews = data.get("matt_approval_required", [])
            changes = data.get("changes_since_previous_brief", [])
            if pulls:
                lines.append("Open pull requests:")
                lines.extend(
                    f"- #{item.get('number')} {item.get('title')}"
                    for item in pulls[:10]
                    if isinstance(item, dict)
                )
            if issues:
                lines.append("Active issues:")
                lines.extend(
                    f"- #{item.get('number')} {item.get('title')}"
                    for item in issues[:10]
                    if isinstance(item, dict)
                )
            if blocked:
                lines.append("Blocked:")
                lines.extend(
                    f"- #{item.get('number')} {item.get('title')}: "
                    f"{', '.join(item.get('blocker_reasons', []))}"
                    for item in blocked[:10]
                    if isinstance(item, dict)
                )
            if reviews:
                lines.append("Requires Matt review:")
                lines.extend(
                    f"- #{item.get('number')} {item.get('title')}"
                    for item in reviews[:10]
                    if isinstance(item, dict)
                )
            if changes:
                lines.append("Changed since previous brief:")
                lines.extend(
                    f"- {item.get('action')}: "
                    f"#{item.get('item', {}).get('number')} "
                    f"{item.get('item', {}).get('title')}"
                    for item in changes[:10]
                    if isinstance(item, dict)
                    and isinstance(item.get("item"), dict)
                )
            elif data.get("baseline_status") == "unavailable":
                lines.append("Changed since previous brief: baseline unavailable.")
            else:
                lines.append(
                    "Changed since previous brief: no material changes."
                )
        elif response.command == "health":
            validation = data.get("validation", {})
            lines.append(f"Objects validated: {validation.get('objects_validated', 0)}")
        elif response.command == "client":
            campaigns = data.get("campaigns", [])
            if campaigns:
                current = campaigns[0]
                lines.append(f"Stage: {current.get('current_stage', 'unknown')}")
                lines.append(f"Next: {current.get('next_action', 'No action available')}")
        elif response.command in {"next", "what_next", "continue"}:
            primary = data.get("primary", {})
            if primary:
                lines.append(f"Stage: {primary.get('current_stage', 'unknown')}")
                lines.append(f"Owner action: {primary.get('next_action', 'No action available')}")
        if response.status == "blocked":
            lines.append("Status: blocked")
        elif response.status == "error":
            lines.append(f"Error: {data.get('error_code', 'unknown_error')}")
        return "\n".join(lines)[:3500]

    @staticmethod
    def _error(code: str, message: str):
        return {"ok": False, "error": {"code": code, "message": message}}


def load_growth_objects(root: Path) -> list[dict[str, Any]]:
    """Load canonical object records while ignoring schemas and unrelated JSON."""
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
            if isinstance(candidate, dict) and candidate.get("id") and candidate.get("object_type"):
                records.append(candidate)
    return records


def build_mission_control_loader(
    progress_engine: RepositoryProgressEngine,
    object_loader: ObjectLoader,
    gateway_health_endpoint: str,
    github_work_loader: GitHubWorkLoader | None = None,
) -> MissionControlLoader:
    """Build the live read-only Mission Control snapshot used by Telegram commands."""
    builder = MissionControlBuilder()
    doctor = ServiceDoctor(timeout_seconds=float(os.getenv("NARRATIIVE_DOCTOR_TIMEOUT_SECONDS", "3")))

    def load() -> MissionControlSnapshot:
        objects = list(object_loader())
        progress = progress_engine.build_snapshot(objects)
        gateway = doctor.check("runtime-gateway", gateway_health_endpoint)
        connection_state = "connected" if gateway.healthy else "degraded"
        evidence = "HTTP health check passed" if gateway.healthy else gateway.error
        github_work = None
        if github_work_loader is None:
            github_connection = {
                "state": "not_connected",
                "evidence": "GitHub awareness is not configured",
            }
        else:
            try:
                github_work = github_work_loader()
                github_connection = {
                    "state": "connected",
                    "evidence": (
                        f"GitHub API observation for {github_work.repository} "
                        f"at {github_work.observed_at}"
                    ),
                    "last_checked_at": github_work.observed_at,
                }
            except Exception as exc:
                github_connection = {
                    "state": "degraded",
                    "evidence": f"GitHub awareness failed closed: {exc}",
                }
        return builder.build(
            generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            progress=progress,
            connections={
                "runtime-gateway": {
                    "state": connection_state,
                    "evidence": evidence,
                },
                "telegram-bridge": {
                    "state": "connected",
                    "evidence": "Current request reached Tony HTTP bridge",
                },
                "GitHub": github_connection,
            },
            github_work=github_work,
        )

    return load


def build_github_components(
    *,
    runtime_root: Path,
    repository_root: Path,
) -> tuple[GitHubWorkLoader | None, ExecutiveBriefArchive | None]:
    repository = os.getenv("TONY_GITHUB_REPOSITORY", "").strip()
    workspace_id = os.getenv("TONY_GITHUB_WORKSPACE_ID", "").strip()
    matt_login = os.getenv("TONY_GITHUB_MATT_LOGIN", "").strip()
    token = os.getenv("TONY_GITHUB_TOKEN", "").strip()
    if not all((repository, workspace_id, matt_login, token)):
        return None, None

    config = GitHubConfig(
        repository=repository,
        workspace_id=workspace_id,
        matt_login=matt_login,
        api_url=os.getenv("TONY_GITHUB_API_URL", "https://api.github.com").strip(),
        timeout_seconds=float(os.getenv("TONY_GITHUB_TIMEOUT_SECONDS", "10")),
        max_pages=int(os.getenv("TONY_GITHUB_MAX_PAGES", "20")),
    )
    workspace_runtime = WorkspaceRuntimeManager(
        runtime_root, repository_root
    ).runtime(workspace_id)
    archive = ExecutiveBriefArchive(
        workspace_runtime.artifact_catalog,
        workspace_runtime.event_log,
        workspace_id=workspace_id,
    )
    service = GitHubWorkService(config, GitHubRESTClient(config))

    def load() -> GitHubWorkSnapshot:
        prior = archive.latest_github_snapshot(repository=config.repository)
        if prior is None:
            return service.build()
        previous, artifact_id = prior
        return service.build(
            previous=previous,
            baseline_artifact_id=artifact_id,
        )

    return load, archive


def build_diagnostics_runner(
    gateway_health_endpoint: str,
    command_service: TonyCommandService,
    object_loader: ObjectLoader,
) -> DiagnosticsRunner:
    doctor = ServiceDoctor(timeout_seconds=float(os.getenv("NARRATIIVE_DOCTOR_TIMEOUT_SECONDS", "3")))

    def run() -> dict[str, Any]:
        gateway = doctor.check("runtime-gateway", gateway_health_endpoint)
        checks: list[dict[str, Any]] = [
            {
                "name": "tony-http-bridge",
                "healthy": True,
                "status_code": 200,
                "error": "",
            },
            ServiceDoctor._as_dict(gateway),
        ]
        try:
            objects = list(object_loader())
            repository = command_service.execute("/health", objects)
            repository_healthy = repository.status == "healthy"
            checks.append(
                {
                    "name": "repository-state",
                    "healthy": repository_healthy,
                    "status_code": None,
                    "error": "" if repository_healthy else repository.message,
                    "objects_validated": repository.data.get("validation", {}).get("objects_validated", 0),
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": "repository-state",
                    "healthy": False,
                    "status_code": None,
                    "error": f"repository check failed: {exc}",
                }
            )
        return {"ok": all(check["healthy"] for check in checks), "checks": checks}

    return run


def build_app() -> TonyHTTPBridge:
    api_key = os.getenv("NARRATIIVE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("NARRATIIVE_API_KEY is required")
    endpoint = os.getenv("NARRATIIVE_GATEWAY_ENDPOINT", "http://127.0.0.1:8787/")
    gateway_health_endpoint = os.getenv("NARRATIIVE_GATEWAY_HEALTH_ENDPOINT", "http://127.0.0.1:8787/health")
    bridge_token = os.getenv("TONY_BRIDGE_TOKEN", "")
    gateway_timeout = float(os.getenv("TONY_GATEWAY_TIMEOUT_SECONDS", "25"))
    adapter = TonyOrchestrationAdapter(HttpGatewayTransport(endpoint, api_key, timeout_seconds=gateway_timeout))

    schema_path = Path(os.getenv(
        "TONY_GROWTH_OBJECT_SCHEMA",
        str(REPOSITORY_ROOT / "schemas" / "shared" / "growth-object.schema.json"),
    ))
    objects_root = Path(os.getenv("TONY_OBJECTS_ROOT", str(REPOSITORY_ROOT / "clients")))
    runtime_root = Path(os.getenv("NARRATIIVE_RUNTIME_ROOT", ".runtime")).resolve()
    validator = GrowthObjectValidator.from_path(schema_path)
    progress_engine = RepositoryProgressEngine(validator)
    object_loader = lambda: load_growth_objects(objects_root)
    github_work_loader, brief_archive = build_github_components(
        runtime_root=runtime_root,
        repository_root=REPOSITORY_ROOT,
    )
    mission_control_loader = build_mission_control_loader(
        progress_engine,
        object_loader,
        gateway_health_endpoint,
        github_work_loader,
    )
    command_service = TonyCommandService(
        progress_engine,
        mission_control_loader=mission_control_loader,
        github_configured=github_work_loader is not None,
    )
    return TonyHTTPBridge(
        adapter,
        bridge_token,
        command_service=command_service,
        object_loader=object_loader,
        diagnostics_runner=build_diagnostics_runner(
            gateway_health_endpoint, command_service, object_loader
        ),
        brief_archive=brief_archive,
    )


def main() -> None:
    host = os.getenv("TONY_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("TONY_BRIDGE_PORT", "8790"))
    with make_server(host, port, build_app()) as server:
        print(f"Tony bridge listening on http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
