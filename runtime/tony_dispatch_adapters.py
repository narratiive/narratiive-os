from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Mapping
from urllib import request

from runtime.github_work import GitHubConfig, GitHubRESTClient, GitHubWorkError
from runtime.inbound_leads import CANONICAL_NOTION_LEADS_DATA_SOURCE_ID
from runtime.native_business_adapters import (
    FirefliesDispatcher,
    GmailDispatcher,
    GoogleCalendarDispatcher,
    GoogleDriveDispatcher,
    GoogleOAuthConfig,
    NotionWorkflowProjectionDispatcher,
)
from runtime.tony_claude_api_dispatcher import build_claude_api_dispatcher


SUPPORTED_DISPATCH_WORKERS = (
    "Claude",
    "Fireflies",
    "Gmail",
    "Google Calendar",
    "Google Drive",
    "GitHub",
    "Notion",
    "Replit",
    "n8n",
)


def _env_key(worker: str) -> str:
    return worker.upper().replace(" ", "_").replace("-", "_")


def build_http_dispatchers(
    environ: Mapping[str, str] | None = None,
) -> dict[str, callable]:
    """Build explicitly configured live dispatch handlers.

    HTTP worker endpoints remain the default integration surface. Claude can also be
    explicitly enabled as a direct Anthropic Messages API preparation worker with
    TONY_DISPATCH_CLAUDE_MODE=anthropic_api. Nothing is inferred or enabled merely
    because credentials exist, so Tony remains fail-closed by default.
    """
    env = os.environ if environ is None else environ
    handlers: dict[str, callable] = {}
    for worker in SUPPORTED_DISPATCH_WORKERS:
        key = _env_key(worker)
        url = str(env.get(f"TONY_DISPATCH_{key}_URL", "")).strip()
        if not url:
            continue
        token = str(env.get(f"TONY_DISPATCH_{key}_TOKEN", "")).strip()
        handlers[worker] = _http_handler(url, token)

    claude_mode = str(env.get("TONY_DISPATCH_CLAUDE_MODE", "")).strip().casefold()
    if "Claude" not in handlers and claude_mode == "anthropic_api":
        handlers["Claude"] = build_claude_api_dispatcher(env)

    google_oauth = GoogleOAuthConfig(
        access_token=str(env.get("TONY_GOOGLE_ACCESS_TOKEN", "")).strip(),
        client_id=str(env.get("TONY_GOOGLE_CLIENT_ID", "")).strip(),
        client_secret=str(env.get("TONY_GOOGLE_CLIENT_SECRET", "")).strip(),
        refresh_token=str(env.get("TONY_GOOGLE_REFRESH_TOKEN", "")).strip(),
    )
    native_google = {
        "Gmail": ("google_api", GmailDispatcher),
        "Google Calendar": ("google_api", GoogleCalendarDispatcher),
        "Google Drive": ("google_api", GoogleDriveDispatcher),
    }
    for worker, (mode, factory) in native_google.items():
        if worker in handlers:
            continue
        key = _env_key(worker)
        if (
            str(env.get(f"TONY_DISPATCH_{key}_MODE", "")).strip().casefold() == mode
            and google_oauth.configured
        ):
            if worker == "Google Calendar":
                handlers[worker] = factory(
                    google_oauth,
                    calendar_id=str(env.get("TONY_GOOGLE_CALENDAR_ID", "primary")).strip() or "primary",
                    timezone_name=str(env.get("TONY_GOOGLE_CALENDAR_TIMEZONE", "Europe/London")).strip() or "Europe/London",
                )
            else:
                if worker == "Google Drive":
                    upload_root = str(env.get("TONY_WORKFLOW_RUNTIME_ROOT") or "").strip()
                    handlers[worker] = factory(
                        google_oauth,
                        allowed_upload_root=Path(upload_root).expanduser() if upload_root else None,
                    )
                else:
                    handlers[worker] = factory(google_oauth)

    if "Notion" not in handlers and str(env.get("TONY_DISPATCH_NOTION_MODE", "")).strip().casefold() == "notion_api":
        token = next(
            (
                str(env.get(name, "")).strip()
                for name in ("NARRATIIVE_NOTION_TOKEN", "NOTION_API_TOKEN", "NOTION_API_KEY", "NOTION_TOKEN")
                if str(env.get(name, "")).strip()
            ),
            "",
        )
        if token:
            handlers["Notion"] = NotionWorkflowProjectionDispatcher(
                token,
                str(env.get("NARRATIIVE_NOTION_LEADS_DATA_SOURCE_ID", "")).strip()
                or CANONICAL_NOTION_LEADS_DATA_SOURCE_ID,
            )

    if "Fireflies" not in handlers and str(env.get("TONY_DISPATCH_FIREFLIES_MODE", "")).strip().casefold() == "fireflies_api":
        api_key = str(env.get("TONY_FIREFLIES_API_KEY") or env.get("FIREFLIES_API_KEY") or "").strip()
        if api_key:
            handlers["Fireflies"] = FirefliesDispatcher(api_key)

    if "GitHub" not in handlers:
        repository = str(env.get("TONY_GITHUB_REPOSITORY", "")).strip()
        workspace_id = str(env.get("TONY_GITHUB_WORKSPACE_ID", "")).strip()
        matt_login = str(env.get("TONY_GITHUB_MATT_LOGIN", "")).strip()
        token = str(env.get("TONY_GITHUB_TOKEN", "")).strip()
        if all((repository, workspace_id, matt_login, token)):
            try:
                config = GitHubConfig(
                    repository=repository,
                    workspace_id=workspace_id,
                    matt_login=matt_login,
                    api_url=str(env.get("TONY_GITHUB_API_URL", "https://api.github.com")).strip(),
                    timeout_seconds=float(env.get("TONY_GITHUB_TIMEOUT_SECONDS", "10")),
                    max_pages=min(int(env.get("TONY_GITHUB_MAX_PAGES", "20")), 20),
                )
            except (GitHubWorkError, ValueError):
                pass
            else:
                handlers["GitHub"] = _GitHubReadDispatcher(
                    config,
                    GitHubRESTClient(config, token_loader=lambda: token),
                )

    if "n8n" not in handlers and str(env.get("TONY_DISPATCH_N8N_MODE", "")).strip().casefold() == "local_sqlite":
        database_path = Path(str(env.get("TONY_N8N_DATABASE_PATH", Path.home() / ".n8n" / "database.sqlite"))).expanduser()
        if database_path.is_file():
            handlers["n8n"] = _N8NReadDispatcher(database_path)
    return handlers


