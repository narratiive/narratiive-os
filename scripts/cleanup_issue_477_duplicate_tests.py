from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request


MARKER = "ISSUE477-LOA-PASS3-20261017T0644Z"
GMAIL_MESSAGE_IDS = (
    "1a1489864621076b",
    "1a1489867661ed8e",
    "1a1489a037ccfc1e",
)
NOTION_PAGE_IDS = (
    "3fc0c9cf-a8f2-81b5-b75a-d3f865a526c7",
    "3fc0c9cf-a8f2-81aa-8692-c59a92ecdbac",
)
PRESERVED_NOTION_PAGE_ID = "3fc0c9cf-a8f2-81e7-aeea-cdd7cdc8ab16"


def _json_request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: Any = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, headers=headers or {}, method=method)
    with request.urlopen(req, timeout=30) as response:  # nosec B310 - fixed Google/Notion API origins
        value = json.loads(response.read().decode("utf-8") or "{}")
    if not isinstance(value, dict):
        raise RuntimeError("API response was not a JSON object")
    return value


def _google_access_token() -> tuple[str, list[str]]:
    body = parse.urlencode(
        {
            "client_id": os.environ["TONY_GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["TONY_GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["TONY_GOOGLE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = request.Request("https://oauth2.googleapis.com/token", data=body, method="POST")
    with request.urlopen(req, timeout=30) as response:  # nosec B310 - fixed Google OAuth endpoint
        token = json.loads(response.read().decode("utf-8"))
    access = str(token["access_token"])
    info = _json_request(
        "https://oauth2.googleapis.com/tokeninfo?" + parse.urlencode({"access_token": access})
    )
    return access, sorted(str(info.get("scope") or "").split())


def _gmail_message(access_token: str, message_id: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    query = parse.urlencode(
        [("format", "metadata"), ("metadataHeaders", "Subject"), ("metadataHeaders", "From"), ("metadataHeaders", "To")]
    )
    raw = _json_request(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?{query}", headers=headers
    )
    message_headers = {
        str(item.get("name") or ""): str(item.get("value") or "")
        for item in (raw.get("payload", {}).get("headers") or [])
        if isinstance(item, dict)
    }
    return {
        "id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "label_ids": sorted(raw.get("labelIds") or []),
        "snippet": str(raw.get("snippet") or ""),
        "headers": message_headers,
    }


def _notion_page(token: str, page_id: str) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    raw = _json_request(f"https://api.notion.com/v1/pages/{page_id}", headers=headers)
    title_fragments: list[str] = []
    for prop in (raw.get("properties") or {}).values():
        if not isinstance(prop, dict) or prop.get("type") != "title":
            continue
        title_fragments.extend(str(item.get("plain_text") or "") for item in prop.get("title") or [])
    return {
        "id": raw.get("id"),
        "url": raw.get("url"),
        "archived": raw.get("archived"),
        "in_trash": raw.get("in_trash"),
        "title": "".join(title_fragments),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--audit-path", type=Path, required=True)
    args = parser.parse_args()
    now = datetime.now(timezone.utc).isoformat()
    audit: dict[str, Any] = {
        "operation": "issue-477-duplicate-test-cleanup",
        "marker": MARKER,
        "started_at": now,
        "apply": args.apply,
        "recovery_policy": "Gmail messages moved to Trash; Notion pages archived. No permanent deletion.",
        "preserved_notion_page_id": PRESERVED_NOTION_PAGE_ID,
        "gmail": [],
        "notion": [],
    }
    access_token, scopes = _google_access_token()
    audit["google_oauth_scopes"] = scopes
    gmail_headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    for message_id in GMAIL_MESSAGE_IDS:
        entry: dict[str, Any] = {"id": message_id}
        try:
            before = _gmail_message(access_token, message_id)
            entry["before"] = before
            searchable = " ".join([before["snippet"], *before["headers"].values()])
            if MARKER not in searchable:
                raise RuntimeError("safety marker missing; message was not changed")
            if args.apply and "TRASH" not in before["label_ids"]:
                _json_request(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash",
                    method="POST",
                    headers=gmail_headers,
                    body={},
                )
            entry["after"] = _gmail_message(access_token, message_id)
            entry["status"] = "trashed" if "TRASH" in entry["after"]["label_ids"] else "verified_not_changed"
        except Exception as exc:  # preserve per-record cleanup evidence and continue
            entry["status"] = "blocked"
            entry["error"] = f"{type(exc).__name__}: {exc}"
        audit["gmail"].append(entry)

    notion_token = os.environ["NARRATIIVE_NOTION_TOKEN"]
    notion_headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    for page_id in NOTION_PAGE_IDS:
        entry = {"id": page_id}
        try:
            before = _notion_page(notion_token, page_id)
            entry["before"] = before
            if args.apply and not before.get("archived") and not before.get("in_trash"):
                _json_request(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    method="PATCH",
                    headers=notion_headers,
                    body={"archived": True},
                )
            entry["after"] = _notion_page(notion_token, page_id)
            entry["status"] = "archived" if entry["after"].get("archived") or entry["after"].get("in_trash") else "verified_not_changed"
        except Exception as exc:
            entry["status"] = "blocked"
            entry["error"] = f"{type(exc).__name__}: {exc}"
        audit["notion"].append(entry)

    audit["completed_at"] = datetime.now(timezone.utc).isoformat()
    args.audit_path.parent.mkdir(parents=True, exist_ok=True)
    args.audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "gmail": [item["status"] for item in audit["gmail"]],
        "notion": [item["status"] for item in audit["notion"]],
        "audit_path": str(args.audit_path),
    }, indent=2))


if __name__ == "__main__":
    main()
