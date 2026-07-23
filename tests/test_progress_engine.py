from __future__ import annotations

import unittest
from pathlib import Path

from runtime.progress_engine import CANONICAL_SEQUENCE, RepositoryProgressEngine
from runtime.repository_validator import GrowthObjectValidator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "shared" / "growth-object.schema.json"


def object_record(object_type="growth_specification", status="draft", **overrides):
    record = {
        "id": f"{object_type}:rave:launch",
        "object_type": object_type,
        "version": "1.0",
        "client_id": "rave",
        "client_name": "Rave Coffee",
        "campaign_id": "launch",
        "campaign_name": "National Growth",
        "status": status,
        "created_at": "2026-07-22T20:00:00Z",
        "updated_at": "2026-07-22T20:00:00Z",
        "created_by": "tony",
        "approved_by": None,
        "approved_at": None,
        "parent_object_id": None if object_type == "growth_specification" else "growth_specification:rave:launch",
        "source_object_ids": [],
        "child_object_ids": [],
        "repository_path": f"clients/rave/{object_type}.json",
        "commit_sha": None,
    }
    if status in {"approved", "active", "superseded", "archived"}:
        record["approved_by"] = "matt"
        record["approved_at"] = "2026-07-22T21:00:00Z"
    record.update(overrides)
    return record


def reciprocal(records):
    root = next(record for record in records if record["object_type"] == "growth_specification")
    root["child_object_ids"] = [record["id"] for record in records if record is not root]
    return records


class RepositoryProgressEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        validator = GrowthObjectValidator.from_path(SCHEMA_PATH)
        cls.engine = RepositoryProgressEngine(validator)

    def test_empty_repository_is_reported(self):
        snapshot = self.engine.build_snapshot([])
        self.assertEqual(snapshot.status, "empty")
        self.assertEqual(snapshot.campaigns, ())

    def test_missing_next_object_is_actionable(self):
        root = object_record(status="approved")
        snapshot = self.engine.build_snapshot([root])
        campaign = snapshot.campaigns[0]
        self.assertEqual(campaign.current_stage, "growth_blueprint")
        self.assertEqual(campaign.current_status, "missing")
        self.assertEqual(campaign.next_action, "create growth_blueprint")
        self.assertEqual(campaign.completion_percent, 14)

    def test_in_review_object_becomes_current_action(self):
        records = reciprocal([
            object_record(status="approved"),
            object_record("growth_blueprint", status="in_review"),
        ])
        snapshot = self.engine.build_snapshot(records)
        campaign = snapshot.campaigns[0]
        self.assertEqual(campaign.current_stage, "growth_blueprint")
        self.assertEqual(campaign.next_action, "review and approve growth_blueprint")
        self.assertEqual(campaign.health, "on_track")

    def test_validation_errors_block_campaign(self):
        root = object_record(status="approved", approved_by=None, approved_at=None)
        snapshot = self.engine.build_snapshot([root])
        campaign = snapshot.campaigns[0]
        self.assertEqual(snapshot.status, "blocked")
        self.assertEqual(campaign.health, "blocked")
        self.assertIn("missing_approval", campaign.blocker_codes)

    def test_complete_cycle_points_to_next_specification(self):
        records = reciprocal([
            object_record(stage, status="approved")
            for stage in CANONICAL_SEQUENCE
        ])
        snapshot = self.engine.build_snapshot(records)
        campaign = snapshot.campaigns[0]
        self.assertEqual(snapshot.status, "healthy")
        self.assertEqual(campaign.completion_percent, 100)
        self.assertEqual(campaign.next_action, "start the next Growth Specification cycle")

    def test_snapshot_is_machine_readable(self):
        snapshot = self.engine.build_snapshot([object_record()])
        payload = snapshot.to_dict()
        self.assertEqual(payload["campaigns"][0]["client_id"], "rave")
        self.assertIn("validation", payload)


if __name__ == "__main__":
    unittest.main()
