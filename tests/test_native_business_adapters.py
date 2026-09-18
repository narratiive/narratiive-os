from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from datetime import datetime, timezone

from runtime.native_business_adapters import (
    BusinessAdapterError,
    FirefliesDispatcher,
    GmailDispatcher,
    GoogleCalendarDispatcher,
    GoogleDriveDispatcher,
    GoogleOAuthConfig,
    NotionWorkflowProjectionDispatcher,
)
from runtime.tony_dispatch_adapters import build_http_dispatchers
from runtime.tony_execution_readiness import build_execution_readiness_report


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _size=-1):
        return json.dumps(self.payload).encode("utf-8")


class Router:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        if not self.responses:
            raise AssertionError("unexpected provider request")
        response = self.responses.pop(0)
        value = response(req) if callable(response) else response
        if isinstance(value, BaseException):
            raise value
        return value if hasattr(value, "__enter__") else Response(value)


def read_contract(**target):
    return {"execution_mode": "autonomous_read", "target": target}


def approved_contract(payload, **target):
    return {
        "execution_mode": "approval_gated_write",
        "approval_granted": True,
        "state": "approved_pending_execution",
        "payload": payload,
        "target": target,
    }


class NativeBusinessAdapterTests(unittest.TestCase):
    def test_native_modes_enable_only_when_required_credentials_are_present(self):
        missing = build_http_dispatchers(
            {
                "TONY_DISPATCH_GMAIL_MODE": "google_api",
                "TONY_DISPATCH_NOTION_MODE": "notion_api",
                "TONY_DISPATCH_FIREFLIES_MODE": "fireflies_api",
            }
        )
        self.assertEqual(missing, {})

        configured = build_http_dispatchers(
            {
                "TONY_DISPATCH_GMAIL_MODE": "google_api",
                "TONY_DISPATCH_GOOGLE_CALENDAR_MODE": "google_api",
                "TONY_DISPATCH_GOOGLE_DRIVE_MODE": "google_api",
                "TONY_GOOGLE_ACCESS_TOKEN": "synthetic-access-token",
                "TONY_DISPATCH_NOTION_MODE": "notion_api",
                "NARRATIIVE_NOTION_TOKEN": "synthetic-notion-token",
                "TONY_DISPATCH_FIREFLIES_MODE": "fireflies_api",
                "TONY_FIREFLIES_API_KEY": "synthetic-fireflies-key",
            }
        )
        self.assertEqual(set(configured), {"Gmail", "Google Calendar", "Google Drive", "Notion", "Fireflies"})

    def test_readiness_reports_native_modes_without_rendering_credentials(self):
        env = {
            "TONY_DISPATCH_CLAUDE_URL": "http://claude.invalid",
            "TONY_DISPATCH_GMAIL_MODE": "google_api",
            "TONY_DISPATCH_GOOGLE_CALENDAR_MODE": "google_api",
            "TONY_DISPATCH_GOOGLE_DRIVE_MODE": "google_api",
            "TONY_GOOGLE_ACCESS_TOKEN": "never-render-this",
            "TONY_DISPATCH_NOTION_MODE": "notion_api",
            "NARRATIIVE_NOTION_TOKEN": "never-render-this",
            "TONY_DISPATCH_FIREFLIES_MODE": "fireflies_api",
            "FIREFLIES_API_KEY": "never-render-this",
        }
        report = build_execution_readiness_report(env)
        self.assertTrue(report.ready)
        self.assertEqual({item.mode for item in report.workers}, {"http", "google_api", "notion_api", "fireflies_api"})
        self.assertNotIn("never-render-this", json.dumps(report.to_dict()))

    def test_google_refresh_credentials_are_exchanged_at_call_time(self):
        router = Router([
            {"access_token": "ephemeral-token"},
            {"emailAddress": "safe@example.invalid"},
        ])
        adapter = GmailDispatcher(
            GoogleOAuthConfig(client_id="client", client_secret="secret", refresh_token="refresh"),
            opener=router,
        )

        result = adapter.probe()

        self.assertTrue(result["read_only"])
        form = router.requests[0].data.decode("utf-8")
        self.assertIn("grant_type=refresh_token", form)
        self.assertEqual(router.requests[1].get_header("Authorization"), "Bearer ephemeral-token")
        self.assertNotIn("ephemeral-token", json.dumps(result))

    def test_gmail_reads_only_the_anchored_thread(self):
        router = Router([
            {"id": "anchor", "threadId": "thread-1"},
            {
                "id": "thread-1",
                "messages": [
                    {"id": "anchor", "payload": {"headers": []}, "snippet": "sent"},
                    {"id": "reply-1", "payload": {"headers": [{"name": "From", "value": "safe@example.invalid"}]}, "snippet": "SAFE reply"},
                ],
            },
        ])
        adapter = GmailDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter({"execution_mode": "autonomous_read", "payload": {"gmail_message_id": "anchor"}})

        self.assertTrue(result["read_only"])
        self.assertTrue(result["reply_found"])
        self.assertEqual(result["thread_id"], "thread-1")
        self.assertEqual(result["message_id"], "reply-1")
        self.assertEqual(result["mutation_count"], 0)

    def test_gmail_search_returns_bounded_metadata_without_mutation(self):
        router = Router([
            {"messages": [{"id": "m1", "threadId": "t1"}]},
            {
                "id": "m1",
                "threadId": "t1",
                "snippet": "SAFE proposal",
                "payload": {"headers": [
                    {"name": "From", "value": "hello@narratiive.com"},
                    {"name": "Subject", "value": "KatKin"},
                ]},
            },
        ])
        adapter = GmailDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter({
            "execution_mode": "autonomous_read",
            "operation": "search",
            "target": {"query": "KatKin", "max_results": 3},
        })

        self.assertTrue(result["read_only"])
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(result["results"][0]["subject"], "KatKin")
        self.assertIn("q=KatKin", router.requests[0].full_url)

    def test_gmail_list_defaults_to_inbox_and_reports_unread_state(self):
        router = Router([
            {"messages": [{"id": "m1", "threadId": "t1"}]},
            {
                "id": "m1",
                "threadId": "t1",
                "labelIds": ["INBOX", "UNREAD"],
                "snippet": "Hello &amp; welcome",
                "payload": {"headers": [{"name": "From", "value": "lead@example.invalid"}]},
            },
        ])
        adapter = GmailDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter({"execution_mode": "autonomous_read", "operation": "list", "target": {}})

        self.assertEqual(result["query"], "in:inbox")
        self.assertEqual(result["results"][0]["snippet"], "Hello & welcome")
        self.assertTrue(result["results"][0]["unread"])
        self.assertIn("q=in%3Ainbox", router.requests[0].full_url)

    def test_gmail_get_content_reads_the_selected_inbound_message(self):
        encoded = base64.urlsafe_b64encode(b"Can we arrange a call next week?").decode("ascii").rstrip("=")
        router = Router([{
            "id": "inbound-1",
            "threadId": "thread-1",
            "labelIds": ["INBOX"],
            "snippet": "Can we arrange a call next week?",
            "payload": {
                "mimeType": "text/plain",
                "body": {"data": encoded},
                "headers": [
                    {"name": "From", "value": "lead@example.invalid"},
                    {"name": "To", "value": "hello@narratiive.com"},
                    {"name": "Subject", "value": "New project"},
                ],
            },
        }])
        adapter = GmailDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter({
            "execution_mode": "autonomous_read",
            "operation": "get_content",
            "target": {"message_id": "inbound-1"},
        })

        self.assertEqual(result["message_id"], "inbound-1")
        self.assertEqual(result["thread_id"], "thread-1")
        self.assertEqual(result["body"], "Can we arrange a call next week?")
        self.assertTrue(result["content_included"])
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(len(router.requests), 1)

    def test_gmail_write_requires_approval_and_suppresses_duplicate_send(self):
        adapter = GmailDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=Router([]))
        with self.assertRaisesRegex(BusinessAdapterError, "approval"):
            adapter(
                {
                    "execution_mode": "approval_gated_write",
                    "approval_granted": False,
                    "payload": {"recipient_email": "safe@example.invalid", "subject": "SAFE", "body": "SAFE"},
                }
            )

        router = Router([{"messages": [{"id": "existing", "threadId": "thread-1"}]}])
        adapter = GmailDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)
        result = adapter(approved_contract({"recipient_email": "safe@example.invalid", "subject": "SAFE", "body": "SAFE"}))
        self.assertTrue(result["duplicate_suppressed"])
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(len(router.requests), 1)

    def test_gmail_internal_review_exception_is_exact_and_supports_attachment(self):
        contract = {
            "execution_mode": "authorised_internal_review_write",
            "approval_scope": "narratiive_internal_artifact_review",
            "idempotency_key": "safe-internal-review",
            "payload": {
                "kind": "internal_artifact_review_delivery",
                "recipient_email": "hello@narratiive.com",
                "subject": "SAFE internal review",
                "body": "Review the attached immutable artefact.",
                "attachments": [
                    {
                        "filename": "SAFE-Blueprint-Lite-v1.html",
                        "mime_type": "text/html",
                        "content_base64": base64.b64encode(b"<html>SAFE</html>").decode("ascii"),
                    }
                ],
            },
        }
        router = Router([{"messages": []}, {"id": "sent-1", "threadId": "thread-1"}])
        adapter = GmailDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter(contract)

        self.assertTrue(result["sent"])
        raw = json.loads(router.requests[1].data)["raw"]
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
        self.assertIn("SAFE-Blueprint-Lite-v1.html", decoded)
        self.assertIn("Content-Type: text/html", decoded)

        rejected = {**contract, "payload": {**contract["payload"], "recipient_email": "outside@example.com"}}
        with self.assertRaisesRegex(BusinessAdapterError, "scope_rejected"):
            adapter(rejected)

    def test_calendar_freebusy_is_read_only_and_create_uses_deterministic_id(self):
        router = Router([
            {"calendars": {"primary": {"busy": [{"start": "2026-09-08T10:00:00Z", "end": "2026-09-08T10:30:00Z"}]}}},
            HTTPError("https://calendar.google.invalid", 404, "not found", {}, None),
            lambda req: {"id": json.loads(req.data)["id"], "htmlLink": "https://calendar.google.invalid/event"},
        ])
        adapter = GoogleCalendarDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)
        read = adapter(read_contract(time_min="2026-09-08T00:00:00Z", time_max="2026-09-09T00:00:00Z"))
        created = adapter(approved_contract({"slot": {"start": "2026-09-08T11:00:00Z", "end": "2026-09-08T11:30:00Z"}, "reply_message_id": "safe-reply"}))

        self.assertEqual(read["mutation_count"], 0)
        self.assertTrue(created["created"])
        self.assertEqual(len(created["event_id"]), 32)
        self.assertIn("sendUpdates=none", router.requests[2].full_url)

    def test_calendar_read_accepts_tony_natural_range_shapes(self):
        router = Router([
            {"calendars": {"primary": {"busy": []}}},
            {"calendars": {"primary": {"busy": []}}},
        ])
        adapter = GoogleCalendarDispatcher(
            GoogleOAuthConfig(access_token="synthetic"),
            opener=router,
            clock=lambda: datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc),
        )

        relative = adapter({
            "execution_mode": "autonomous_read",
            "operation": "list",
            "target": {"days_ahead": 7},
        })
        dated = adapter({
            "execution_mode": "autonomous_read",
            "operation": "list",
            "target": {"start_date": "2026-09-17", "end_date": "2026-09-23"},
        })

        self.assertEqual(relative["timezone"], "Europe/London")
        self.assertTrue(relative["time_min"].startswith("2026-09-16T17:00:00"))
        self.assertTrue(relative["time_max"].startswith("2026-09-23T17:00:00"))
        self.assertTrue(dated["time_min"].startswith("2026-09-17T00:00:00"))
        self.assertTrue(dated["time_max"].startswith("2026-09-24T00:00:00"))
        self.assertEqual(json.loads(router.requests[0].data)["timeMin"], relative["time_min"])
        self.assertEqual(relative["mutation_count"], 0)

    def test_calendar_create_suppresses_replay_when_deterministic_event_exists(self):
        event_id = "9d8fd3c31bae4a086b8fb32933732535"
        router = Router([{"id": event_id, "htmlLink": "https://calendar.google.invalid/event"}])
        adapter = GoogleCalendarDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter(
            {
                **approved_contract(
                    {"slot": {"start": "2026-09-08T11:00:00Z", "end": "2026-09-08T11:30:00Z"}}
                ),
                "idempotency_key": "safe-calendar-replay",
            }
        )

        self.assertTrue(result["duplicate_suppressed"])
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(len(router.requests), 1)

    def test_drive_workspace_creation_is_idempotent(self):
        router = Router([{"files": [{"id": "folder-1", "webViewLink": "https://drive.google.invalid/folder-1"}]}])
        adapter = GoogleDriveDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)
        result = adapter(approved_contract({"kind": "client_delivery_drive_workspace", "delivery_project_record_id": "safe-project", "folder_structure": []}, company="SAFE TEST ONLY"))
        self.assertTrue(result["duplicate_suppressed"])
        self.assertEqual(result["folder_id"], "folder-1")
        self.assertEqual(result["mutation_count"], 0)

    def test_drive_search_is_bounded_and_read_only(self):
        router = Router([{"files": [{"id": "file-1", "name": "KatKin Proposal.pdf", "mimeType": "application/pdf"}]}])
        adapter = GoogleDriveDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter({
            "execution_mode": "autonomous_read",
            "operation": "search",
            "target": {"query": "KatKin", "max_results": 50},
        })

        self.assertTrue(result["read_only"])
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(result["files"][0]["name"], "KatKin Proposal.pdf")
        self.assertIn("pageSize=10", router.requests[0].full_url)

    def test_drive_list_defaults_to_recent_non_trashed_files(self):
        router = Router([{"files": [{"id": "file-1", "name": "Recent strategy.pdf"}]}])
        adapter = GoogleDriveDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter({"execution_mode": "autonomous_read", "operation": "list", "target": {"max_results": 5}})

        self.assertEqual(result["source_id"], "drive:list")
        self.assertEqual(result["files"][0]["name"], "Recent strategy.pdf")
        self.assertIn("q=trashed%3Dfalse", router.requests[0].full_url)
        self.assertIn("orderBy=modifiedTime%20desc", router.requests[0].full_url)

    def test_drive_get_metadata_without_file_id_lists_recent_files(self):
        router = Router([{"files": [{"id": "file-1", "name": "Recent strategy.pdf"}]}])
        adapter = GoogleDriveDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter({
            "execution_mode": "autonomous_read",
            "operation": "get_metadata",
            "target": {"max_results": 10, "fields": ["name", "mimeType", "modifiedTime"]},
        })

        self.assertEqual(result["source_id"], "drive:list")
        self.assertEqual(result["files"][0]["name"], "Recent strategy.pdf")
        self.assertIn("orderBy=modifiedTime%20desc", router.requests[0].full_url)
        self.assertEqual(result["mutation_count"], 0)

    def test_drive_workspace_replay_repairs_only_missing_child_folders(self):
        router = Router(
            [
                {"files": [{"id": "folder-1", "webViewLink": "https://drive.google.invalid/folder-1"}]},
                {"files": [{"id": "existing-child"}]},
                {"files": []},
                {"id": "new-child"},
            ]
        )
        adapter = GoogleDriveDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)

        result = adapter(
            approved_contract(
                {
                    "kind": "client_delivery_drive_workspace",
                    "delivery_project_record_id": "safe-project",
                    "folder_structure": ["01 Strategy", "02 Research"],
                },
                company="SAFE TEST ONLY",
            )
        )

        self.assertEqual(result["folder_id"], "folder-1")
        self.assertEqual(result["mutation_count"], 1)
        self.assertFalse(result["duplicate_suppressed"])
        self.assertEqual(router.requests[-1].method, "POST")

    def test_drive_reviewed_artifact_uses_bounded_multipart_upload(self):
        router = Router([{"files": []}, {"id": "file-1", "webViewLink": "https://drive.google.invalid/file-1"}])
        adapter = GoogleDriveDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=router)
        result = adapter(approved_contract({"kind": "reviewed_growth_blueprint_artifact", "parent_folder_id": "folder-1", "filename": "SAFE Blueprint.md", "content": "SAFE synthetic content"}))
        self.assertEqual(result["file_id"], "file-1")
        self.assertIn("uploadType=multipart", router.requests[1].full_url)
        self.assertIn("multipart/related", router.requests[1].get_header("Content-type"))

    def test_drive_reviewed_binary_upload_requires_exact_root_type_and_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deck = root / "Northstar Growth Blueprint.pptx"
            content = b"PK\x03\x04 SAFE synthetic PPTX package"
            deck.write_bytes(content)
            router = Router([{"files": []}, {"id": "file-pptx", "webViewLink": "https://drive.google.invalid/file-pptx"}])
            adapter = GoogleDriveDispatcher(
                GoogleOAuthConfig(access_token="synthetic"),
                opener=router,
                allowed_upload_root=root,
            )
            result = adapter(
                approved_contract(
                    {
                        "kind": "reviewed_growth_blueprint_file",
                        "parent_folder_id": "folder-1",
                        "filename": deck.name,
                        "local_path": str(deck),
                        "checksum": hashlib.sha256(content).hexdigest(),
                        "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    }
                )
            )
            self.assertEqual(result["file_id"], "file-pptx")
            self.assertEqual(result["checksum"], hashlib.sha256(content).hexdigest())
            self.assertIn(content, router.requests[1].data)

    def test_drive_binary_upload_rejects_unapproved_path_and_checksum(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            file = Path(outside) / "unsafe.pdf"
            file.write_bytes(b"%PDF-1.7 safe test")
            adapter = GoogleDriveDispatcher(
                GoogleOAuthConfig(access_token="synthetic"),
                opener=Router([{"files": []}]),
                allowed_upload_root=root,
            )
            payload = {
                "kind": "reviewed_growth_blueprint_file",
                "parent_folder_id": "folder-1",
                "filename": file.name,
                "local_path": str(file),
                "checksum": hashlib.sha256(file.read_bytes()).hexdigest(),
                "mime_type": "application/pdf",
            }
            with self.assertRaisesRegex(BusinessAdapterError, "outside_allowed_root"):
                adapter(approved_contract(payload))

            inside = root / "safe.pdf"
            inside.write_bytes(file.read_bytes())
            payload.update({"filename": inside.name, "local_path": str(inside), "checksum": "0" * 64})
            with self.assertRaisesRegex(BusinessAdapterError, "checksum_mismatch"):
                adapter(approved_contract(payload))

    def test_notion_projection_requires_approval_and_suppresses_matching_marker(self):
        adapter = NotionWorkflowProjectionDispatcher("synthetic", "source-1", opener=Router([]))
        with self.assertRaisesRegex(BusinessAdapterError, "approval"):
            adapter(
                {
                    "execution_mode": "approval_gated_write",
                    "approval_granted": False,
                    "payload": {"kind": "workflow_business_state_projection"},
                    "target": {"lead_id": "page-1"},
                }
            )

        key = "safe-projection-key"
        router = Router([{"id": "page-1", "properties": {"AI Summary": {"rich_text": [{"plain_text": f"[workflow-projection:{key}]"}]}}}])
        adapter = NotionWorkflowProjectionDispatcher("synthetic", "source-1", opener=router)
        result = adapter(approved_contract({"kind": "workflow_business_state_projection", "projection_key": key}, lead_id="page-1"))
        self.assertTrue(result["duplicate_suppressed"])
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(len(router.requests), 1)

    def test_notion_search_returns_plain_business_properties_without_mutation(self):
        router = Router([{
            "results": [{
                "id": "page-1",
                "url": "https://notion.invalid/page-1",
                "properties": {
                    "Company": {"type": "title", "title": [{"plain_text": "KatKin"}]},
                    "Email": {"type": "email", "email": "safe@example.invalid"},
                },
            }]
        }])
        adapter = NotionWorkflowProjectionDispatcher("synthetic", "source-1", opener=router)

        result = adapter({
            "execution_mode": "autonomous_read",
            "operation": "search",
            "target": {"query": "KatKin"},
        })

        self.assertTrue(result["read_only"])
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(result["pages"][0]["properties"]["Company"], "KatKin")
        self.assertEqual(result["pages"][0]["properties"]["Email"], "safe@example.invalid")
        self.assertEqual(router.requests[0].method, "POST")

    def test_notion_projection_maps_only_canonical_business_fields(self):
        router = Router([
            {"id": "page-1", "properties": {"AI Summary": {"rich_text": []}}},
            {"id": "page-1"},
        ])
        adapter = NotionWorkflowProjectionDispatcher("synthetic", "source-1", opener=router)
        result = adapter(
            approved_contract(
                {
                    "kind": "workflow_business_state_projection",
                    "projection_key": "safe-key",
                    "workflow_id": "blueprint_lite_to_discovery_preparation",
                    "workflow_status": "awaiting_approval",
                    "approval_status": "pending",
                    "lifecycle_stage": "discovery",
                    "proposed_next_action": "Review SAFE internal preparation.",
                    "deliverable_state": "persisted_internal_drive_not_delivered",
                    "drive_files": [{
                        "filename": "Northstar-Growth-Blueprint.pdf",
                        "file_url": "https://drive.invalid/file-1",
                    }],
                },
                lead_id="page-1",
            )
        )
        body = json.loads(router.requests[1].data)
        self.assertEqual(set(body["properties"]), {"Status", "AI Summary", "Recommended Next Action", "Approval Status", "Pipeline Stage"})
        self.assertEqual(body["properties"]["Approval Status"]["select"]["name"], "Needs Review")
        summary = body["properties"]["AI Summary"]["rich_text"][0]["text"]["content"]
        self.assertIn("persisted_internal_drive_not_delivered", summary)
        self.assertIn("https://drive.invalid/file-1", summary)
        self.assertEqual(result["projection_key"], "safe-key")

    def test_fireflies_returns_provenanced_transcript_without_mutation(self):
        router = Router([{"data": {"transcript": {
            "id": "transcript-1",
            "title": "SAFE TEST",
            "date": 1788861600000,
            "transcript_url": "https://app.fireflies.ai/view/transcript-1",
            "participants": ["safe@example.invalid"],
            "speakers": [{"id": 1, "name": "Synthetic"}],
            "summary": {"overview": "Source-provided overview", "action_items": "Synthetic action"},
            "sentences": [{"index": 0, "speaker_name": "Synthetic", "speaker_id": 1, "text": "Evidence only", "start_time": 1.5, "end_time": 3.0}],
        }}}])
        adapter = FirefliesDispatcher(
            "synthetic",
            opener=router,
            clock=lambda: datetime(2026, 9, 6, tzinfo=timezone.utc),
        )
        result = adapter({"execution_mode": "autonomous_read", "payload": {"transcript_id": "transcript-1"}})
        self.assertTrue(result["read_only"])
        self.assertEqual(result["source_id"], "fireflies:transcript:transcript-1")
        self.assertIn("Evidence only", result["content"])
        self.assertEqual(result["sentences"][0]["start_time"], 1.5)
        self.assertEqual(result["fireflies_summary"]["action_items"], "Synthetic action")
        self.assertEqual(result["sources"][0]["location"], "https://app.fireflies.ai/view/transcript-1")
        self.assertEqual(result["sources"][0]["retrieved_at"], "2026-09-06T00:00:00+00:00")
        self.assertEqual(result["evidence_status"], "complete")
        self.assertFalse(result["external_action_taken"])
        self.assertEqual(result["mutation_count"], 0)

    def test_fireflies_discovers_transcripts_with_bounded_pagination(self):
        first = [{"id": f"transcript-{index}", "title": "SAFE"} for index in range(50)]
        second = [{"id": f"transcript-{index}", "title": "SAFE"} for index in range(50, 55)]
        router = Router([{"data": {"transcripts": first}}, {"data": {"transcripts": second}}])
        adapter = FirefliesDispatcher("synthetic", opener=router)

        result = adapter({
            "execution_mode": "autonomous_read",
            "payload": {"kind": "fireflies_transcript_discovery", "limit": 55, "keyword": "SAFE"},
        })

        self.assertEqual(result["returned_count"], 55)
        self.assertEqual(result["next_skip"], 55)
        self.assertTrue(result["has_more"])
        self.assertEqual(json.loads(router.requests[0].data)["variables"]["skip"], 0)
        self.assertEqual(json.loads(router.requests[1].data)["variables"]["skip"], 50)
        self.assertNotIn("mutation", json.loads(router.requests[0].data)["query"].casefold())

    def test_fireflies_safe_read_list_operation_maps_target_to_discovery(self):
        router = Router([{"data": {"transcripts": [{"id": "transcript-1", "title": "Discovery"}]}}])
        adapter = FirefliesDispatcher("synthetic", opener=router)

        result = adapter({
            "execution_mode": "autonomous_read",
            "operation": "list",
            "target": {"max_results": 3, "keyword": "Discovery"},
        })

        self.assertEqual(result["source_id"], "fireflies:transcripts")
        self.assertEqual(result["returned_count"], 1)
        variables = json.loads(router.requests[0].data)["variables"]
        self.assertEqual(variables["limit"], 3)
        self.assertEqual(variables["keyword"], "Discovery")

    def test_fireflies_retries_rate_limit_and_classifies_provider_errors(self):
        rate_limit = HTTPError("https://api.fireflies.ai/graphql", 429, "rate", {"Retry-After": "0"}, None)
        router = Router([rate_limit, {"data": {"user": {"user_id": "safe-user"}, "transcripts": []}}])
        sleeps = []
        adapter = FirefliesDispatcher("synthetic", opener=router, sleeper=sleeps.append)
        probe = adapter.probe()
        self.assertTrue(probe["verified"])
        self.assertIn("transcript_text_and_timestamps", probe["validated_capabilities"])
        self.assertEqual(sleeps, [0.0])

        for payload, expected in (
            ({"errors": [{"code": "auth_failed"}]}, "fireflies_auth_failed"),
            ({"errors": [{"code": "object_not_found"}]}, "fireflies_transcript_not_found"),
            (["not-an-object"], "fireflies_response_malformed"),
        ):
            failing = FirefliesDispatcher("synthetic", opener=Router([payload]), max_attempts=1)
            with self.assertRaisesRegex(BusinessAdapterError, expected):
                failing({"execution_mode": "autonomous_read", "payload": {"transcript_id": "missing"}})

        for status, expected in ((401, "fireflies_auth_failed"), (403, "fireflies_forbidden")):
            error = HTTPError("https://api.fireflies.ai/graphql", status, "denied", {}, None)
            failing = FirefliesDispatcher("synthetic", opener=Router([error]), max_attempts=1)
            with self.assertRaisesRegex(BusinessAdapterError, expected):
                failing.probe()

    def test_fireflies_missing_credential_and_incomplete_records_fail_safe(self):
        with self.assertRaisesRegex(BusinessAdapterError, "fireflies_not_configured"):
            FirefliesDispatcher("")
        adapter = FirefliesDispatcher(
            "synthetic",
            opener=Router([{"data": {"transcript": {"id": "transcript-1", "title": "Metadata only"}}}]),
        )
        result = adapter({"execution_mode": "autonomous_read", "payload": {"transcript_id": "transcript-1"}})
        self.assertEqual(result["evidence_status"], "metadata_only")
        self.assertEqual(result["transcript"], "")
        self.assertEqual(result["summary"], "")
        self.assertFalse(result["external_action_taken"])

    def test_fireflies_resolves_the_exact_calendar_event_before_reading_transcript(self):
        router = Router(
            [
                {
                    "data": {
                        "transcripts": [
                            {"id": "other", "calendar_id": "other-event", "cal_id": ""},
                            {"id": "transcript-1", "calendar_id": "event-1", "cal_id": "event-1_20260908"},
                        ]
                    }
                },
                {
                    "data": {
                        "transcript": {
                            "id": "transcript-1",
                            "title": "SAFE TEST",
                            "sentences": [{"speaker_name": "Synthetic", "text": "Grounded meeting evidence"}],
                        }
                    }
                },
            ]
        )
        adapter = FirefliesDispatcher("synthetic", opener=router)

        result = adapter(
            {"execution_mode": "autonomous_read", "payload": {"calendar_event_id": "event-1"}}
        )

        self.assertEqual(result["transcript_id"], "transcript-1")
        self.assertEqual(result["source_id"], "fireflies:transcript:transcript-1")
        self.assertEqual(result["mutation_count"], 0)

    def test_provider_errors_are_sanitised(self):
        adapter = GmailDispatcher(GoogleOAuthConfig(access_token="synthetic"), opener=mock.Mock(side_effect=OSError("sensitive provider detail")))
        with self.assertRaisesRegex(BusinessAdapterError, "provider_unavailable") as raised:
            adapter.probe()
        self.assertNotIn("sensitive", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
