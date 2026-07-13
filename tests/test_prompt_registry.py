import tempfile
import unittest
from pathlib import Path

from runtime.prompt_registry import FilePromptRegistry


class PromptRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = FilePromptRegistry(Path(self.tmp.name) / "prompts")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_publish_creates_incrementing_versions(self) -> None:
        first = self.registry.publish("research-analyst", "Prompt one")
        second = self.registry.publish("research-analyst", "Prompt two")
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertNotEqual(first.checksum, second.checksum)

    def test_activate_selects_explicit_version(self) -> None:
        self.registry.publish("strategy-director", "Version one")
        second = self.registry.publish("strategy-director", "Version two")
        active = self.registry.activate("strategy-director", second.version)
        self.assertEqual(active.version, 2)
        self.assertEqual(self.registry.active("strategy-director").content, "Version two")

    def test_rollback_moves_to_previous_version(self) -> None:
        self.registry.publish("creative-director", "One")
        self.registry.publish("creative-director", "Two")
        self.registry.activate("creative-director", 2)
        rolled_back = self.registry.rollback("creative-director")
        self.assertEqual(rolled_back.version, 1)
        self.assertEqual(self.registry.active("creative-director").content, "One")

    def test_rollback_from_first_version_fails(self) -> None:
        self.registry.publish("quality-reviewer", "One")
        self.registry.activate("quality-reviewer", 1)
        with self.assertRaises(ValueError):
            self.registry.rollback("quality-reviewer")

    def test_missing_active_prompt_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.registry.active("missing")

    def test_rejects_unsafe_prompt_id(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.publish("../prompt", "bad")


if __name__ == "__main__":
    unittest.main()
