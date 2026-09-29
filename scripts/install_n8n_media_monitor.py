#!/usr/bin/env python3
"""Install daily and weekly read-only Media Control monitors in local n8n."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKFLOW_ID = "narratiive-media-monitor"
WORKFLOW_NAME = "Narratiive - Read-only Media Monitor"
REFERENCE_WORKFLOW_ID = "s7TvzzAsJRKLRDU7"


def workflow_definition() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nodes = [
        _schedule("daily", "15 7 * * *", [320, 220]),
        _request("daily", "'media-daily-' + $now.setZone('Europe/London').toFormat('yyyy-LL-dd')", [570, 220]),
        _schedule("weekly", "30 7 * * 1", [320, 420]),
        _request("weekly", "'media-weekly-' + $now.setZone('Europe/London').toFormat(\"kkkk-'W'WW\")", [570, 420]),
    ]
    return nodes, {
        "Daily Media Monitor": {"main": [[{"node": "Build Daily Media Report", "type": "main", "index": 0}]]},
        "Weekly Media Monitor": {"main": [[{"node": "Build Weekly Media Report", "type": "main", "index": 0}]]},
    }


def _schedule(cadence: str, expression: str, position: list[int]) -> dict[str, Any]:
    label = cadence.title()
    return {
        "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": expression}]}},
        "id": f"narratiive-{cadence}-media-trigger",
        "name": f"{label} Media Monitor",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": position,
    }


def _request(cadence: str, request_id: str, position: list[int]) -> dict[str, Any]:
    label = cadence.title()
    return {
        "parameters": {
            "method": "POST",
            "url": "http://127.0.0.1:8790/media/monitor",
            "sendHeaders": True,
            "specifyHeaders": "json",
            "jsonHeaders": "={{ JSON.stringify({ Authorization: 'Bearer ' + $env.TONY_BRIDGE_TOKEN }) }}",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": f"={{{{ {{ cadence: '{cadence}', request_id: {request_id} }} }}}}",
            "options": {"response": {"response": {"fullResponse": True}}, "timeout": 30000},
        },
        "id": f"narratiive-{cadence}-media-request",
        "name": f"Build {label} Media Report",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.4,
        "position": position,
    }


def install(database: Path, *, restart: bool) -> dict[str, Any]:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"n8n database not found: {database}")
    backup = database.with_name(
        f"{database.name}.before-media-monitor-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
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
    description = "Daily and weekly evidence-backed media reports. Read-only; no platform mutation or publication."
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
            raise RuntimeError("a different workflow already uses the Media Monitor name")
        with connection:
            connection.execute(
                "INSERT INTO workflow_history (versionId, workflowId, authors, createdAt, updatedAt, nodes, connections, name, autosaved, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (version_id, WORKFLOW_ID, "Narratiive OS", now, now, encoded_nodes, encoded_connections, WORKFLOW_NAME, description),
            )
            if existing:
                connection.execute(
                    "UPDATE workflow_entity SET active = 1, nodes = ?, connections = ?, settings = ?, versionId = ?, activeVersionId = ?, triggerCount = 2, updatedAt = ?, versionCounter = versionCounter + 1, isArchived = 0, description = ? WHERE id = ?",
                    (encoded_nodes, encoded_connections, settings, version_id, version_id, now, description, WORKFLOW_ID),
                )
            else:
                connection.execute(
                    "INSERT INTO workflow_entity (id, name, active, nodes, connections, settings, staticData, pinData, versionId, triggerCount, meta, parentFolderId, createdAt, updatedAt, isArchived, versionCounter, description, activeVersionId) VALUES (?, ?, 1, ?, ?, ?, NULL, NULL, ?, 2, NULL, NULL, ?, ?, 0, 1, ?, ?)",
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
        "backup": str(backup),
        "restarted": restart,
        "read_only": True,
        "schedules": {"daily": "07:15 Europe/London", "weekly": "Monday 07:30 Europe/London"},
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
