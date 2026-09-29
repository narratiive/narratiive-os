from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.install_n8n_tiktok_oauth_callback import WORKFLOW_ID, install, workflow_definition


def database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
    CREATE TABLE workflow_entity (id TEXT PRIMARY KEY, name TEXT, active INTEGER, nodes TEXT, connections TEXT,
      settings TEXT, staticData TEXT, pinData TEXT, versionId TEXT, triggerCount INTEGER, meta TEXT,
      parentFolderId TEXT, createdAt TEXT, updatedAt TEXT, isArchived INTEGER, versionCounter INTEGER,
      description TEXT, activeVersionId TEXT);
    CREATE TABLE workflow_history (versionId TEXT, workflowId TEXT, authors TEXT, createdAt TEXT, updatedAt TEXT,
      nodes TEXT, connections TEXT, name TEXT, autosaved INTEGER, description TEXT);
    CREATE TABLE shared_workflow (workflowId TEXT, projectId TEXT, role TEXT, createdAt TEXT, updatedAt TEXT);
    INSERT INTO shared_workflow VALUES ('s7TvzzAsJRKLRDU7', 'project-one', 'workflow:owner', 'now', 'now');
    """)
    connection.commit()
    connection.close()


class TikTokOAuthWorkflowTests(unittest.TestCase):
    def test_definition_forwards_only_to_authenticated_loopback_and_never_persists(self):
        nodes, _ = workflow_definition()
        webhook, request, response = nodes
        self.assertEqual(webhook["parameters"]["httpMethod"], "GET")
        self.assertEqual(webhook["parameters"]["path"], "tiktok-media-oauth-callback")
        self.assertEqual(request["parameters"]["url"], "http://127.0.0.1:8790/oauth/tiktok/callback")
        self.assertIn("TONY_BRIDGE_TOKEN", request["parameters"]["jsonHeaders"])
        self.assertIn("auth_code", request["parameters"]["jsonBody"])
        self.assertEqual(response["type"], "n8n-nodes-base.respondToWebhook")

    def test_install_is_idempotent_and_disables_execution_data_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "database.sqlite"
            database(path)
            first = install(path, restart=False)
            second = install(path, restart=False)
            self.assertFalse(first["execution_data_persisted"])
            connection = sqlite3.connect(path)
            row = connection.execute("SELECT active, settings FROM workflow_entity WHERE id = ?", (WORKFLOW_ID,)).fetchone()
            count = connection.execute("SELECT COUNT(*) FROM workflow_entity WHERE id = ?", (WORKFLOW_ID,)).fetchone()[0]
            history = connection.execute("SELECT COUNT(*) FROM workflow_history WHERE workflowId = ?", (WORKFLOW_ID,)).fetchone()[0]
            connection.close()
            self.assertEqual(count, 1)
            self.assertEqual(history, 2)
            self.assertEqual(row[0], 1)
            settings = json.loads(row[1])
            self.assertEqual(settings["saveDataErrorExecution"], "none")
            self.assertEqual(settings["saveDataSuccessExecution"], "none")
            self.assertFalse(settings["saveManualExecutions"])
            self.assertTrue(second["read_only"])


if __name__ == "__main__":
    unittest.main()
