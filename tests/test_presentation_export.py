import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from runtime.presentation_export import (
    BlueprintPresentationExporter,
    ClaudeSlidesAdapter,
    FakePresentationAdapter,
    FilePresentationExportStore,
    PresentationExportRequest,
    PresentationTemplateConfiguration,
)


def canonical_checksum(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def renderable(workspace_id="rave", client_id="rave-client"):
    return {
        "workspace_id": workspace_id,
        "client_id": client_id,
        "acts": [
            {"act": index, "slide_numbers": list(range((index - 1) * 5 + 1, index * 5 + 1))}
            for index in range(1, 7)
        ],
        "slides": [
            {
                "slide_no": number,
                "slide_name": f"Slide {number}",
                "act": ((number - 1) // 5) + 1,
                "layout": "canonical",
                "speaker_notes": [f"Source note {number}"],
            }
            for number in range(1, 31)
        ],
    }


def request_for(payload, *, requested_version=None, workspace_id="rave", client_id="rave-client"):
    return PresentationExportRequest(
        workspace_id=workspace_id,
        client_id=client_id,
        blueprint_id="rave-growth-blueprint",
        blueprint_version=3,
        renderable_checksum=canonical_checksum(payload),
        canon_version="3.0",
        canon_checksums={"schema": "a" * 64, "visuals": "b" * 64},
        template=PresentationTemplateConfiguration(
            template_id="narratiive-master",
            template_version="2026-07",
            destination_folder_id="rave-deliverables",
        ),
        requested_version=requested_version,
    )


class PresentationExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = FilePresentationExportStore(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def test_exports_complete_ordered_blueprint_through_fake_adapter(self):
        payload = renderable()
        adapter = FakePresentationAdapter()
        exporter = BlueprintPresentationExporter(adapter, self.store)
        record = exporter.export(request_for(payload), payload)
        self.assertEqual(record.status, "completed")
        self.assertEqual(len(adapter.calls[0]["blueprint"]["slides"]), 30)
        self.assertEqual(record.provider, "claude")
        self.assertTrue(record.presentation_url.startswith("https://docs.google.com/presentation/"))

    def test_identical_request_is_idempotent(self):
        payload = renderable()
        adapter = FakePresentationAdapter()
        exporter = BlueprintPresentationExporter(adapter, self.store)
        first = exporter.export(request_for(payload), payload)
        second = exporter.export(request_for(payload), payload)
        self.assertEqual(first, second)
        self.assertEqual(len(adapter.calls), 1)

    def test_explicit_new_version_creates_new_export(self):
        payload = renderable()
        adapter = FakePresentationAdapter()
        exporter = BlueprintPresentationExporter(adapter, self.store)
        first = exporter.export(request_for(payload), payload)
        second = exporter.export(request_for(payload, requested_version=2), payload)
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertEqual(len(adapter.calls), 2)

    def test_failed_export_is_immutable_and_not_completed(self):
        payload = renderable()
        exporter = BlueprintPresentationExporter(
            FakePresentationAdapter(fail=True, retryable=True), self.store
        )
        record = exporter.export(request_for(payload), payload)
        self.assertEqual(record.status, "failed")
        self.assertTrue(record.retryable)
        self.assertEqual(record.presentation_id, "")
        self.assertEqual(self.store.get("rave", "rave-client", record.export_id), record)

    def test_rejects_cross_workspace_renderable(self):
        payload = renderable(workspace_id="maeving")
        request = request_for(payload, workspace_id="rave")
        exporter = BlueprintPresentationExporter(FakePresentationAdapter(), self.store)
        with self.assertRaisesRegex(ValueError, "different workspace"):
            exporter.export(request, payload)

    def test_rejects_malformed_or_reordered_deck(self):
        payload = renderable()
        payload["slides"][0], payload["slides"][1] = payload["slides"][1], payload["slides"][0]
        exporter = BlueprintPresentationExporter(FakePresentationAdapter(), self.store)
        with self.assertRaisesRegex(ValueError, "ordering"):
            exporter.export(request_for(payload), payload)

    def test_claude_adapter_delegates_existing_export_capability(self):
        captured = {}

        def claude_export(payload):
            captured.update(payload)
            return {
                "presentation_id": "claude-deck-1",
                "presentation_url": "https://docs.google.com/presentation/d/claude-deck-1/edit",
                "provider_request_id": "claude-request-1",
            }

        payload = renderable()
        exporter = BlueprintPresentationExporter(ClaudeSlidesAdapter(claude_export), self.store)
        record = exporter.export(request_for(payload), payload)
        self.assertEqual(captured["operation"], "export_google_slides")
        self.assertEqual(captured["template_id"], "narratiive-master")
        self.assertEqual(record.presentation_id, "claude-deck-1")

    def test_records_do_not_persist_credentials(self):
        payload = renderable()
        record = BlueprintPresentationExporter(FakePresentationAdapter(), self.store).export(
            request_for(payload), payload
        )
        serialized = json.dumps(record.to_dict()).lower()
        self.assertNotIn("token", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("credential", serialized)


if __name__ == "__main__":
    unittest.main()
