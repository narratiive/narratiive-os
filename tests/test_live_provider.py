import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from runtime.composition import compose_workspace_runtime
from runtime.definitions import StageDefinition, WorkflowDefinition
from runtime.live_provider import EnvironmentTextProviderClient, LiveTextProviderConfig
from runtime.models import StageStatus
from runtime.provider_routing import (
    CostClass,
    LatencyClass,
    ModelCapabilities,
    ModelRouter,
    ProviderAvailability,
    ProviderCapabilityRegistry,
    ProviderHealthRecord,
    ProviderHealthRegistry,
    ProviderModelRecord,
    RouteTarget,
    RoutingPolicy,
)
from runtime.workspaces import Workspace


class LiveTextHandler(BaseHTTPRequestHandler):
    response_payload = {
        "choices": [
            {"message": {"content": "# Completed Research\n\nLive evidence."}}
        ]
    }
    received_headers = {}
    received_body = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received_headers = dict(self.headers.items())
        type(self).received_body = json.loads(self.rfile.read(length).decode("utf-8"))
        payload = json.dumps(type(self).response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


class FailIfCalledProvider:
    def generate(self, package):
        raise AssertionError("unavailable primary provider must not be called")


class LiveProviderIntegrationTests(unittest.TestCase):
    endpoint_env = "NARRATIIVE_TEST_LIVE_ENDPOINT"
    api_key_env = "NARRATIIVE_TEST_LIVE_API_KEY"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        (self.repo / "agents").mkdir(parents=True)
        (self.repo / "agents" / "research.md").write_text(
            """# Research Agent
<!-- AI_AGENT_ID: research_analyst -->
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
        self.workspace = Workspace("rave", "rave", "RAVE")
        self.runtime = compose_workspace_runtime(
            self.root / "state",
            self.repo,
            self.workspace,
        )
        definition = WorkflowDefinition(
            workflow_id="test_pipeline",
            stages=(
                StageDefinition("research", "agents/research.md", ("client_inputs",)),
            ),
        )
        self.runtime.run_service.create_run(definition, "run-1", {"client_inputs"})
        self.runtime.dispatch_service.enqueue_current_stage(
            "run-1",
            context={"workspace_id": "rave"},
        )
        self.primary = RouteTarget("primary", "reasoning-v1")
        self.live = RouteTarget("live-text", "text-v1")
        capabilities = ModelCapabilities(
            reasoning=True,
            long_context=True,
            structured_output=True,
            vision=False,
            tool_use=False,
            latency_class=LatencyClass.STANDARD,
            cost_class=CostClass.MEDIUM,
        )
        self.capability_registry = ProviderCapabilityRegistry(
            (
                ProviderModelRecord("primary", "reasoning-v1", capabilities),
                ProviderModelRecord("live-text", "text-v1", capabilities),
            )
        )
        self.health = ProviderHealthRegistry(
            (
                ProviderHealthRecord(
                    self.primary,
                    ProviderAvailability.UNAVAILABLE,
                    "scheduled_maintenance",
                ),
                ProviderHealthRecord(self.live, ProviderAvailability.AVAILABLE),
            )
        )
        self.server = HTTPServer(("127.0.0.1", 0), LiveTextHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        LiveTextHandler.response_payload = {
            "choices": [
                {"message": {"content": "# Completed Research\n\nLive evidence."}}
            ]
        }
        LiveTextHandler.received_headers = {}
        LiveTextHandler.received_body = {}

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def _router(self) -> ModelRouter:
        return ModelRouter(
            capabilities=self.capability_registry,
            health=self.health,
            policies=(
                RoutingPolicy(
                    policy_id="rave-research",
                    version="2026-07-13",
                    workspace_id="rave",
                    stage_id="research",
                    specialist_id="research_analyst",
                    primary=self.primary,
                    fallbacks=(self.live,),
                ),
            ),
        )

    def _client(self) -> EnvironmentTextProviderClient:
        return EnvironmentTextProviderClient(
            LiveTextProviderConfig(
                provider_id=self.live.provider_id,
                model_id=self.live.model_id,
                endpoint_env=self.endpoint_env,
                api_key_env=self.api_key_env,
                timeout_seconds=1,
            )
        )

    def _worker(self):
        return self.runtime.routed_worker(
            worker_id="worker-live",
            router=self._router(),
            providers={
                self.primary: FailIfCalledProvider(),
                self.live: self._client(),
            },
            output_type_by_stage={"research": "completed_research"},
        )

    def test_live_stage_uses_fallback_and_records_auditable_routing(self) -> None:
        secret = "test-secret-that-must-not-persist"
        endpoint = f"http://127.0.0.1:{self.server.server_port}/chat/completions"
        with patch.dict(
            os.environ,
            {self.endpoint_env: endpoint, self.api_key_env: secret},
            clear=False,
        ):
            job = self._worker().run_once()

        self.assertIsNotNone(job)
        state = self.runtime.run_repository.load("run-1")
        self.assertEqual(state.stage("research").status, StageStatus.COMPLETED)
        artifact = state.stage("research").output_artifacts[0]
        self.assertEqual(
            Path(artifact.location).read_text(encoding="utf-8"),
            "# Completed Research\n\nLive evidence.",
        )
        self.assertEqual(
            LiveTextHandler.received_headers["Authorization"],
            f"Bearer {secret}",
        )
        self.assertEqual(LiveTextHandler.received_body["model"], "text-v1")

        result_routing = self.runtime.dispatch_queue.get(job.job_id).result["routing"]
        self.assertEqual(result_routing["provider_id"], "live-text")
        self.assertEqual(result_routing["model_id"], "text-v1")
        self.assertEqual(result_routing["policy_version"], "2026-07-13")
        self.assertEqual(result_routing["fallback_index"], 1)
        self.assertIn("primary/reasoning-v1:unavailable", result_routing["routing_reason"])
        completed = [
            event
            for event in self.runtime.event_log.read("run-1")
            if event.event_type == "dispatch.completed"
        ][0]
        self.assertEqual(completed.payload["routing"], result_routing)
        persisted_runtime = "\n".join(
            path.read_text(encoding="utf-8")
            for path in self.runtime.paths.root.rglob("*")
            if path.is_file()
        )
        self.assertNotIn(secret, persisted_runtime)

    def test_missing_credentials_requests_retry_without_corrupting_state(self) -> None:
        endpoint = f"http://127.0.0.1:{self.server.server_port}/chat/completions"
        with patch.dict(os.environ, {self.endpoint_env: endpoint}, clear=False):
            os.environ.pop(self.api_key_env, None)
            job = self._worker().run_once()

        state = self.runtime.run_repository.load("run-1")
        self.assertEqual(state.stage("research").status, StageStatus.RETRY_REQUIRED)
        queued = self.runtime.dispatch_queue.get(job.job_id)
        self.assertIn("ProviderConfigurationError", queued.error)
        self.assertIn(self.api_key_env, queued.error)

    def test_malformed_live_output_requests_retry(self) -> None:
        LiveTextHandler.response_payload = {"choices": []}
        endpoint = f"http://127.0.0.1:{self.server.server_port}/chat/completions"
        with patch.dict(
            os.environ,
            {self.endpoint_env: endpoint, self.api_key_env: "temporary-secret"},
            clear=False,
        ):
            job = self._worker().run_once()

        state = self.runtime.run_repository.load("run-1")
        self.assertEqual(state.stage("research").status, StageStatus.RETRY_REQUIRED)
        self.assertIn("ProviderTransportError", self.runtime.dispatch_queue.get(job.job_id).error)

    def test_live_timeout_requests_retry(self) -> None:
        endpoint = f"http://127.0.0.1:{self.server.server_port}/chat/completions"
        with patch.dict(
            os.environ,
            {self.endpoint_env: endpoint, self.api_key_env: "temporary-secret"},
            clear=False,
        ), patch("runtime.live_provider.urlopen", side_effect=TimeoutError):
            job = self._worker().run_once()

        state = self.runtime.run_repository.load("run-1")
        self.assertEqual(state.stage("research").status, StageStatus.RETRY_REQUIRED)
        self.assertIn("ProviderTransportError", self.runtime.dispatch_queue.get(job.job_id).error)


if __name__ == "__main__":
    unittest.main()
