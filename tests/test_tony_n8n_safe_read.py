from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from runtime.tony_dispatch_adapters import _N8NReadDispatcher, build_http_dispatchers


class TonyN8NSafeReadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "database.sqlite"
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                '''
                CREATE TABLE workflow_entity (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    active INTEGER NOT NULL,
                    nodes TEXT,
                    connections TEXT,
                    "createdAt" TEXT NOT NULL,
                    "updatedAt" TEXT NOT NULL,
                    "isArchived" INTEGER NOT NULL,
                    "versionCounter" INTEGER NOT NULL
                )
                '''
            )
            connection.executemany(
                '''
                INSERT INTO workflow_entity
                    (id, name, active, nodes, connections, "createdAt", "updatedAt", "isArchived", "versionCounter")
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                [
                    ("wf-live", "Narratiive Lead Intake", 1, "SECRET NODE DATA", "SECRET CONNECTION DATA", "2026-01-01", "2026-09-16", 0, 4),
                    ("wf-archived", "Old Narratiive Workflow", 0, "ARCHIVED", "ARCHIVED", "2025-01-01", "2025-02-01", 1, 2),
                ],
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self):
        self.temporary.cleanup()

    def test_returns_only_bounded_non_archived_workflow_metadata(self):
        result = _N8NReadDispatcher(self.database)(
            {
                "execution_mode": "autonomous_read",
                "operation": "list",
                "target": {"query": "Lead", "max_results": 5},
            }
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(result["record_ids"], ["wf-live"])
        self.assertEqual(result["workflows"][0]["name"], "Narratiive Lead Intake")
        self.assertNotIn("nodes", result["workflows"][0])
        self.assertNotIn("connections", result["workflows"][0])
        self.assertNotIn("SECRET", str(result))

    def test_dispatcher_is_registered_only_for_explicit_read_only_mode(self):
        disabled = build_http_dispatchers({"TONY_N8N_DATABASE_PATH": str(self.database)})
        enabled = build_http_dispatchers(
            {
                "TONY_DISPATCH_N8N_MODE": "local_sqlite",
                "TONY_N8N_DATABASE_PATH": str(self.database),
            }
        )
        self.assertNotIn("n8n", disabled)
        self.assertIn("n8n", enabled)


if __name__ == "__main__":
    unittest.main()
