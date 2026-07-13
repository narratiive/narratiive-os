import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from runtime.composition import compose_local_runtime
from runtime.definitions import StageDefinition, WorkflowDefinition
from runtime.http_provider import HttpProviderConfig, ProviderTransportError
from runtime.models import StageStatus


class ProviderHandler(BaseHTTPRequestHandler):
    response_status = 200
    response_payload = {}
    received_headers = {}
    received_body = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received_headers = dict(self.headers.items())
        type(self).received_body = json.loads(self.rfile.read(length).decode("utf-8"))
        payload = json.dumps(type(self).response_payload).encode("utf-8")
        self.send_response(type(self).response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


class HttpRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        (self.repo / "agents").mkdir(parents=True)
        (self.repo / "agents" / "research.md").write_text(
            """# Research Agent
<!-- AI_AGENT_ID: research -->
<!-- AI_AGENT_VERSION: 1.0 -->
<!-- AI_INPUT_TYPE: client_inputs -->
<!-- AI_OUTPUT_TYPE: completed_research -->
## Purpose
Research supplied evidence.
## Inputs
Client inputs.
## Outputs
Completed research.
## Rules
Use supplied evidence only.
## Workflow
Validate, research, return.
## Failure Conditions
Fail when evidence is missing.
""",
            encoding="utf-8",
        )
        self.runtime = compose_local_runtime(self.root / "state", self.repo)
        definition = WorkflowDefinition(
            workflow_id="test_pipeline",
            stages=(StageDefinition("research", "agents/research.md", ("client_inputs",)),),
        )
        self.runtime.run_service.create_run(definition, "run-1", {"client_inputs"})
        self.runtime.dispatch_service.enqueue_current_stage("run-1")

        ProviderHandler.response_status = 200
        ProviderHandler.response_payload = {
            "job_id": "run-1--research",
            "run_id": "run-1",
            "stage_id": "research",
            "output_type": "completed_research",
            "content": "# Completed Research\n\nEvidence-backed findings.",
            "metadata": {"provider": "test"},
        }
        self.server = HTTPServer(("127.0.0.1", 0), ProviderHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_http_worker_executes_end_to_end(self):
        endpoint = f"http://127.0.0.1:{self.server.server_port}/execute"
        worker = self.runtime.http_worker(
            worker_id="worker-http",
            provider_config=HttpProviderConfig(endpoint=endpoint, bearer_token="secret"),
            output_type_by_stage={"research": "completed_research"},
        )
        job = worker.run_once()
        self.assertIsNotNone(job)
        state = self.runtime.run_repository.load("run-1")
        self.assertEqual(state.stage("research").status, StageStatus.COMPLETED)
        self.assertTrue((self.runtime.paths.artifacts / "run-1" / "research.md").exists())
        self.assertEqual(ProviderHandler.received_headers.get("Authorization"), "Bearer secret")
        self.assertEqual(ProviderHandler.received_body["stage_id"], "research")

    def test_invalid_provider_payload_becomes_retryable_failure(self):
        ProviderHandler.response_payload = {"not": "a provider response"}
        endpoint = f"http://127.0.0.1:{self.server.server_port}/execute"
        worker = self.runtime.http_worker(
            worker_id="worker-http",
            provider_config=HttpProviderConfig(endpoint=endpoint),
            output_type_by_stage={"research": "completed_research"},
        )
        job = worker.run_once()
        state = self.runtime.run_repository.load("run-1")
        self.assertEqual(state.stage("research").status, StageStatus.RETRY_REQUIRED)
        self.assertIn("ProviderTransportError", self.runtime.dispatch_queue.get(job.job_id).error)

    def test_http_config_rejects_non_http_endpoint(self):
        with self.assertRaises(ValueError):
            HttpProviderConfig(endpoint="file:///tmp/provider")

    def test_composition_requires_repository_directory(self):
        with self.assertRaises(ValueError):
            compose_local_runtime(self.root / "other-state", self.root / "missing")


if __name__ == "__main__":
    unittest.main()
