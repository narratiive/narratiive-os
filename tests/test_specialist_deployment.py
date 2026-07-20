import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runtime.prompt_registry import FilePromptRegistry
from runtime.specialists import SpecialistCatalog, deployment_manifest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = "workflows/growth_blueprint_pipeline.json"


class SpecialistDeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = FilePromptRegistry(Path(self.tmp.name) / "prompts")
        self.catalog = SpecialistCatalog(REPOSITORY_ROOT, WORKFLOW_PATH)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_deploys_and_activates_every_specialist(self) -> None:
        deployments = self.catalog.deploy(self.registry)
        self.assertEqual(len(deployments), 5)
        self.assertEqual(
            [item.stage_id for item in deployments],
            [
                "research_analyst",
                "strategy_director",
                "campaign_world_generator",
                "creative_director",
                "quality_reviewer",
            ],
        )
        for item in deployments:
            active = self.registry.active(item.prompt_id)
            self.assertEqual(active.version, item.prompt_version)
            self.assertEqual(active.checksum, item.prompt_checksum)

    def test_redeploying_unchanged_specialists_is_idempotent(self) -> None:
        first = self.catalog.deploy(self.registry)
        second = self.catalog.deploy(self.registry)
        self.assertEqual(first, second)
        for item in first:
            self.assertEqual(len(self.registry.history(item.prompt_id)), 1)

    def test_deployment_manifest_is_machine_readable(self) -> None:
        payload = deployment_manifest(self.catalog.deploy(self.registry))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(len(payload["specialists"]), 5)
        self.assertEqual(
            payload["specialists"][-1]["output_type"],
            "completed_quality_review",
        )

    def test_rejects_workflow_outside_repository(self) -> None:
        outside = Path(self.tmp.name) / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            SpecialistCatalog(REPOSITORY_ROOT, outside)

    def test_script_and_module_invocations_produce_the_same_deployment(self) -> None:
        registry_root = Path(self.tmp.name) / "cli-prompts"
        script_output = Path(self.tmp.name) / "script-deployment.json"
        module_output = Path(self.tmp.name) / "module-deployment.json"
        common_arguments = [
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--registry-root",
            str(registry_root),
        ]

        script_result = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "scripts" / "deploy_specialists.py"),
                *common_arguments,
                "--output",
                str(script_output),
            ],
            cwd=self.tmp.name,
            capture_output=True,
            text=True,
            check=False,
        )
        module_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.deploy_specialists",
                *common_arguments,
                "--output",
                str(module_output),
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(script_result.returncode, 0, script_result.stderr)
        self.assertEqual(module_result.returncode, 0, module_result.stderr)
        self.assertEqual(json.loads(script_result.stdout), json.loads(module_result.stdout))
        self.assertEqual(
            json.loads(script_output.read_text(encoding="utf-8")),
            json.loads(module_output.read_text(encoding="utf-8")),
        )


if __name__ == "__main__":
    unittest.main()
