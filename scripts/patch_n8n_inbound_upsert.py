#!/usr/bin/env python3
"""Make the live unified inbound workflow idempotent before Notion creation."""

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


WORKFLOW_ID = "l6TysPR86l5VAoXc"
WORKFLOW_NAME = "Narratiive - Unified Inbound Lead Intake + Tony Sync"
NOTION_DATABASE_ID = "34b0c9cfa8f280aa9862f05f4a65c676"
NOTION_CREDENTIAL_NAME = "Notion account"

NORMALISE = "Normalise Diagnostic Payload1"
QUERY = "Find Existing Submission"
BRANCH = "Submission Already Exists?"
EXISTING = "Use Existing Notion Lead"
CREATE = "Create Notion Lead1"
MERGE = "Select Canonical Notion Lead"
SYNC = "Sync Lead to Tony"
PREPARE = "Prepare Response1"


def _node(nodes: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [node for node in nodes if node.get("name") == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one n8n node named {name!r}")
    return matches[0]


def _connection(node: str, *, index: int = 0) -> dict[str, Any]:
    return {"node": node, "type": "main", "index": index}


def _stable_id_javascript() -> str:
    return """
function stableHash(value) {
  let hash = 2166136261;
  const text = JSON.stringify(value);
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

const suppliedLeadId =
  body.lead_id ||
  body.leadId ||
  body.id ||
  (tallyData && (tallyData.responseId || tallyData.submissionId)) ||
  '';

const sourceSubmissionId = String(suppliedLeadId || `inbound-${stableHash(body)}`);

const requestedSource = String(body.source || '').trim().toLowerCase();
const sourceType = requestedSource === 'email'
  ? 'Email'
  : isTally
    ? 'Tally'
    : 'Growth Diagnostic';
""".strip()


def _patch_normaliser(node: dict[str, Any]) -> None:
    code = str(node.get("parameters", {}).get("jsCode") or "")
    if "const sourceSubmissionId" not in code:
        anchor = "const isTally =\n  Boolean(tallyData) ||\n  String(body.source || '').toLowerCase() === 'tally';"
        if anchor not in code:
            raise ValueError("normaliser contract changed; source-id anchor is missing")
        code = code.replace(anchor, f"{anchor}\n\n{_stable_id_javascript()}", 1)
    elif "const sourceType" not in code:
        source_anchor = "const sourceSubmissionId = String(suppliedLeadId || `inbound-${stableHash(body)}`);"
        if source_anchor not in code:
            raise ValueError("normaliser source-submission contract changed")
        source_type = """

const requestedSource = String(body.source || '').trim().toLowerCase();
const sourceType = requestedSource === 'email'
  ? 'Email'
  : isTally
    ? 'Tally'
    : 'Growth Diagnostic';
""".rstrip()
        code = code.replace(source_anchor, f"{source_anchor}{source_type}", 1)
    old_expression = """  lead_id:
    body.lead_id ||
    body.leadId ||
    body.id ||
    (tallyData && (tallyData.responseId || tallyData.submissionId)) ||
    '',"""
    if old_expression in code:
        code = code.replace(old_expression, "  lead_id: sourceSubmissionId,", 1)
    elif "lead_id: sourceSubmissionId" not in code:
        raise ValueError("normaliser lead-id expression is not recognised")
    code = code.replace(
        "source: isTally ? 'Tally' : 'Growth Diagnostic',",
        "source: sourceType,",
    )
    if "inbound_message_id:" not in code:
        code = code.replace(
            "  lead_id: sourceSubmissionId,",
            "  lead_id: sourceSubmissionId,\n\n  inbound_message_id: body.inbound_message_id || body.message_id || '',",
            1,
        )
    node["parameters"]["jsCode"] = code


def _notion_credentials(credential_id: str) -> dict[str, Any]:
    return {"notionApi": {"id": credential_id, "name": NOTION_CREDENTIAL_NAME}}


def _secure_notion_node(node: dict[str, Any], credential_id: str) -> None:
    parameters = node.setdefault("parameters", {})
    parameters["authentication"] = "predefinedCredentialType"
    parameters["nodeCredentialType"] = "notionApi"
    headers = parameters.get("headerParameters", {}).get("parameters", [])
    parameters["headerParameters"] = {
        "parameters": [
            header
            for header in headers
            if str(header.get("name") or "").strip().casefold() != "authorization"
        ]
    }
    node["credentials"] = _notion_credentials(credential_id)


def _patch_create_node(node: dict[str, Any], credential_id: str) -> None:
    _secure_notion_node(node, credential_id)
    body = str(node.get("parameters", {}).get("jsonBody") or "")
    if "Source Submission ID" not in body:
        anchor = "  properties: {\n"
        if anchor not in body:
            raise ValueError("Notion create payload contract changed")
        addition = """  properties: {
    "Source Submission ID": {
      rich_text: [{ text: { content: $('Normalise Diagnostic Payload1').first().json.lead_id } }]
    },
"""
        body = body.replace(anchor, addition, 1)
    if "Inbound Message ID" not in body:
        body = body.replace(
            '    "Source Submission ID": {\n      rich_text: [{ text: { content: $(\'Normalise Diagnostic Payload1\').first().json.lead_id } }]\n    },',
            '    "Source Submission ID": {\n      rich_text: [{ text: { content: $(\'Normalise Diagnostic Payload1\').first().json.lead_id } }]\n    },\n    "Inbound Message ID": {\n      rich_text: [{ text: { content: $(\'Normalise Diagnostic Payload1\').first().json.inbound_message_id || "" } }]\n    },',
            1,
        )
    body = body.replace("$json.", "$('Normalise Diagnostic Payload1').first().json.")
    body = body.replace(
        "$('Normalise Diagnostic Payload1').first().json.source === \"Tally\" ? \"Tally\" : \"Growth Diagnostic\"",
        "$('Normalise Diagnostic Payload1').first().json.source",
    )
    body = body.replace(
        'name: "New Diagnostic"',
        'name: $(\'Normalise Diagnostic Payload1\').first().json.source === "Email" ? "Email Enquiry" : "New Diagnostic"',
    )
    body = body.replace(
        "$('Normalise Diagnostic Payload1').first().json.source === \"Tally\"\n                ? \"Tally inbound enquiry.\"\n                : \"Growth Diagnostic completed.\"",
        "$('Normalise Diagnostic Payload1').first().json.source === \"Email\"\n                ? \"Person-to-person email enquiry received. No reply has been sent.\"\n                : $('Normalise Diagnostic Payload1').first().json.source === \"Tally\"\n                  ? \"Tally inbound enquiry.\"\n                  : \"Growth Diagnostic completed.\"",
    )
    node["parameters"]["jsonBody"] = body


def patch_workflow(
    nodes: list[dict[str, Any]],
    connections: dict[str, Any],
    *,
    notion_credential_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nodes = json.loads(json.dumps(nodes))
    connections = json.loads(json.dumps(connections))
    _patch_normaliser(_node(nodes, NORMALISE))
    _patch_create_node(_node(nodes, CREATE), notion_credential_id)

    retained = [node for node in nodes if node.get("name") not in {QUERY, BRANCH, EXISTING, MERGE}]
    query = {
        "id": "narratiive-inbound-find-existing",
        "name": QUERY,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [560, 180],
        "parameters": {
            "method": "POST",
            "url": f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "notionApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Notion-Version", "value": "2022-06-28"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ ({ filter: { property: 'Source Submission ID', rich_text: { equals: $('Normalise Diagnostic Payload1').first().json.lead_id } }, page_size: 1 }) }}",
            "options": {"response": {"response": {"fullResponse": True}}, "timeout": 30000},
        },
        "credentials": _notion_credentials(notion_credential_id),
    }
    branch = {
        "id": "narratiive-inbound-existing-branch",
        "name": BRANCH,
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [780, 180],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [
                    {
                        "id": "narratiive-existing-result",
                        "leftValue": "={{ ($json.body?.results || $json.results || []).length > 0 }}",
                        "rightValue": "",
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
    }
    existing = {
        "id": "narratiive-inbound-use-existing",
        "name": EXISTING,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1020, 80],
        "parameters": {
            "jsCode": "const response = $json.body || $json;\nconst existing = Array.isArray(response.results) ? response.results[0] : null;\nif (!existing) throw new Error('idempotency branch selected without an existing Notion lead');\nreturn [{ json: { body: existing, statusCode: 200, idempotent_replay: true } }];"
        },
    }
    merge = {
        "id": "narratiive-inbound-select-canonical",
        "name": MERGE,
        "type": "n8n-nodes-base.merge",
        "typeVersion": 3.2,
        "position": [1260, 180],
        "parameters": {"mode": "append"},
    }
    nodes = [*retained, query, branch, existing, merge]

    prepare = _node(nodes, PREPARE)
    prepare_code = str(prepare.get("parameters", {}).get("jsCode") or "")
    prepare["parameters"]["jsCode"] = prepare_code.replace(
        "$('Create Notion Lead1').first().json",
        "$('Select Canonical Notion Lead').first().json",
    )

    connections[NORMALISE] = {"main": [[_connection(QUERY)]]}
    connections[QUERY] = {"main": [[_connection(BRANCH)]]}
    connections[BRANCH] = {
        "main": [[_connection(EXISTING)], [_connection(CREATE)]],
    }
    connections[EXISTING] = {"main": [[_connection(MERGE, index=0)]]}
    connections[CREATE] = {"main": [[_connection(MERGE, index=1)]]}
    connections[MERGE] = {"main": [[_connection(SYNC)]]}
    return nodes, connections


def install(database: Path, *, restart: bool) -> dict[str, Any]:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"n8n database not found: {database}")
    backup = database.with_name(f"{database.name}.before-inbound-upsert-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    shutil.copy2(database, backup)

    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT name, nodes, connections FROM workflow_entity WHERE id = ?",
            (WORKFLOW_ID,),
        ).fetchone()
        if row is None or row[0] != WORKFLOW_NAME:
            raise RuntimeError("canonical unified inbound workflow was not found")
        credential = connection.execute(
            "SELECT id FROM credentials_entity WHERE name = ? AND type = 'notionApi'",
            (NOTION_CREDENTIAL_NAME,),
        ).fetchone()
        if credential is None:
            raise RuntimeError("canonical n8n Notion credential was not found")
        nodes, connections = patch_workflow(
            json.loads(row[1]),
            json.loads(row[2]),
            notion_credential_id=str(credential[0]),
        )
        version_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        encoded_nodes = json.dumps(nodes, separators=(",", ":"))
        encoded_connections = json.dumps(connections, separators=(",", ":"))
        with connection:
            connection.execute(
                "INSERT INTO workflow_history (versionId, workflowId, authors, createdAt, updatedAt, nodes, connections, name, autosaved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (version_id, WORKFLOW_ID, "Narratiive OS", now, now, encoded_nodes, encoded_connections, WORKFLOW_NAME),
            )
            connection.execute(
                "UPDATE workflow_entity SET nodes = ?, connections = ?, versionId = ?, activeVersionId = ?, updatedAt = ? WHERE id = ?",
                (encoded_nodes, encoded_connections, version_id, version_id, now, WORKFLOW_ID),
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
        "version_id": version_id,
        "backup": str(backup),
        "restarted": restart,
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
