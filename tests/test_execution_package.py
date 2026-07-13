import tempfile
import unittest
from pathlib import Path

from runtime.agent_manifest import parse_agent_manifest
from runtime.dispatch import DispatchJob
from runtime.execution_package import ExecutionPackageBuilder
from runtime.models import ArtifactRef


AGENT_TEXT = """# Research Agent

<!-- AI_AGENT_ID: research_analyst -->
<!-- AI_AGENT_VERSION: 2.1 -->

## Purpose
Gather and structure evidence.

## Inputs
Client material.

## Outputs
Research handoff.

## Rules
Do not invent evidence.

## Workflow
Validate, gather, structure, hand off.
"""


class AgentManifestTests(unittest.TestCase):
    def test_parses_metadata_and_sections(self) -> None:
        manifest = parse_agent_manifest(AGENT_TEXT, source_path="agents/research.md")
        self.assertEqual(manifest.agent_id, "research_analyst")
        self.assertEqual(manifest.version, "2.1")
        self.assertEqual(manifest.section("Purpose"), "Gather and structure evidence.")

    def test_rejects_missing_required_sections(self) -> None:
        with self.assertRaises(ValueError):
            parse_agent_manifest("<!-- AI_AGENT_ID: broken -->\n## Purpose\nOnly one section")


class ExecutionPackageBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "agents").mkdir()
        (self.root / "agents" / "research.md").write_text(AGENT_TEXT, encoding="utf-8")
        self.builder = ExecutionPackageBuilder(
            self.root,
            {"research": "completed_research_inputs"},
        )
        self.job = DispatchJob(
            job_id="job-1",
            run_id="run-1",
            stage_id="research",
            agent_ref="agents/research.md",
            payload={"client_name": "Rave"},
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_builds_deterministic_provider_neutral_package(self) -> None:
        source = ArtifactRef("source-1", "client_inputs", "inputs/rave.json")
        package = self.builder.build(self.job, input_artifacts=[source])
        self.assertEqual(package.agent_id, "research_analyst")
        self.assertEqual(package.expected_output_type, "completed_research_inputs")
        self.assertEqual(package.context["client_name"], "Rave")
        self.assertEqual(package.input_artifacts[0]["artifact_id"], "source-1")
        self.assertEqual(package.memory_records, ())
        self.assertIn("Do not invent evidence", package.instructions)
        self.assertEqual(package.to_dict()["schema_version"], 1)

    def test_rejects_missing_output_contract(self) -> None:
        builder = ExecutionPackageBuilder(self.root, {})
        with self.assertRaises(ValueError):
            builder.build(self.job)

    def test_rejects_agent_path_outside_repository(self) -> None:
        unsafe = DispatchJob("job-2", "run-1", "research", "../outside.md", {})
        with self.assertRaises(ValueError):
            self.builder.build(unsafe)


if __name__ == "__main__":
    unittest.main()
