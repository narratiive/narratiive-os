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
        self.assertEqual({slide.layout_type for slide in schema.slides}, {"A", "B", "C", "D", "E", "F"})
        self.assertEqual(schema.slides[0].slide_no, 1)
        self.assertEqual(schema.slides[-1].slide_no, 30)
        population = registry.asset("blueprint_population_system").read_text()
        schema_text = registry.asset("blueprint_schema_v3").read_text()
        visual_framework = registry.asset("visual_framework_library_v1").read_text()
        visual_intelligence = registry.asset("visual_intelligence_system_v1").read_text()
        self.assertIn("# NARRATIIVE BLUEPRINT POPULATION SYSTEM", population)
        self.assertIn("The architecture never changes.", population)
        self.assertIn("## WHY IS GROWTH HARDER THAN IT APPEARS?", population)
        self.assertIn("## FINAL STRATEGIC PRINCIPLE", population)
        self.assertIn("The statement should be memorable enough to be repeated internally.", population)
        self.assertIn("V3.1 UPDATE (RAVE REVIEW LEARNINGS)", schema_text)
        self.assertIn("Source of truth: 02 Growth Blueprint System + Narratiive Growth Blueprint 30-slide structure + Blueprint Population System + Master Context + Founder Brief + Scoring System + Founder-Grade Upgrade Rules.", schema_text)
        self.assertIn("SLIDE 01 — COVER", schema_text)
        self.assertIn("\"slide_no\": 30,", schema_text)
        self.assertIn("\"layout_type\": \"F\"", schema_text)
        self.assertIn("The 30-slide version is the full paid master Blueprint. The 5-slide Executive Summary and 10-slide Diagnostic Teaser should be generated from this schema, not treated as separate products.", schema_text)
        self.assertIn("\"so_what_test\": \"Does the deck end with conviction and a natural next commercial step?\"", schema_text)
        self.assertIn("# NARRATIIVE VISUAL FRAMEWORK LIBRARY v1", visual_framework)
        self.assertIn("Ecosystem Map of Forces", visual_framework)
        self.assertIn("Campaign Factory", visual_framework)
        self.assertIn("Make it stick → Single Statement", visual_framework)
        self.assertIn("NARRATIIVE VISUAL INTELLIGENCE SYSTEM v1", visual_intelligence)
        self.assertIn("Every Blueprint should contain 3–5 Founder Insight Boxes.", visual_intelligence)
        self.assertIn("Data should never exist without interpretation.", visual_intelligence)
        self.assertIn("The objective of every Blueprint is not to impress.", visual_intelligence)

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

            manifest_path = root / "manifest.json"
            shutil.copy2(BLUEPRINT_ROOT / "manifest.json", manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assets"][0]["checksum"] = "tampered"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                BlueprintKnowledgeRegistry(root)


if __name__ == "__main__":
    unittest.main()
