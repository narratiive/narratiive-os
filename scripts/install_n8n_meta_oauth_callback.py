#!/usr/bin/env python3
"""Install the credential-safe Meta advertising OAuth callback in local n8n."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from runtime.meta_oauth import META_REDIRECT_URI


WORKFLOW_ID = "narratiive-meta-oauth-callback"
WORKFLOW_NAME = "Narratiive - Meta Advertising OAuth Callback"
REFERENCE_WORKFLOW_ID = "s7TvzzAsJRKLRDU7"
WEBHOOK_PATH = "meta-media-oauth-callback"


def workflow_definition() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nodes = [
        {
            "parameters": {
                "httpMethod": "GET",
                "path": WEBHOOK_PATH,
                "responseMode": "responseNode",
                "options": {},
            },
            "id": "narratiive-meta-oauth-webhook",
            "name": "Meta OAuth Callback",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2.1,
            "position": [320, 300],
            "webhookId": "269a4dc0-48c6-4b8e-890c-d4685a35ac62",
        },
        {
            "parameters": {
                "method": "POST",
                "url": "http://127.0.0.1:8790/oauth/meta/callback",
                "sendHeaders": True,
                "specifyHeaders": "json",
                "jsonHeaders": "={{ JSON.stringify({ Authorization: 'Bearer ' + $env.TONY_BRIDGE_TOKEN }) }}",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ { state: $json.query.state, code: $json.query.code, error: $json.query.error } }}",
                "options": {
                    "response": {"response": {"fullResponse": True, "neverError": True}},
                    "timeout": 30000,
                },
            },
            "id": "narratiive-meta-oauth-exchange",
            "name": "Exchange with Tony",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.4,
            "position": [560, 300],
        },
        {
            "parameters": {
                "respondWith": "json",
                "responseBody": "={{ $json.body }}",
                "options": {"responseCode": "={{ $json.statusCode }}"},
            },
            "id": "narratiive-meta-oauth-response",
            "name": "Safe OAuth Response",
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1.4,
            "position": [800, 300],
        },
    ]
    connections = {
        "Meta OAuth Callback": {"main": [[{"node": "Exchange with Tony", "type": "main", "index": 0}]]},
        "Exchange with Tony": {"main": [[{"node": "Safe OAuth Response", "type": "main", "index": 0}]]},
    }
    return nodes, connections


def install(database: Path, *, restart: bool) -> dict[str, Any]:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"n8n database not found: {database}")
    backup = database.with_name(
        f"{database.name}.before-meta-oauth-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    shutil.copy2(database, backup)
    nodes, connections = workflow_definition()
    encoded_nodes = json.dumps(nodes, separators=(",", ":"))
    encoded_connections = json.dumps(connections, separators=(",", ":"))
    settings = json.dumps(
        {
            "executionOrder": "v1",
            "saveDataErrorExecution": "none",
            "saveDataSuccessExecution": "none",
            "saveManualExecutions": False,
            "timezone": "Europe/London",
        },
        separators=(",", ":"),
    )
    version_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    connection = sqlite3.connect(database)
    try:
        project = connection.execute(
            "SELECT projectId FROM shared_workflow WHERE workflowId = ? ORDER BY createdAt LIMIT 1",
            (REFERENCE_WORKFLOW_ID,),
        ).fetchone()
        if project is None:
            raise RuntimeError("canonical n8n project ownership could not be resolved")
        existing = connection.execute(
            "SELECT id FROM workflow_entity WHERE id = ? OR name = ?", (WORKFLOW_ID, WORKFLOW_NAME)
        ).fetchall()
        if any(str(row[0]) != WORKFLOW_ID for row in existing):
            raise RuntimeError("a different workflow already uses the Meta OAuth callback name")
        description = "Read-only Meta advertising OAuth callback. Execution payloads are never persisted."
        with connection:
            connection.execute(
                "INSERT INTO workflow_history (versionId, workflowId, authors, createdAt, updatedAt, nodes, connections, name, autosaved, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (version_id, WORKFLOW_ID, "Narratiive OS", now, now, encoded_nodes, encoded_connections, WORKFLOW_NAME, description),
            )
            if existing:
                connection.execute(
                    "UPDATE workflow_entity SET active = 1, nodes = ?, connections = ?, settings = ?, versionId = ?, activeVersionId = ?, triggerCount = 1, updatedAt = ?, versionCounter = versionCounter + 1, isArchived = 0, description = ? WHERE id = ?",
                    (encoded_nodes, encoded_connections, settings, version_id, version_id, now, description, WORKFLOW_ID),
                )
            else:
                connection.execute(
                    "INSERT INTO workflow_entity (id, name, active, nodes, connections, settings, staticData, pinData, versionId, triggerCount, meta, parentFolderId, createdAt, updatedAt, isArchived, versionCounter, description, activeVersionId) VALUES (?, ?, 1, ?, ?, ?, NULL, NULL, ?, 1, NULL, NULL, ?, ?, 0, 1, ?, ?)",
                    (WORKFLOW_ID, WORKFLOW_NAME, encoded_nodes, encoded_connections, settings, version_id, now, now, description, version_id),
                )
                connection.execute(
                    "INSERT INTO shared_workflow (workflowId, projectId, role, createdAt, updatedAt) VALUES (?, ?, 'workflow:owner', ?, ?)",
                    (WORKFLOW_ID, str(project[0]), now, now),
                )
    finally:
        connection.close()
    if restart:
        subprocess.run(("launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.narratiive.n8n"), check=True)
    return {
        "status": "installed",
        "workflow_id": WORKFLOW_ID,
        "redirect_url": META_REDIRECT_URI,
        "backup": str(backup),
        "restarted": restart,
        "read_only": True,
        "execution_data_persisted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path.home() / ".n8n" / "database.sqlite")
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(args.database, restart=not args.no_restart), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
