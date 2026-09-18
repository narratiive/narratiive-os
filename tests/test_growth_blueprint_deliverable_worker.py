from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.deliverable_production import FakePresentationRenderer, FileDeliverableStore, _checksum
from runtime.growth_blueprint_deliverable_worker import (
    GrowthBlueprintDeliverableWorker,
    GrowthBlueprintDeliverableWorkerError,
    build_growth_blueprint_deliverable_worker,
)
from runtime.workflow_quality import growth_blueprint_deliverable_quality_gate
from tests.test_deliverable_production import artifact


class CountingRenderer(FakePresentationRenderer):
    def __init__(self) -> None:
        self.calls = 0

    def render(self, specification, output_dir):
        self.calls += 1
        return super().render(specification, output_dir)


def contract(source: dict, *, checksum: str | None = None) -> dict:
    return {
        "quality_accepted_growth_blueprint": source,
        "blueprint_identity": {
            "artifact_id": "artifact-northstar-approved-v1",
            "version": 1,
            "checksum": checksum or _checksum(source),
        },
        "client_context": {"name": "Northstar Test Co"},
        "workflow_context": {
            "workflow_id": "growth_blueprint_deliverable_production",
            "stage_id": "produce_growth_blueprint_deliverable",
            "workspace_id": "northstar-test-workspace",
            "client_id": "northstar-test-co",
            "run_id": "northstar-test-blueprint-deliverable-v1",
        },
    }


class GrowthBlueprintDeliverableWorkerTests(unittest.TestCase):
    def test_produces_review_only_deliverable_and_replays_without_rerendering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            renderer = CountingRenderer()
            worker = GrowthBlueprintDeliverableWorker(
                renderer=renderer,
                store=FileDeliverableStore(root / "records"),
                output_root=root / "outputs",
            )
            source = artifact()

            first = worker(contract(source))
            replay = worker(contract(source))

            self.assertTrue(growth_blueprint_deliverable_quality_gate(first)["passed"])
            self.assertFalse(first["external_action_taken"])
            self.assertFalse(first["publication_authorised"])
            self.assertFalse(first["delivery_authorised"])
            self.assertFalse(first["replay"])
            self.assertTrue(replay["replay"])
            self.assertEqual(renderer.calls, 1)
            self.assertTrue(Path(first["editable_pptx"]).is_file())
            self.assertTrue(Path(first["review_pdf"]).is_file())

    def test_rejects_blueprint_whose_content_no_longer_matches_approved_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            worker = GrowthBlueprintDeliverableWorker(
                renderer=FakePresentationRenderer(),
                store=FileDeliverableStore(root / "records"),
                output_root=root / "outputs",
            )
            with self.assertRaisesRegex(GrowthBlueprintDeliverableWorkerError, "checksum"):
                worker(contract(artifact(), checksum="0" * 64))

    def test_client_scopes_do_not_share_deliverable_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            renderer = CountingRenderer()
            worker = GrowthBlueprintDeliverableWorker(
                renderer=renderer,
                store=FileDeliverableStore(root / "records"),
                output_root=root / "outputs",
            )
            source = artifact()
            first = contract(source)
            second = contract(source)
            second["workflow_context"] = {
                **second["workflow_context"],
                "client_id": "northstar-test-co-two",
                "run_id": "northstar-test-blueprint-deliverable-v2",
            }

            worker(first)
            worker(second)

            self.assertEqual(renderer.calls, 2)

    def test_factory_is_disabled_by_default_and_fails_closed_when_misconfigured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(build_growth_blueprint_deliverable_worker(temporary, {}))
            with self.assertRaisesRegex(GrowthBlueprintDeliverableWorkerError, "paths are unavailable"):
                build_growth_blueprint_deliverable_worker(
                    temporary,
                    {"NARRATIIVE_DOCUMENT_WORKER_MODE": "local_artifact_tool"},
                )


if __name__ == "__main__":
    unittest.main()
