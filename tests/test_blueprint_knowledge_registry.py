from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from runtime.blueprint_knowledge_registry import BlueprintKnowledgeRegistry


REPO_ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_ROOT = REPO_ROOT / "knowledge" / "blueprint"


class BlueprintKnowledgeRegistryTests(unittest.TestCase):
    def test_loads_the_canonical_blueprint_bundle_and_schema(self) -> None:
        registry = BlueprintKnowledgeRegistry.from_default()

        bundle = registry.active_bundle()
        schema = registry.schema()

        self.assertEqual(bundle.bundle_id, "blueprint-canon-v1")
        self.assertEqual(bundle.prompt_asset_id, "blueprint_population_system")
        self.assertEqual(
            [component.asset_id for component in bundle.components],
            [
                "blueprint_population_system",
                "blueprint_schema_v3",
                "visual_framework_library_v1",
                "visual_intelligence_system_v1",
            ],
        )
        self.assertEqual(
            registry.prompt_asset(bundle).repository_path,
            "knowledge/blueprint/population-system.md",
        )
        self.assertEqual(
            [asset.repository_path for asset in registry.supporting_assets(bundle)],
            [
                "knowledge/blueprint/blueprint-schema-v3.md",
                "knowledge/blueprint/visual-framework-library-v1.md",
                "knowledge/blueprint/visual-intelligence-system-v1.md",
            ],
        )
        self.assertEqual(len(schema.acts), 6)
        self.assertEqual(len(schema.slides), 30)
        population = registry.asset("blueprint_population_system").read_text()
        schema_text = registry.asset("blueprint_schema_v3").read_text()
        visual_framework = registry.asset("visual_framework_library_v1").read_text()
        visual_intelligence = registry.asset("visual_intelligence_system_v1").read_text()
        self.assertIn("The architecture never changes.", population)
        self.assertIn("The client-specific thinking fills the architecture.", population)
        self.assertIn("V3.1 UPDATE (RAVE REVIEW LEARNINGS)", schema_text)
        self.assertIn("Target quality threshold for future Blueprint generations: 9.5/10 founder-grade output.", schema_text)
        self.assertIn("SELECTION LOGIC (which framework when)", visual_framework)
        self.assertIn("Visual communication is always preferred to written explanation.", visual_intelligence)
        self.assertIn("Founder Insight Boxes", visual_intelligence)
        self.assertIn("SO WHAT?", visual_intelligence)

    def test_rejects_manifest_checksum_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(parents=True, exist_ok=True)
            blueprint_root = root / "knowledge" / "blueprint"
            blueprint_root.mkdir(parents=True, exist_ok=True)
            for path in BLUEPRINT_ROOT.iterdir():
                destination = blueprint_root / path.name
                if path.is_dir():
                    shutil.copytree(path, destination)
                else:
                    shutil.copy2(path, destination)

            manifest_path = blueprint_root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assets"][0]["checksum"] = "tampered"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                BlueprintKnowledgeRegistry(root)


if __name__ == "__main__":
    unittest.main()
