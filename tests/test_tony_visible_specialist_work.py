from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TonyVisibleSpecialistWorkTests(unittest.TestCase):
    def test_named_material_specialist_work_is_persistent_and_native(self) -> None:
        prompt = (ROOT / "openclaw" / "workspace-templates" / "tony" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("spawn it with `visible: true`", prompt)
        self.assertIn('`category: "Narratiive specialists"`', prompt)
        self.assertIn("native persistent specialist-session mode", prompt)
        self.assertIn("default hidden sub-agent mode only for short internal work", prompt)
        self.assertIn("sessionUrl", prompt)
        self.assertIn("Do not create a second Narratiive-side specialist registry", prompt)
        self.assertIn("An accepted spawn proves delegation started, not that the specialist completed the work", prompt)


if __name__ == "__main__":
    unittest.main()
