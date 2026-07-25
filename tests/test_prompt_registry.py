import json
import tempfile
import unittest
from pathlib import Path

from runtime.prompt_registry import FilePromptRegistry, PromptTerminologyError
from runtime.terminology_policy import TerminologyPolicy


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

    def test_publish_records_governing_terminology_version(self) -> None:
        prompt = self.registry.publish(
            "research-analyst",
            "Use the Growth Blueprint as the strategic output.",
            {"owner": "strategy"},
        )
        self.assertEqual(
            prompt.metadata["terminology_policy_version"],
            self.registry.terminology_policy.version,
        )
        self.assertEqual(prompt.metadata["owner"], "strategy")

    def test_publish_rejects_retired_terminology_without_writing_version(self) -> None:
        with self.assertRaises(PromptTerminologyError) as raised:
            self.registry.publish("research-analyst", "Create an Opportunity Card.")
        self.assertEqual(raised.exception.terms, ("Opportunity Card",))
        self.assertEqual(self.registry.history("research-analyst"), [])

    def test_publish_reports_all_distinct_retired_terms(self) -> None:
        with self.assertRaises(PromptTerminologyError) as raised:
            self.registry.publish(
                "research-analyst",
                "Turn the Opportunity Card into a Growth Sprint and another Opportunity Card.",
            )
        self.assertEqual(raised.exception.terms, ("Growth Sprint", "Opportunity Card"))

    def test_activate_selects_explicit_version(self) -> None:
        self.registry.publish("strategy-director", "Version one")
        second = self.registry.publish("strategy-director", "Version two")
        active = self.registry.activate("strategy-director", second.version)
        self.assertEqual(active.version, 2)
        self.assertEqual(self.registry.active("strategy-director").content, "Version two")

    def test_activation_revalidates_historical_prompt_against_current_policy(self) -> None:
        permissive_policy = TerminologyPolicy(
            {
                "status": "active",
                "version": "1.0.0",
                "approved_terms": [],
                "unsettled_terms": [],
                "retired_terms": [
                    {"term": "Old Phrase", "replacement": None, "rationale": "retired"}
                ],
            }
        )
        governed_root = Path(self.tmp.name) / "governed"
        registry = FilePromptRegistry(governed_root, terminology_policy=permissive_policy)
        prompt = registry.publish("strategy-director", "Use the future phrase")

        version_path = governed_root / "versions" / "strategy-director--v1.json"
        payload = json.loads(version_path.read_text(encoding="utf-8"))
        payload["content"] = "Use the future phrase"
        version_path.write_text(json.dumps(payload), encoding="utf-8")

        stricter_policy = TerminologyPolicy(
            {
                "status": "active",
                "version": "2.0.0",
                "approved_terms": [],
                "unsettled_terms": [],
                "retired_terms": [
                    {"term": "future phrase", "replacement": None, "rationale": "now retired"}
                ],
            }
        )
        stricter_registry = FilePromptRegistry(governed_root, terminology_policy=stricter_policy)
        with self.assertRaises(PromptTerminologyError):
            stricter_registry.activate(prompt.prompt_id, prompt.version)

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
