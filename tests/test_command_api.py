import io
import json
import tempfile
import unittest
from pathlib import Path

from runtime.command_api import CommandError, RuntimeCommandAPI
from runtime.composition import compose_local_runtime
from runtime.wsgi_api import RuntimeWSGIApp


class CommandAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        (self.repo / "workflow_definitions").mkdir(parents=True)
        (self.repo / "workflow_definitions" / "test.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "workflow_id": "test_pipeline",
                    "stages": [
                        {
                            "stage_id": "research",
                            "agent_ref": "agents/research.md",
                            "required_inputs": ["client_inputs"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.runtime = compose_local_runtime(self.root / "state", self.repo)
        self.api = RuntimeCommandAPI(self.runtime)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_get_list_and_dispatch(self):
        created = self.api.handle(
            {
                "command": "runs.create",
                "run_id": "run-1",
                "definition_path": "workflow_definitions/test.json",
                "available_inputs": ["client_inputs"],
            }
        )
        self.assertTrue(created["ok"])
        self.assertEqual(created["data"]["current_stage_id"], "research")

        listed = self.api.handle({"command": "runs.list"})
        self.assertEqual(listed["data"]["run_ids"], ["run-1"])

        fetched = self.api.handle({"command": "runs.get", "run_id": "run-1"})
        self.assertEqual(fetched["data"]["run_id"], "run-1")

        dispatched = self.api.handle(
            {
                "command": "stages.dispatch",
                "run_id": "run-1",
                "client_id": "rave",
            }
        )
        self.assertEqual(dispatched["data"]["stage_id"], "research")
        self.assertEqual(dispatched["data"]["payload"]["client_id"], "rave")

        job = self.api.handle({"command": "jobs.get", "job_id": dispatched["data"]["job_id"]})
        self.assertEqual(job["data"]["status"], "pending")

    def test_unsafe_definition_path_is_rejected(self):
        with self.assertRaises(CommandError) as error:
            self.api.handle(
                {
                    "command": "runs.create",
                    "run_id": "run-1",
                    "definition_path": "../outside.json",
                    "available_inputs": [],
                }
            )
        self.assertEqual(error.exception.code, "unsafe_path")

    def test_unknown_command_is_not_found(self):
        with self.assertRaises(CommandError) as error:
            self.api.handle({"command": "system.destroy"})
        self.assertEqual(error.exception.status, 404)

    def test_wsgi_gateway_returns_structured_response(self):
        app = RuntimeWSGIApp(self.api)
        request = json.dumps({"command": "health"}).encode("utf-8")
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        body = b"".join(
            app(
                {
                    "REQUEST_METHOD": "POST",
                    "PATH_INFO": "/commands",
                    "CONTENT_LENGTH": str(len(request)),
                    "wsgi.input": io.BytesIO(request),
                },
                start_response,
            )
        )
        payload = json.loads(body)
        self.assertEqual(captured["status"], "200 OK")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "ok")

    def test_wsgi_gateway_hides_internal_errors(self):
        app = RuntimeWSGIApp(self.api)
        request = b"not-json"
        captured = {}

        def start_response(status, headers):
            captured["status"] = status

        body = b"".join(
            app(
                {
                    "REQUEST_METHOD": "POST",
                    "PATH_INFO": "/commands",
                    "CONTENT_LENGTH": str(len(request)),
                    "wsgi.input": io.BytesIO(request),
                },
                start_response,
            )
        )
        payload = json.loads(body)
        self.assertEqual(captured["status"], "400 Bad Request")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "invalid_json")


if __name__ == "__main__":
    unittest.main()
