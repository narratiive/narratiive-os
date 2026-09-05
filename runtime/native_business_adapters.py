from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Callable, Mapping
from urllib import parse, request
from urllib.error import HTTPError, URLError


OpenUrl = Callable[..., Any]


class BusinessAdapterError(RuntimeError):
    """A provider adapter failed without exposing provider or credential detail."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _require_read(contract: Mapping[str, Any]) -> None:
    if _text(contract.get("execution_mode")) != "autonomous_read":
        raise BusinessAdapterError("adapter operation is not an authorised read")


def _require_write(contract: Mapping[str, Any]) -> None:
    mode = _text(contract.get("execution_mode"))
    approved = contract.get("approval_granted") is True or contract.get("approval") == "openclaw_allow_once"
    if mode not in {"approval_gated_write", "approved_write"} or not approved:
        raise BusinessAdapterError("adapter write requires exact approval evidence")


class JsonApiClient:
    def __init__(self, *, opener: OpenUrl = request.urlopen, max_response_bytes: int = 1_000_000) -> None:
        self.opener = opener
        self.max_response_bytes = max_response_bytes

    def call(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        form: Mapping[str, str] | None = None,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        data: bytes | None = None
        final_headers = {"Accept": "application/json", **dict(headers or {})}
        if body is not None:
            data = json.dumps(dict(body)).encode("utf-8")
            final_headers["Content-Type"] = "application/json"
        elif form is not None:
            data = parse.urlencode(dict(form)).encode("utf-8")
            final_headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = request.Request(url, data=data, headers=final_headers, method=method)
        try:
            with self.opener(req, timeout=timeout) as response:
                raw = response.read(self.max_response_bytes + 1)
        except HTTPError as exc:
            raise BusinessAdapterError(f"provider_http_{exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise BusinessAdapterError("provider_unavailable") from exc
        if len(raw) > self.max_response_bytes:
            raise BusinessAdapterError("provider_response_too_large")
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BusinessAdapterError("provider_response_invalid") from exc
        if not isinstance(payload, dict):
            raise BusinessAdapterError("provider_response_invalid")
        if payload.get("error") or payload.get("errors"):
            raise BusinessAdapterError("provider_reported_error")
        return payload

    def call_bytes(
        self,
        url: str,
        *,
        data: bytes,
        headers: Mapping[str, str],
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        req = request.Request(url, data=data, headers={"Accept": "application/json", **dict(headers)}, method="POST")
        try:
            with self.opener(req, timeout=timeout) as response:
                raw = response.read(self.max_response_bytes + 1)
        except HTTPError as exc:
            raise BusinessAdapterError(f"provider_http_{exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise BusinessAdapterError("provider_unavailable") from exc
        if len(raw) > self.max_response_bytes:
            raise BusinessAdapterError("provider_response_too_large")
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BusinessAdapterError("provider_response_invalid") from exc
        if not isinstance(payload, dict) or payload.get("error") or payload.get("errors"):
            raise BusinessAdapterError("provider_response_invalid")
        return payload


@dataclass(frozen=True, slots=True)
class GoogleOAuthConfig:
    access_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    token_url: str = "https://oauth2.googleapis.com/token"

    @property
    def configured(self) -> bool:
        return bool(self.access_token or (self.client_id and self.client_secret and self.refresh_token))


class GoogleTokenProvider:
    def __init__(self, config: GoogleOAuthConfig, client: JsonApiClient) -> None:
        self.config = config
        self.client = client

    def token(self) -> str:
        if self.config.access_token:
            return self.config.access_token
        if not self.config.configured:
            raise BusinessAdapterError("google_oauth_not_configured")
        payload = self.client.call(
            self.config.token_url,
            method="POST",
            form={
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "refresh_token": self.config.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        token = _text(payload.get("access_token"))
        if not token:
            raise BusinessAdapterError("google_oauth_refresh_failed")
        return token


class GoogleAdapter:
    def __init__(self, oauth: GoogleOAuthConfig, *, opener: OpenUrl = request.urlopen) -> None:
        self.client = JsonApiClient(opener=opener)
        self.tokens = GoogleTokenProvider(oauth, self.client)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens.token()}"}


class GmailDispatcher(GoogleAdapter):
    api_base = "https://gmail.googleapis.com/gmail/v1"

    def probe(self) -> dict[str, Any]:
        self.client.call(f"{self.api_base}/users/me/profile", headers=self._headers())
        return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": "gmail:profile"}

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        mode = _text(contract.get("execution_mode"))
        return self._read(contract) if mode == "autonomous_read" else self._send(contract)

    def _read(self, contract: Mapping[str, Any]) -> dict[str, Any]:
        _require_read(contract)
        payload, target = _mapping(contract.get("payload")), _mapping(contract.get("target"))
        message_id = _text(payload.get("gmail_message_id") or target.get("message_id"))
        thread_id = _text(target.get("thread_id"))
        if message_id and not thread_id:
            item = self.client.call(
                f"{self.api_base}/users/me/messages/{parse.quote(message_id, safe='')}?format=metadata",
                headers=self._headers(),
            )
            thread_id = _text(item.get("threadId"))
        if not thread_id:
            raise BusinessAdapterError("gmail_read_requires_message_or_thread_id")
        thread = self.client.call(
            f"{self.api_base}/users/me/threads/{parse.quote(thread_id, safe='')}?format=full",
            headers=self._headers(),
        )
        messages = [item for item in thread.get("messages", []) if isinstance(item, Mapping)]
        seen = {
            _text(item)
            for item in payload.get("seen_message_ids", [])
            if _text(item)
        } if isinstance(payload.get("seen_message_ids"), list) else set()
        candidates = [
            item
            for item in messages
            if _text(item.get("id")) != message_id
            and _text(item.get("id")) not in seen
            and "SENT" not in {str(label).upper() for label in item.get("labelIds", [])}
        ]
        latest = candidates[-1] if candidates else None
        headers = {
            _text(item.get("name")).casefold(): _text(item.get("value"))
            for item in _mapping(_mapping(latest).get("payload")).get("headers", [])
            if isinstance(item, Mapping)
        }
        body = _gmail_message_body(_mapping(latest))
        return {
            "verified": True,
            "read_only": True,
            "mutation_count": 0,
            "source_id": f"gmail:thread:{thread_id}",
            "thread_id": thread_id,
            "message_id": _text(_mapping(latest).get("id")) or message_id,
            "reply_found": latest is not None,
            "sender": headers.get("from", ""),
            "received_at": headers.get("date", ""),
            "snippet": _text(_mapping(latest).get("snippet")),
            "body": body or _text(_mapping(latest).get("snippet")),
            "summary": "A matching Gmail thread was read without mutation.",
        }

    def _send(self, contract: Mapping[str, Any]) -> dict[str, Any]:
        _require_write(contract)
        payload, target = _mapping(contract.get("payload")), _mapping(contract.get("target"))
        recipient = _text(payload.get("recipient_email") or target.get("recipient_email") or target.get("email"))
        subject = _text(payload.get("subject") or payload.get("email_subject") or target.get("subject"))
        body = _text(payload.get("body") or payload.get("email_body") or target.get("body"))
        if not recipient or "@" not in recipient or not subject or not body:
            raise BusinessAdapterError("gmail_send_requires_exact_recipient_subject_and_body")
        key = _text(contract.get("idempotency_key")) or hashlib.sha256(
            f"{recipient}\0{subject}\0{body}".encode("utf-8")
        ).hexdigest()
        message_header = f"<narratiive-{hashlib.sha256(key.encode()).hexdigest()[:32]}@narratiive.invalid>"
        query = parse.urlencode({"q": f"in:sent rfc822msgid:{message_header}", "maxResults": "1"})
        existing = self.client.call(f"{self.api_base}/users/me/messages?{query}", headers=self._headers())
        matches = existing.get("messages", [])
        if isinstance(matches, list) and matches:
            prior = _mapping(matches[0])
            return {
                "verified": True,
                "sent": True,
                "mutation_count": 0,
                "message_id": _text(prior.get("id")),
                "thread_id": _text(prior.get("threadId")),
                "duplicate_suppressed": True,
            }
        email = EmailMessage()
        email["To"] = recipient
        email["Subject"] = subject
        email["Message-ID"] = message_header
        email.set_content(body)
        raw = base64.urlsafe_b64encode(email.as_bytes()).decode("ascii").rstrip("=")
        sent = self.client.call(
            f"{self.api_base}/users/me/messages/send",
            method="POST",
            headers=self._headers(),
            body={"raw": raw},
        )
        message_id = _text(sent.get("id"))
        if not message_id:
            raise BusinessAdapterError("gmail_send_unverified")
        return {"verified": True, "sent": True, "mutation_count": 1, "message_id": message_id, "thread_id": _text(sent.get("threadId"))}


class GoogleCalendarDispatcher(GoogleAdapter):
    api_base = "https://www.googleapis.com/calendar/v3"

    def __init__(self, oauth: GoogleOAuthConfig, *, calendar_id: str = "primary", opener: OpenUrl = request.urlopen) -> None:
        super().__init__(oauth, opener=opener)
        self.calendar_id = calendar_id

    def probe(self) -> dict[str, Any]:
        calendar_id = parse.quote(self.calendar_id, safe="")
        self.client.call(f"{self.api_base}/calendars/{calendar_id}", headers=self._headers())
        return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": f"calendar:{self.calendar_id}"}

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        mode = _text(contract.get("execution_mode"))
        payload, target = _mapping(contract.get("payload")), _mapping(contract.get("target"))
        if mode == "autonomous_read":
            _require_read(contract)
            time_min = _text(target.get("time_min") or payload.get("time_min"))
            time_max = _text(target.get("time_max") or payload.get("time_max"))
            if not time_min or not time_max:
                raise BusinessAdapterError("calendar_read_requires_time_range")
            result = self.client.call(
                f"{self.api_base}/freeBusy",
                method="POST",
                headers=self._headers(),
                body={"timeMin": time_min, "timeMax": time_max, "items": [{"id": self.calendar_id}]},
            )
            busy = _mapping(_mapping(result.get("calendars")).get(self.calendar_id)).get("busy", [])
            return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": f"calendar:{self.calendar_id}", "event_ids": [], "busy": busy, "summary": "Calendar availability was read without mutation."}
        _require_write(contract)
        slot = _mapping(payload.get("slot"))
        start = _text(slot.get("start") or target.get("start"))
        end = _text(slot.get("end") or target.get("end"))
        if not start or not end:
            raise BusinessAdapterError("calendar_write_requires_exact_start_and_end")
        key = _text(contract.get("idempotency_key") or payload.get("reply_message_id") or payload.get("gmail_message_id"))
        if not key:
            raise BusinessAdapterError("calendar_write_requires_idempotency_key")
        event_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        calendar_id = parse.quote(self.calendar_id, safe="")
        event_url = f"{self.api_base}/calendars/{calendar_id}/events/{event_id}"
        try:
            existing = self.client.call(event_url, headers=self._headers())
        except BusinessAdapterError as exc:
            if str(exc) != "provider_http_404":
                raise
        else:
            if _text(existing.get("id")) != event_id:
                raise BusinessAdapterError("calendar_existing_event_unverified")
            return {
                "verified": True,
                "created": True,
                "mutation_count": 0,
                "duplicate_suppressed": True,
                "event_id": event_id,
                "url": _text(existing.get("htmlLink")),
            }
        event = {
            "id": event_id,
            "summary": _text(slot.get("summary") or target.get("summary")) or "Narratiive Discovery",
            "start": {"dateTime": start},
            "end": {"dateTime": end},
            "extendedProperties": {"private": {"narratiiveIdempotencyKey": key[:1024]}},
        }
        created = self.client.call(
            f"{self.api_base}/calendars/{calendar_id}/events?sendUpdates=none",
            method="POST",
            headers=self._headers(),
            body=event,
        )
        returned_id = _text(created.get("id"))
        if returned_id != event_id:
            raise BusinessAdapterError("calendar_write_unverified")
        return {"verified": True, "created": True, "mutation_count": 1, "event_id": returned_id, "url": _text(created.get("htmlLink"))}


class GoogleDriveDispatcher(GoogleAdapter):
    api_base = "https://www.googleapis.com/drive/v3"

    def probe(self) -> dict[str, Any]:
        self.client.call(f"{self.api_base}/files?pageSize=1&fields=files(id)", headers=self._headers())
        return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": "drive:files"}

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        mode = _text(contract.get("execution_mode"))
        payload, target = _mapping(contract.get("payload")), _mapping(contract.get("target"))
        if mode == "autonomous_read":
            _require_read(contract)
            file_id = _text(target.get("file_id") or payload.get("file_id"))
            if not file_id:
                raise BusinessAdapterError("drive_read_requires_file_id")
            fields = parse.quote("id,name,mimeType,modifiedTime,webViewLink,parents", safe=",")
            item = self.client.call(f"{self.api_base}/files/{parse.quote(file_id, safe='')}?fields={fields}", headers=self._headers())
            return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": f"drive:file:{file_id}", "file_id": _text(item.get("id")), "summary": "Drive metadata was read without mutation."}
        _require_write(contract)
        kind = _text(payload.get("kind"))
        if kind == "client_delivery_drive_workspace":
            return self._create_workspace(contract, payload, target)
        if kind in {"reviewed_growth_blueprint_artifact", "growth_blueprint_revision"}:
            return self._create_text_file(contract, payload, target)
        raise BusinessAdapterError("drive_write_kind_not_supported")

    def _key(self, contract: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
        material = _text(contract.get("idempotency_key") or payload.get("delivery_project_record_id"))
        if not material:
            material = json.dumps(dict(payload), sort_keys=True, default=str)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _find_existing(self, key: str) -> Mapping[str, Any] | None:
        q = parse.quote(f"appProperties has {{ key='narratiiveIdempotencyKey' and value='{key}' }} and trashed=false", safe="")
        result = self.client.call(f"{self.api_base}/files?q={q}&pageSize=1&fields=files(id,name,mimeType,webViewLink)", headers=self._headers())
        files = result.get("files", [])
        return _mapping(files[0]) if isinstance(files, list) and files else None

    def _create_workspace(self, contract: Mapping[str, Any], payload: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
        key = self._key(contract, payload)
        existing = self._find_existing(key)
        if existing:
            root = existing
            root_id = _text(existing.get("id"))
            mutations = 0
        else:
            name = _text(target.get("company")) or f"Narratiive delivery {key[:12]}"
            root = self.client.call(
                f"{self.api_base}/files?fields=id,webViewLink",
                method="POST",
                headers=self._headers(),
                body={"name": name, "mimeType": "application/vnd.google-apps.folder", "appProperties": {"narratiiveIdempotencyKey": key}},
            )
            root_id = _text(root.get("id"))
            mutations = 1
        if not root_id:
            raise BusinessAdapterError("drive_workspace_unverified")
        for folder in payload.get("folder_structure", []):
            folder_name = _text(folder)
            if not folder_name:
                continue
            child_key = hashlib.sha256(f"{key}\0{folder_name}".encode("utf-8")).hexdigest()
            if self._find_existing(child_key):
                continue
            created = self.client.call(
                f"{self.api_base}/files?fields=id",
                method="POST",
                headers=self._headers(),
                body={
                    "name": folder_name,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [root_id],
                    "appProperties": {"narratiiveIdempotencyKey": child_key},
                },
            )
            if not _text(created.get("id")):
                raise BusinessAdapterError("drive_workspace_child_unverified")
            mutations += 1
        url = _text(root.get("webViewLink")) or f"https://drive.google.com/drive/folders/{root_id}"
        return {
            "verified": True,
            "created": True,
            "mutation_count": mutations,
            "duplicate_suppressed": existing is not None and mutations == 0,
            "folder_id": root_id,
            "file_id": root_id,
            "folder_url": url,
            "url": url,
        }

    def _create_text_file(self, contract: Mapping[str, Any], payload: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
        key = self._key(contract, payload)
        existing = self._find_existing(key)
        if existing:
            url = _text(existing.get("webViewLink"))
            return {"verified": True, "created": True, "mutation_count": 0, "duplicate_suppressed": True, "file_id": _text(existing.get("id")), "file_url": url, "url": url}
        parent = _text(payload.get("parent_folder_id") or target.get("drive_folder_id"))
        filename = _text(payload.get("filename"))
        content = payload.get("content")
        if not parent or not filename or content in (None, "", {}, []):
            raise BusinessAdapterError("drive_file_requires_parent_name_and_content")
        rendered = content if isinstance(content, str) else json.dumps(content, indent=2, sort_keys=True)
        metadata = {"name": filename, "parents": [parent], "mimeType": "text/markdown", "appProperties": {"narratiiveIdempotencyKey": key}}
        boundary = f"narratiive-{hashlib.sha256(key.encode()).hexdigest()[:24]}"
        data = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            + json.dumps(metadata)
            + f"\r\n--{boundary}\r\nContent-Type: text/markdown; charset=UTF-8\r\n\r\n"
            + rendered
            + f"\r\n--{boundary}--\r\n"
        ).encode("utf-8")
        created = self.client.call_bytes(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,webViewLink",
            data=data,
            headers={**self._headers(), "Content-Type": f"multipart/related; boundary={boundary}"},
        )
        file_id = _text(created.get("id"))
        if not file_id:
            raise BusinessAdapterError("drive_file_unverified")
        url = _text(created.get("webViewLink")) or f"https://drive.google.com/open?id={file_id}"
        return {"verified": True, "created": True, "mutation_count": 1, "file_id": file_id, "file_url": url, "url": url}


class NotionWorkflowProjectionDispatcher:
    api_base = "https://api.notion.com"
    notion_version = "2026-03-11"

    def __init__(self, token: str, data_source_id: str, *, opener: OpenUrl = request.urlopen) -> None:
        if not _text(token) or not _text(data_source_id):
            raise BusinessAdapterError("notion_not_configured")
        self.token = token
        self.data_source_id = data_source_id
        self.client = JsonApiClient(opener=opener)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Notion-Version": self.notion_version}

    def probe(self) -> dict[str, Any]:
        self.client.call(f"{self.api_base}/v1/data_sources/{self.data_source_id}", headers=self._headers())
        return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": f"notion:data_source:{self.data_source_id}"}

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        mode = _text(contract.get("execution_mode"))
        target, payload = _mapping(contract.get("target")), _mapping(contract.get("payload"))
        page_id = _text(target.get("record_id") or target.get("page_id") or target.get("lead_id") or payload.get("lead_id"))
        if mode == "autonomous_read":
            _require_read(contract)
            if page_id:
                page = self.client.call(f"{self.api_base}/v1/pages/{parse.quote(page_id, safe='')}", headers=self._headers())
                return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": f"notion:page:{page_id}", "record_id": _text(page.get("id")), "summary": "Notion record was read without mutation."}
            result = self.client.call(f"{self.api_base}/v1/data_sources/{self.data_source_id}/query", method="POST", headers=self._headers(), body={"page_size": 1})
            ids = [_text(item.get("id")) for item in result.get("results", []) if isinstance(item, Mapping) and _text(item.get("id"))]
            return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": f"notion:data_source:{self.data_source_id}", "record_ids": ids, "summary": "The canonical Notion data source was read without mutation."}
        _require_write(contract)
        if _text(payload.get("kind")) != "workflow_business_state_projection" or not page_id:
            raise BusinessAdapterError("notion_projection_requires_exact_page_and_kind")
        key = _text(payload.get("projection_key") or contract.get("idempotency_key"))
        if not key:
            raise BusinessAdapterError("notion_projection_requires_idempotency_key")
        current = self.client.call(f"{self.api_base}/v1/pages/{parse.quote(page_id, safe='')}", headers=self._headers())
        marker = f"[workflow-projection:{key}]"
        summary_text = _notion_plain_text(_mapping(_mapping(current.get("properties")).get("AI Summary")))
        if marker in summary_text:
            return {"verified": True, "updated": True, "mutation_count": 0, "duplicate_suppressed": True, "record_id": _text(current.get("id")), "projection_key": key}
        status = {"active": "Active", "blocked": "Waiting", "awaiting_approval": "Waiting", "complete": "Complete", "failed": "Waiting"}.get(_text(payload.get("workflow_status")), "Waiting")
        approval = {"pending": "Needs Review", "approved": "Approved", "rejected": "Rejected"}.get(_text(payload.get("approval_status")))
        pipeline = {"blueprint_lite": "Blueprint Lite", "discovery": "Discovery Call", "proposal": "Proposal", "delivery": "Growth Sprint"}.get(_text(payload.get("lifecycle_stage")))
        summary = f"Tony workflow {_text(payload.get('workflow_id'))} is { _text(payload.get('workflow_status'))}. {marker}"
        properties: dict[str, Any] = {
            "Status": {"status": {"name": status}},
            "AI Summary": {"rich_text": [{"type": "text", "text": {"content": summary[:1900]}}]},
            "Recommended Next Action": {"rich_text": [{"type": "text", "text": {"content": _text(payload.get("proposed_next_action"))[:1900]}}]},
        }
        if approval:
            properties["Approval Status"] = {"select": {"name": approval}}
        if pipeline:
            properties["Pipeline Stage"] = {"select": {"name": pipeline}}
        updated = self.client.call(f"{self.api_base}/v1/pages/{parse.quote(page_id, safe='')}", method="PATCH", headers=self._headers(), body={"properties": properties})
        returned_id = _text(updated.get("id"))
        if returned_id != page_id:
            raise BusinessAdapterError("notion_projection_unverified")
        return {"verified": True, "updated": True, "mutation_count": 1, "record_id": returned_id, "projection_key": key}


class FirefliesDispatcher:
    api_url = "https://api.fireflies.ai/graphql"

    def __init__(self, api_key: str, *, opener: OpenUrl = request.urlopen) -> None:
        if not _text(api_key):
            raise BusinessAdapterError("fireflies_not_configured")
        self.api_key = api_key
        self.client = JsonApiClient(opener=opener)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def probe(self) -> dict[str, Any]:
        result = self.client.call(self.api_url, method="POST", headers=self._headers(), body={"query": "query { user { user_id } }"})
        if not _text(_mapping(_mapping(result.get("data")).get("user")).get("user_id")):
            raise BusinessAdapterError("fireflies_probe_unverified")
        return {"verified": True, "read_only": True, "mutation_count": 0, "source_id": "fireflies:user"}

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        _require_read(contract)
        payload, target = _mapping(contract.get("payload")), _mapping(contract.get("target"))
        transcript_id = _text(payload.get("transcript_id") or target.get("transcript_id") or target.get("meeting_id"))
        calendar_event_id = _text(payload.get("calendar_event_id") or target.get("calendar_event_id"))
        if not transcript_id and calendar_event_id:
            transcript_id = self._find_transcript_for_calendar_event(calendar_event_id)
        if not transcript_id:
            raise BusinessAdapterError("fireflies_read_requires_transcript_or_calendar_event_id")
        query = "query Transcript($id: String!) { transcript(id: $id) { id title date duration participants summary { overview short_summary action_items } sentences { speaker_name text } } }"
        result = self.client.call(self.api_url, method="POST", headers=self._headers(), body={"query": query, "variables": {"id": transcript_id}})
        transcript = _mapping(_mapping(result.get("data")).get("transcript"))
        if _text(transcript.get("id")) != transcript_id:
            raise BusinessAdapterError("fireflies_transcript_unverified")
        sentences = [item for item in transcript.get("sentences", []) if isinstance(item, Mapping)]
        content = "\n".join(f"{_text(item.get('speaker_name'))}: {_text(item.get('text'))}" for item in sentences if _text(item.get("text")))
        generated_summary = _mapping(transcript.get("summary"))
        summary_text = _text(generated_summary.get("overview") or generated_summary.get("short_summary"))
        return {
            "verified": True,
            "read_only": True,
            "mutation_count": 0,
            "source_id": f"fireflies:transcript:{transcript_id}",
            "transcript_id": transcript_id,
            "meeting_id": transcript_id,
            "title": _text(transcript.get("title")),
            "participants": list(transcript.get("participants", [])) if isinstance(transcript.get("participants"), list) else [],
            "content": content or summary_text,
            "transcript": content,
            "meeting_summary": summary_text,
            "summary": summary_text or "Fireflies transcript evidence was retrieved without mutation.",
        }

    def _find_transcript_for_calendar_event(self, event_id: str) -> str:
        query = "query Transcripts($limit: Int, $mine: Boolean) { transcripts(limit: $limit, mine: $mine) { id calendar_id cal_id } }"
        result = self.client.call(
            self.api_url,
            method="POST",
            headers=self._headers(),
            body={"query": query, "variables": {"limit": 50, "mine": True}},
        )
        transcripts = _mapping(result.get("data")).get("transcripts", [])
        matches = [
            item
            for item in transcripts
            if isinstance(item, Mapping)
            and event_id in {_text(item.get("calendar_id")), _text(item.get("cal_id")).split("_")[0]}
        ]
        if len(matches) != 1:
            raise BusinessAdapterError(
                "fireflies_calendar_event_not_found" if not matches else "fireflies_calendar_event_ambiguous"
            )
        transcript_id = _text(matches[0].get("id"))
        if not transcript_id:
            raise BusinessAdapterError("fireflies_calendar_event_unverified")
        return transcript_id


def _notion_plain_text(prop: Mapping[str, Any]) -> str:
    values = prop.get("rich_text") if isinstance(prop.get("rich_text"), list) else []
    return "".join(_text(item.get("plain_text")) for item in values if isinstance(item, Mapping))


def _gmail_message_body(message: Mapping[str, Any]) -> str:
    def decode_part(part: Mapping[str, Any]) -> str:
        mime_type = _text(part.get("mimeType")).casefold()
        body = _mapping(part.get("body"))
        encoded = _text(body.get("data"))
        if encoded and mime_type in {"text/plain", ""}:
            try:
                padded = encoded + "=" * (-len(encoded) % 4)
                return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace").strip()
            except (ValueError, UnicodeDecodeError):
                return ""
        children = part.get("parts") if isinstance(part.get("parts"), list) else []
        return "\n".join(value for value in (decode_part(_mapping(child)) for child in children) if value).strip()

    return decode_part(_mapping(message.get("payload")))
