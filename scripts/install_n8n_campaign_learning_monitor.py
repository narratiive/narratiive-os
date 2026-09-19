#!/usr/bin/env python3
"""Install the read-only hourly Campaign Learning monitor in local n8n."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKFLOW_ID = "narratiive-learning-monitor"
WORKFLOW_NAME = "Narratiive - Hourly Campaign Learning Monitor"
REFERENCE_WORKFLOW_ID = "s7TvzzAsJRKLRDU7"


def workflow_definition() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nodes = [
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {
                            "field": "hours",
                            "hoursInterval": 1,
                        }
                    ]
                }
            },
            "id": "narratiive-hourly-learning-trigger",
            "name": "Hourly Campaign Learning",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [320, 300],
        },
        {
            "parameters": {
                "method": "POST",
                "url": "http://127.0.0.1:8790/workflow/control",
                "sendHeaders": True,
                "specifyHeaders": "json",
                "jsonHeaders": "={{ JSON.stringify({ Authorization: 'Bearer ' + $env.TONY_BRIDGE_TOKEN }) }}",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ { operation: 'campaign-learning-queue' } }}",
                "options": {
                    "response": {"response": {"fullResponse": True}},
                    "timeout": 30000,
                },
            },
            "id": "narratiive-learning-monitor-request",
            "name": "Check Campaign Learning Queue",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.4,
            "position": [560, 300],
        },
    ]
    connections = {
        "Hourly Campaign Learning": {
            "main": [[{"node": "Check Campaign Learning Queue", "type": "main", "index": 0}]]
        }
    }
    return nodes, connections


def install(database: Path, *, restart: bool) -> dict[str, Any]:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"n8n database not found: {database}")

    backup = database.with_name(
        f"{database.name}.before-learning-monitor-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    shutil.copy2(database, backup)

    nodes, connections = workflow_definition()
    encoded_nodes = json.dumps(nodes, separators=(",", ":"))
    encoded_connections = json.dumps(connections, separators=(",", ":"))
    settings = json.dumps(
        {
            "executionOrder": "v1",
            "saveDataErrorExecution": "all",
            "saveDataSuccessExecution": "all",
            "saveManualExecutions": True,
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
        project_id = str(project[0])
        existing = connection.execute(
            "SELECT id FROM workflow_entity WHERE id = ? OR name = ?",
            (WORKFLOW_ID, WORKFLOW_NAME),
        ).fetchall()
        if any(str(row[0]) != WORKFLOW_ID for row in existing):
            raise RuntimeError("a different workflow already uses the Campaign Learning monitor name")

        with connection:
            connection.execute(
                "INSERT INTO workflow_history "
                "(versionId, workflowId, authors, createdAt, updatedAt, nodes, connections, name, autosaved, description) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (
                    version_id,
                    WORKFLOW_ID,
                    "Narratiive OS",
                    now,
                    now,
                    encoded_nodes,
                    encoded_connections,
                    WORKFLOW_NAME,
                    "Hourly read-only check of the Campaign Learning queue. No media mutation or Notion projection.",
                ),
            )
            if existing:
                connection.execute(
                    "UPDATE workflow_entity SET active = 1, nodes = ?, connections = ?, settings = ?, "
                    "versionId = ?, activeVersionId = ?, triggerCount = 1, updatedAt = ?, "
                    "versionCounter = versionCounter + 1, isArchived = 0, description = ? WHERE id = ?",
                    (
                        encoded_nodes,
                        encoded_connections,
                        settings,
                        version_id,
                        version_id,
                        now,
                        "Hourly read-only check of the Campaign Learning queue. No media mutation or Notion projection.",
                        WORKFLOW_ID,
                    ),
                )
            else:
                connection.execute(
                    "INSERT INTO workflow_entity "
                    "(id, name, active, nodes, connections, settings, staticData, pinData, versionId, "
                    "triggerCount, meta, parentFolderId, createdAt, updatedAt, isArchived, versionCounter, "
                    "description, activeVersionId) "
                    "VALUES (?, ?, 1, ?, ?, ?, NULL, NULL, ?, 1, NULL, NULL, ?, ?, 0, 1, ?, ?)",
                    (
                        WORKFLOW_ID,
                        WORKFLOW_NAME,
                        encoded_nodes,
                        encoded_connections,
                        settings,
                        version_id,
                        now,
                        now,
                        "Hourly read-only check of the Campaign Learning queue. No media mutation or Notion projection.",
                        version_id,
                    ),
                )
                connection.execute(
                    "INSERT INTO shared_workflow (workflowId, projectId, role, createdAt, updatedAt) "
                    "VALUES (?, ?, 'workflow:owner', ?, ?)",
                    (WORKFLOW_ID, project_id, now, now),
                )
    finally:
        connection.close()

    if restart:
        subprocess.run(
            ("launchctl", "kickstart", "-k", f"gui/{__import__('os').getuid()}/com.narratiive.n8n"),
            check=True,
        )
    return {
        "status": "installed",
        "workflow_id": WORKFLOW_ID,
        "workflow_name": WORKFLOW_NAME,
        "version_id": version_id,
        "backup": str(backup),
        "restarted": restart,
        "read_only": True,
        "schedule": "hourly",
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
