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
            ],
        )
        self.assertEqual(len(schema.acts), 6)
        self.assertEqual(len(schema.slides), 30)

    def test_rejects_manifest_checksum_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "knowledge" / "blueprint"
            root.mkdir(parents=True, exist_ok=True)
            for path in BLUEPRINT_ROOT.iterdir():
                destination = root / path.name
                if path.is_dir():
                    shutil.copytree(path, destination)
                else:
                    shutil.copy2(path, destination)

            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assets"][0]["checksum"] = "tampered"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                BlueprintKnowledgeRegistry(root)


if __name__ == "__main__":
    unittest.main()
