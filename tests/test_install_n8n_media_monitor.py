from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.install_n8n_media_monitor import WORKFLOW_ID, install, workflow_definition
from tests.test_install_n8n_meta_oauth_callback import database


class MediaMonitorWorkflowTests(unittest.TestCase):
    def test_workflow_has_daily_weekly_read_only_calls(self):
        nodes, connections = workflow_definition()
        rendered = json.dumps(nodes)
        self.assertIn("15 7 * * *", rendered)
        self.assertIn("30 7 * * 1", rendered)
        self.assertIn("http://127.0.0.1:8790/media/monitor", rendered)
        self.assertIn("TONY_BRIDGE_TOKEN", rendered)
        self.assertNotIn("request_id: ={{", rendered)
        self.assertIn("Daily Media Monitor", connections)
        self.assertIn("Weekly Media Monitor", connections)

    def test_install_is_idempotent_and_does_not_persist_report_payloads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "database.sqlite"
            database(path)
            install(path, restart=False)
            result = install(path, restart=False)
            connection = sqlite3.connect(path)
            row = connection.execute(
                "SELECT active, triggerCount, settings FROM workflow_entity WHERE id = ?", (WORKFLOW_ID,)
            ).fetchone()
            count = connection.execute(
                "SELECT COUNT(*) FROM workflow_entity WHERE id = ?", (WORKFLOW_ID,)
            ).fetchone()[0]
            connection.close()
            self.assertEqual(count, 1)
            self.assertEqual(row[:2], (1, 2))
            settings = json.loads(row[2])
            self.assertEqual(settings["saveDataErrorExecution"], "none")
            self.assertEqual(settings["saveDataSuccessExecution"], "none")
            self.assertFalse(settings["saveManualExecutions"])
            self.assertFalse(result["execution_data_persisted"])


if __name__ == "__main__":
    unittest.main()
