from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.install_n8n_campaign_learning_monitor import (
    REFERENCE_WORKFLOW_ID,
    WORKFLOW_ID,
    WORKFLOW_NAME,
    install,
    workflow_definition,
)


class InstallN8NCampaignLearningMonitorTests(unittest.TestCase):
    def _database(self, root: Path) -> Path:
        path = root / "database.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE workflow_entity (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, active INTEGER NOT NULL,
                nodes TEXT, connections TEXT, settings TEXT, staticData TEXT, pinData TEXT,
                versionId TEXT NOT NULL, triggerCount INTEGER DEFAULT 0, meta TEXT,
                parentFolderId TEXT, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
                isArchived INTEGER NOT NULL DEFAULT 0, versionCounter INTEGER NOT NULL DEFAULT 1,
                description TEXT, activeVersionId TEXT
            );
            CREATE TABLE workflow_history (
                versionId TEXT PRIMARY KEY, workflowId TEXT NOT NULL, authors TEXT NOT NULL,
                createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, nodes TEXT NOT NULL,
                connections TEXT NOT NULL, name TEXT, autosaved INTEGER NOT NULL,
                description TEXT
            );
            CREATE TABLE shared_workflow (
                workflowId TEXT NOT NULL, projectId TEXT NOT NULL, role TEXT NOT NULL,
                createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL,
                PRIMARY KEY (workflowId, projectId)
            );
            """
        )
        connection.execute(
            "INSERT INTO shared_workflow VALUES (?, 'project-1', 'workflow:owner', 'now', 'now')",
            (REFERENCE_WORKFLOW_ID,),
        )
        connection.commit()
        connection.close()
        return path

    def test_definition_is_an_hourly_authenticated_read_only_call(self) -> None:
        nodes, connections = workflow_definition()
        trigger, request = nodes

        self.assertEqual(trigger["parameters"]["rule"]["interval"][0]["hoursInterval"], 1)
        self.assertEqual(request["parameters"]["url"], "http://127.0.0.1:8790/workflow/control")
        self.assertIn("TONY_BRIDGE_TOKEN", request["parameters"]["jsonHeaders"])
        self.assertIn("campaign-learning-queue", request["parameters"]["jsonBody"])
        self.assertNotIn("sync-campaign-learning", json.dumps(nodes))
        self.assertIn("Hourly Campaign Learning", connections)

    def test_install_is_idempotent_and_preserves_one_active_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = self._database(Path(temporary))
            first = install(database, restart=False)
            second = install(database, restart=False)

            connection = sqlite3.connect(database)
            row = connection.execute(
                "SELECT name, active, triggerCount, versionCounter, nodes FROM workflow_entity WHERE id = ?",
                (WORKFLOW_ID,),
            ).fetchone()
            history_count = connection.execute(
                "SELECT count(*) FROM workflow_history WHERE workflowId = ?",
                (WORKFLOW_ID,),
            ).fetchone()[0]
            shared_count = connection.execute(
                "SELECT count(*) FROM shared_workflow WHERE workflowId = ?",
                (WORKFLOW_ID,),
            ).fetchone()[0]
            connection.close()

            self.assertEqual(row[:4], (WORKFLOW_NAME, 1, 1, 2))
            self.assertEqual(history_count, 2)
            self.assertEqual(shared_count, 1)
            self.assertNotEqual(first["version_id"], second["version_id"])
            self.assertTrue(first["read_only"])
            self.assertEqual(first["schedule"], "hourly")
            self.assertTrue(Path(first["backup"]).is_file())


if __name__ == "__main__":
    unittest.main()
