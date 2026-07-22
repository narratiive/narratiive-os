from __future__ import annotations

import json
import unittest
from pathlib import Path

from runtime.repository_validator import GrowthObjectValidator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "shared" / "growth-object.schema.json"


def object_record(**overrides):
    record = {
        "id": "growth-specification:rave:launch",
        "object_type": "growth_specification",
        "version": "1.0",
        "client_id": "rave",
        "client_name": "Rave Coffee",
        "campaign_id": "launch",
        "campaign_name": "National Growth",
        "status": "draft",
        "created_at": "2026-07-22T20:00:00Z",
        "updated_at": "2026-07-22T20:00:00Z",
        "created_by": "tony",
        "approved_by": None,
        "approved_at": None,
        "parent_object_id": None,
        "source_object_ids": [],
        "child_object_ids": [],
        "repository_path": "clients/rave/growth-specification.json",
        "commit_sha": None,
    }
    record.update(overrides)
    return record


class GrowthObjectValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = GrowthObjectValidator.from_path(SCHEMA_PATH)

    def test_schema_exposes_contract_values(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertIn("performance_feedback", self.validator.object_types)
        self.assertIn("approved", self.validator.lifecycle_statuses)

    def test_valid_root_and_child_pass(self):
        root = object_record(child_object_ids=["growth-blueprint:rave:launch"])
        child = object_record(
            id="growth-blueprint:rave:launch",
            object_type="growth_blueprint",
            parent_object_id=root["id"],
            repository_path="clients/rave/growth-blueprint.json",
        )
        report = self.validator.validate([root, child])
        self.assertEqual(report.status, "pass")
        self.assertEqual(report.objects_validated, 2)
        self.assertEqual(report.errors, ())

    def test_approved_object_requires_approval_metadata(self):
        report = self.validator.validate([object_record(status="approved")])
        self.assertEqual(report.status, "fail")
        self.assertEqual([item.code for item in report.errors].count("missing_approval"), 2)

    def test_child_requires_existing_parent(self):
        child = object_record(
            id="campaign-world:rave:launch",
            object_type="campaign_world",
            parent_object_id="growth-specification:rave:missing",
            repository_path="clients/rave/campaign-world.json",
        )
        report = self.validator.validate([child])
        self.assertIn("missing_parent_object", {item.code for item in report.errors})

    def test_duplicate_ids_fail(self):
        first = object_record()
        second = object_record(repository_path="clients/rave/duplicate.json")
        report = self.validator.validate([first, second])
        self.assertIn("duplicate_id", {item.code for item in report.errors})

    def test_missing_source_is_warning_not_failure(self):
        report = self.validator.validate([object_record(source_object_ids=["external:research:one"])])
        self.assertEqual(report.status, "pass")
        self.assertEqual(report.warnings[0].code, "missing_source_object")
        self.assertEqual(report.to_dict()["warnings"][0]["severity"], "warning")


if __name__ == "__main__":
    unittest.main()
