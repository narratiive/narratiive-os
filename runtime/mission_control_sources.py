"""Bounded reads for the existing operator UI; no operational writes or new stores."""
from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from runtime.inbound_leads import FileInboundLeadStore, InboundLead, _plain_text
from runtime.notion_leads import NotionLeadConfig, NotionLeadSource


def read_operator_leads(env: Mapping[str, str], cache: FileInboundLeadStore) -> tuple[InboundLead, ...]:
    """Use the existing authority choice without synchronising a cache on GET."""
    mode = str(env.get("TONY_INBOUND_LEAD_SOURCE") or "notion").strip().casefold()
    if mode == "local_projection":
        return cache.read()
    if mode != "notion":
        raise ValueError("Unsupported authoritative lead source")
    return NotionLeadSource(NotionLeadConfig.from_env(env)).read()


def read_n8n_executions(env: Mapping[str, str]) -> dict[str, Any]:
    if env.get("TONY_DISPATCH_N8N_MODE") != "local_sqlite":
        return {"state": "not_connected", "executions": [], "evidence": "Existing n8n local read adapter is not configured."}
    path = Path(env.get("TONY_N8N_DATABASE_PATH") or str(Path.home() / ".n8n/database.sqlite")).expanduser()
    if not path.is_file():
        return {"state": "not_connected", "executions": [], "evidence": "Configured n8n database is unavailable on this host."}
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            rows = connection.execute(
                'SELECT id, "workflowId", status, "startedAt", "stoppedAt", "retryOf", "retrySuccessId" '
                'FROM execution_entity WHERE "deletedAt" IS NULL ORDER BY id DESC LIMIT 50'
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return {"state": "degraded", "executions": [], "evidence": "n8n execution metadata could not be read; check schema compatibility and database access."}
    return {"state": "connected", "evidence": "Read-only n8n execution metadata; newest 50 retained records. Payloads are excluded; deleted/unretained executions are not covered.",
            "executions": [{"execution_id": str(row[0]), "workflow_id": str(row[1]),
                            "status": str(row[2]), "started_at": row[3], "stopped_at": row[4],
                            "retry_of": row[5], "retry_success_id": row[6]} for row in rows]}


def read_marketing(env: Mapping[str, str]) -> dict[str, Any]:
    source = str(env.get("NARRATIIVE_NOTION_MARKETING_DATA_SOURCE_ID") or "").strip()
    base = {"state": "not_connected", "items": [], "metrics": None,
            "publication_enabled": False,
            "north_star": "Help ambitious founder-led businesses make better growth decisions, then show how those decisions become effective marketing.",
            "editorial_priorities": ["Where the next customers come from", "Why buyers choose a competitor", "What to stop funding", "How strategy becomes a campaign"],
            "strategy_status": "Proposed reset — awaiting Matt's review",
            "blocker": "Confirm the active Notion marketing source and its field mapping; the discovered Content OS database is archived."}
    if not source:
        return base
    if source.replace("-", "") == "2920c9cfa8f28129bfbf000b9ca47fa8":
        return {**base, "blocker": "Archived Content OS cannot be treated as active production. Select the authoritative active source."}
    # Same Notion credentials, API version, bounded pagination and read transport
    # as the existing commercial adapter. No cache, writes or field migrations.
    try:
        config = NotionLeadConfig.from_env(env)
        reader = NotionLeadSource(replace(config, data_source_id=source, max_pages=2))
        items = []
        cursor = None
        for _ in range(reader.config.max_pages):
            page = reader._query_page(cursor)
            if not isinstance(page.get("results"), list):
                raise ValueError("invalid content rows")
            for row in page["results"]:
                if not isinstance(row, dict) or row.get("archived") or row.get("in_trash"):
                    continue
                props = row.get("properties", {})
                if not isinstance(props, dict) or "Title" not in props or "Status" not in props:
                    raise ValueError("marketing schema mismatch")
                value = lambda key: _plain_text(props.get(key))
                items.append({"id": row.get("id"), "title": value("Title"),
                              "status": value("Status") or "Not recorded",
                              "concept": value("Concept"), "draft": value("LinkedIn Copy"),
                              "commercial_objective": value("Commercial Objective"),
                              "owner": value("Owner"), "blocker": value("Blocker"),
                              "updated_at": row.get("last_edited_time"),
                              "approval": "Not verified — inspect exact-version approval record",
                              "publication": "Not verified — publication receipt required"})
            if page.get("has_more") is not True:
                return {**base, "state": "connected", "items": items,
                        "blocker": None, "source_id": source,
                        "evidence": "Current Notion content properties. Status labels alone do not verify approval or publication."}
            cursor = page.get("next_cursor")
            if not isinstance(cursor, str) or not cursor:
                raise ValueError("incomplete content pagination")
        raise ValueError("content read exceeded bound")
    except (RuntimeError, ValueError, TypeError, KeyError, OSError):
        return {**base, "state": "degraded", "blocker": "Marketing read failed. Check Notion access, Title/Status field mapping and the 200-row read bound; no success is inferred."}