class _GitHubReadDispatcher:
    def __init__(self, config: GitHubConfig, client: GitHubRESTClient) -> None:
        self.config = config
        self.client = client

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        if str(contract.get("execution_mode") or "").strip() != "autonomous_read":
            raise GitHubWorkError("GitHub adapter operation is not an authorised read")
        target = contract.get("target") if isinstance(contract.get("target"), Mapping) else {}
        try:
            max_results = min(max(int(target.get("max_results") or 10), 1), 20)
        except (TypeError, ValueError):
            max_results = 10
        resource = str(target.get("resource") or "overview").strip().casefold()
        pull_number = target.get("pull_number")
        if pull_number is not None:
            try:
                number = int(pull_number)
            except (TypeError, ValueError) as exc:
                raise GitHubWorkError("GitHub pull request number is invalid") from exc
            pull = self.client.get_pull_request(number)
            checks = self.client.list_check_runs(str(pull.get("head", {}).get("sha") or ""))
            return {
                "verified": True,
                "read_only": True,
                "mutation_count": 0,
                "source_id": f"github:{self.config.repository}:pull:{number}",
                "record_id": str(number),
                "pull_request": self._normalise(pull),
                "checks": [self._normalise(item) for item in checks[:max_results]],
                "summary": "GitHub pull request state was read without mutation.",
            }
        pulls = [] if resource == "issues" else self.client.list_open_pull_requests()[:max_results]
        issues = [] if resource == "pulls" else [
            item for item in self.client.list_open_issues() if "pull_request" not in item
        ][:max_results]
        return {
            "verified": True,
            "read_only": True,
            "mutation_count": 0,
            "source_id": f"github:{self.config.repository}",
            "repository": self.config.repository,
            "pull_requests": [self._normalise(item) for item in pulls],
            "issues": [self._normalise(item) for item in issues],
            "record_ids": [str(item.get("number")) for item in [*pulls, *issues] if item.get("number")],
            "summary": "GitHub open work was read without mutation.",
        }

    @staticmethod
    def _normalise(item: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: item.get(key)
            for key in ("id", "number", "name", "title", "state", "status", "conclusion", "html_url", "updated_at")
            if item.get(key) not in (None, "")
        }


class _N8NReadDispatcher:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        if str(contract.get("execution_mode") or "").strip() != "autonomous_read":
            raise RuntimeError("n8n adapter operation is not an authorised read")
        target = contract.get("target") if isinstance(contract.get("target"), Mapping) else {}
        try:
            max_results = min(max(int(target.get("max_results") or 20), 1), 50)
        except (TypeError, ValueError):
            max_results = 20
        query_text = str(target.get("query") or "").strip()
        statement = (
            'SELECT id, name, active, "createdAt", "updatedAt", "isArchived", "versionCounter" '
            'FROM workflow_entity WHERE "isArchived" = 0'
        )
        parameters: list[Any] = []
        if query_text:
            statement += " AND name LIKE ? ESCAPE '\\'"
            escaped = query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parameters.append(f"%{escaped}%")
        statement += ' ORDER BY "updatedAt" DESC LIMIT ?'
        parameters.append(max_results)
        connection = sqlite3.connect(f"file:{self.database_path}?mode=ro", uri=True)
        try:
            rows = connection.execute(statement, parameters).fetchall()
        finally:
            connection.close()
        workflows = [
            {
                "workflow_id": str(row[0]),
                "name": str(row[1]),
                "active": bool(row[2]),
                "created_at": str(row[3]),
                "updated_at": str(row[4]),
                "archived": bool(row[5]),
                "version": int(row[6]),
            }
            for row in rows
        ]
        return {
            "verified": True,
            "read_only": True,
            "mutation_count": 0,
            "source_id": "n8n:local:workflows",
            "workflows": workflows,
            "record_ids": [item["workflow_id"] for item in workflows],
            "result_count": len(workflows),
            "summary": "n8n workflow metadata was read from the local database without mutation.",
        }


def _http_handler(url: str, token: str):
    def dispatch(contract: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"dispatch": contract}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = request.Request(url, data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=30) as response:  # nosec B310 - endpoint is explicit operator config
            raw = response.read().decode("utf-8")
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            raise RuntimeError("dispatcher response must be a JSON object")
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else payload
        if not evidence:
            raise RuntimeError("dispatcher returned no structured evidence")
        return evidence

    return dispatch
