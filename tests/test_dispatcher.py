from __future__ import annotations

import unittest
from pathlib import Path

from runtime.dispatcher import TonyDispatcher
from runtime.progress_engine import RepositoryProgressEngine
from runtime.repository_validator import GrowthObjectValidator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "shared" / "growth-object.schema.json"


def object_record(
    object_type="growth_specification",
    status="draft",
    client_id="rave",
    client_name="Rave Coffee",
    campaign_id="launch",
    campaign_name="National Growth",
    **overrides,
):
    record = {
        "id": f"{object_type}:{client_id}:{campaign_id}",
        "object_type": object_type,
        "version": "1.0",
        "client_id": client_id,
        "client_name": client_name,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "status": status,
        "created_at": "2026-07-22T20:00:00Z",
        "updated_at": "2026-07-22T20:00:00Z",
        "created_by": "tony",
        "approved_by": None,
        "approved_at": None,
        "parent_object_id": None if object_type == "growth_specification" else f"growth_specification:{client_id}:{campaign_id}",
        "source_object_ids": [],
        "child_object_ids": [],
        "repository_path": f"clients/{client_id}/{campaign_id}/{object_type}.json",
        "commit_sha": None,
    }
    if status in {"approved", "active", "superseded", "archived"}:
        record["approved_by"] = "matt"
        record["approved_at"] = "2026-07-22T21:00:00Z"
    record.update(overrides)
    return record


def reciprocal(records):
    root = next(record for record in records if record["object_type"] == "growth_specification")
    root["child_object_ids"] = [
        record["id"] for record in records if record["object_type"] != "growth_specification"
    ]
    return records


class TonyDispatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        validator = GrowthObjectValidator.from_path(SCHEMA_PATH)
        cls.dispatcher = TonyDispatcher(RepositoryProgressEngine(validator))

    def test_empty_repository_has_no_dispatch(self):
        self.assertIsNone(self.dispatcher.dispatch([]))

    def test_missing_blueprint_is_assigned_to_claude(self):
        decision = self.dispatcher.dispatch([object_record(status="approved")])
        self.assertEqual(decision.status, "ready")
        self.assertEqual(decision.stage, "growth_blueprint")
        self.assertEqual(decision.assigned_worker, "claude")

    def test_in_review_work_is_assigned_to_matt(self):
        records = reciprocal([
            object_record(status="approved"),
            object_record(object_type="growth_blueprint", status="in_review"),
        ])
        decision = self.dispatcher.dispatch(records)
        self.assertEqual(decision.assigned_worker, "matt")
        self.assertIn("approval", decision.reason.lower())

    def test_validation_error_refuses_dispatch(self):
        invalid = object_record(status="approved", approved_by=None, approved_at=None)
        decision = self.dispatcher.dispatch([invalid])
        self.assertEqual(decision.status, "blocked")
        self.assertIsNone(decision.assigned_worker)
        self.assertIn("missing_approval", decision.blocker_codes)

    def test_blocked_campaign_is_prioritised(self):
        blocked = object_record(status="approved", approved_by=None, approved_at=None)
        healthy = object_record(
            status="approved",
            client_id="maeving",
            client_name="Maeving",
            campaign_id="launch",
        )
        decision = self.dispatcher.dispatch([healthy, blocked])
        self.assertEqual(decision.client_id, "rave")
        self.assertEqual(decision.status, "blocked")

    def test_complete_cycle_returns_to_tony(self):
        stages = (
            "growth_specification",
            "growth_blueprint",
            "campaign_world",
            "creative_directors_bible",
            "production_pack",
            "asset_manifest",
            "performance_feedback",
        )
        records = reciprocal([object_record(object_type=stage, status="approved") for stage in stages])
        decision = self.dispatcher.dispatch(records)
        self.assertEqual(decision.assigned_worker, "tony")
        self.assertEqual(decision.action, "start the next Growth Specification cycle")

    def test_decision_is_json_compatible(self):
        decision = self.dispatcher.dispatch([object_record(status="approved")])
        payload = decision.to_dict()
        self.assertEqual(payload["assigned_worker"], "claude")
        self.assertEqual(payload["blocker_codes"], ())


if __name__ == "__main__":
    unittest.main()
