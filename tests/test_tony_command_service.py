from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.execution_journal import ExecutionJournal
from runtime.progress_engine import RepositoryProgressEngine
from runtime.repository_validator import GrowthObjectValidator
from runtime.tony_command_service import TonyCommandService


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
    roots = {
        (record["client_id"], record["campaign_id"]): record
        for record in records
        if record["object_type"] == "growth_specification"
    }
    for record in records:
        if record["object_type"] == "growth_specification":
            continue
        roots[(record["client_id"], record["campaign_id"])]["child_object_ids"].append(record["id"])
    return records


class TonyCommandServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = GrowthObjectValidator.from_path(SCHEMA_PATH)
        cls.progress_engine = RepositoryProgressEngine(cls.validator)
        cls.service = TonyCommandService(cls.progress_engine)

    def test_status_returns_repository_snapshot(self):
        response = self.service.execute("/status", [object_record(status="approved")])
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["campaign_count"], 1)
        self.assertEqual(response.data["campaigns"][0]["current_stage"], "growth_blueprint")

    def test_client_command_supports_case_insensitive_partial_match(self):
        response = self.service.execute("/client rave", [object_record(status="approved")])
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["client_name"], "Rave Coffee")

    def test_client_command_requires_an_argument(self):
        response = self.service.execute("/client", [])
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "missing_argument")

    def test_clients_aggregates_campaigns(self):
        records = [
            object_record(status="approved"),
            object_record(status="approved", campaign_id="retention", campaign_name="Retention"),
        ]
        response = self.service.execute("/clients", records)
        self.assertEqual(response.data["clients"][0]["campaign_count"], 2)

    def test_continue_prioritises_blocked_campaign(self):
        blocked = object_record(status="approved", approved_by=None, approved_at=None)
        healthy = object_record(
            status="approved",
            client_id="maeving",
            client_name="Maeving",
            campaign_id="launch",
        )
        response = self.service.execute("/continue", [healthy, blocked])
        self.assertEqual(response.status, "blocked")
        self.assertEqual(response.data["primary"]["client_id"], "rave")
        self.assertIn("missing_approval", response.data["primary"]["blocker_codes"])

    def test_health_exposes_machine_readable_validation(self):
        response = self.service.execute("/health", [object_record()])
        self.assertEqual(response.status, "healthy")
        self.assertEqual(response.data["validation"]["objects_validated"], 1)
        self.assertIsNone(response.data["execution_journal"])

    def test_history_requires_configured_journal(self):
        response = self.service.execute("/history", [])
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "journal_unavailable")

    def test_history_filters_execution_records(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ExecutionJournal(directory)
            journal.append(
                decision_id="decision-rave-1",
                workspace_id="narratiive",
                client_id="rave",
                action="generate_campaign_world",
                rationale="Growth Blueprint is approved",
                actor="claude",
                status="selected",
            )
            journal.append(
                decision_id="decision-maeving-1",
                workspace_id="narratiive",
                client_id="maeving",
                action="generate_blueprint",
                rationale="Research is complete",
                actor="claude",
                status="selected",
            )
            service = TonyCommandService(self.progress_engine, journal)
            response = service.execute("/history rave", [])
            self.assertEqual(response.status, "healthy")
            self.assertEqual(len(response.data["records"]), 1)
            self.assertEqual(response.data["records"][0]["decision_id"], "decision-rave-1")

    def test_explain_reconstructs_decision_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ExecutionJournal(directory)
            journal.append(
                decision_id="decision-rave-1",
                workspace_id="narratiive",
                client_id="rave",
                action="generate_campaign_world",
                rationale="Growth Blueprint is approved",
                actor="claude",
                status="selected",
                repository_revision="abc123",
            )
            journal.append(
                decision_id="decision-rave-1",
                workspace_id="narratiive",
                client_id="rave",
                action="generate_campaign_world",
                rationale="Growth Blueprint is approved",
                actor="claude",
                status="completed",
                repository_revision="abc123",
                artifacts=("clients/rave/campaign-world.md",),
            )
            service = TonyCommandService(self.progress_engine, journal)
            response = service.execute("/explain decision-rave-1", [])
            self.assertEqual(response.status, "completed")
            self.assertEqual(response.data["actor"], "claude")
            self.assertEqual(len(response.data["timeline"]), 2)
            self.assertEqual(response.data["artifacts"], ["clients/rave/campaign-world.md"])

    def test_explain_requires_decision_id(self):
        with tempfile.TemporaryDirectory() as directory:
            service = TonyCommandService(self.progress_engine, ExecutionJournal(directory))
            response = service.execute("/explain", [])
            self.assertEqual(response.status, "error")
            self.assertEqual(response.data["error_code"], "missing_argument")

    def test_health_verifies_execution_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = ExecutionJournal(directory)
            journal.append(
                decision_id="decision-rave-1",
                workspace_id="narratiive",
                client_id="rave",
                action="generate_campaign_world",
                rationale="Growth Blueprint is approved",
                actor="claude",
                status="selected",
            )
            service = TonyCommandService(self.progress_engine, journal)
            response = service.execute("/health", [object_record()])
            self.assertTrue(response.data["execution_journal"]["ok"])
            self.assertEqual(response.data["execution_journal"]["records"], 1)

    def test_unsupported_command_is_rejected(self):
        response = self.service.execute("/invent", [])
        self.assertEqual(response.status, "error")
        self.assertEqual(response.data["error_code"], "unsupported_command")

    def test_response_is_json_compatible(self):
        response = self.service.execute("what_next", [])
        payload = response.to_dict()
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["data"]["next_actions"], [])


if __name__ == "__main__":
    unittest.main()
