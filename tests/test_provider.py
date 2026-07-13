import tempfile
import unittest
from pathlib import Path

from runtime.dispatch import DispatchJob
from runtime.execution_package import ExecutionPackageBuilder
from runtime.provider import (
    ArtifactWriter,
    InvalidProviderResponse,
    ProviderExecutor,
    ProviderResponse,
    provider_response_from_json,
)


AGENT = """# Research Agent
<!-- AI_AGENT_ID: research_analyst -->
<!-- AI_AGENT_VERSION: 1.0 -->
## Purpose
Gather evidence.
## Inputs
Client inputs.
## Outputs
Research output.
## Rules
Do not invent.
## Workflow
Validate and deliver.
"""


class FakeProvider:
    def __init__(self, response: ProviderResponse) -> None:
        self.response = response

    def generate(self, package):
        return self.response


class ProviderAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "agents").mkdir()
        (self.root / "agents" / "research.md").write_text(AGENT, encoding="utf-8")
        self.builder = ExecutionPackageBuilder(
            self.root,
            {"research": "completed_research_inputs"},
        )
        self.writer = ArtifactWriter(
            self.root / "artifacts",
            {"completed_research_inputs": ".md"},
        )
        self.job = DispatchJob(
            "job-1",
            "run-1",
            "research",
            "agents/research.md",
            {"client": "Rave"},
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_provider_executor_writes_validated_artifact(self) -> None:
        response = ProviderResponse(
            job_id="job-1",
            run_id="run-1",
            stage_id="research",
            output_type="completed_research_inputs",
            content="# Research\nGrounded output.",
            metadata={"model": "fake-v1"},
        )
        executor = ProviderExecutor(
            package_builder=self.builder,
            provider=FakeProvider(response),
            artifact_writer=self.writer,
        )
        result = executor.execute(self.job)
        artifact = result.outputs[0]
        self.assertEqual(artifact.artifact_type, "completed_research_inputs")
        self.assertTrue(artifact.checksum)
        self.assertEqual(Path(artifact.location).read_text(encoding="utf-8"), response.content)
        self.assertEqual(result.next_available_inputs, ("completed_research_inputs",))

    def test_rejects_mismatched_provider_response(self) -> None:
        response = ProviderResponse(
            job_id="wrong-job",
            run_id="run-1",
            stage_id="research",
            output_type="completed_research_inputs",
            content="output",
        )
        executor = ProviderExecutor(
            package_builder=self.builder,
            provider=FakeProvider(response),
            artifact_writer=self.writer,
        )
        with self.assertRaises(InvalidProviderResponse):
            executor.execute(self.job)
        self.assertFalse((self.root / "artifacts" / "run-1" / "research.md").exists())

    def test_rejects_wrong_output_type(self) -> None:
        response = ProviderResponse(
            job_id="job-1",
            run_id="run-1",
            stage_id="research",
            output_type="campaign_world",
            content="output",
        )
        executor = ProviderExecutor(
            package_builder=self.builder,
            provider=FakeProvider(response),
            artifact_writer=self.writer,
        )
        with self.assertRaises(InvalidProviderResponse):
            executor.execute(self.job)

    def test_parses_json_response(self) -> None:
        response = provider_response_from_json(
            '{"job_id":"job-1","run_id":"run-1","stage_id":"research",'
            '"output_type":"completed_research_inputs","content":"done"}'
        )
        self.assertEqual(response.content, "done")

    def test_rejects_non_json_response(self) -> None:
        with self.assertRaises(InvalidProviderResponse):
            provider_response_from_json("not-json")


if __name__ == "__main__":
    unittest.main()
