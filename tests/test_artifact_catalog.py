import tempfile
import unittest
from pathlib import Path

from runtime.artifact_catalog import FileArtifactCatalog


class ArtifactCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.catalog = FileArtifactCatalog(Path(self.tmp.name) / "artifacts")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_registers_immutable_content_and_version(self) -> None:
        first = self.catalog.register(
            run_id="run-1",
            stage_id="research",
            artifact_type="research_output",
            content="first version",
            producer="research-agent@1",
        )
        second = self.catalog.register(
            run_id="run-1",
            stage_id="research",
            artifact_type="research_output",
            content="second version",
            producer="research-agent@2",
        )
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertNotEqual(first.artifact.artifact_id, second.artifact.artifact_id)
        self.assertTrue(Path(first.artifact.location).exists())

    def test_same_content_is_deduplicated_but_versions_remain_distinct(self) -> None:
        first = self.catalog.register(
            run_id="run-1",
            stage_id="research",
            artifact_type="research_output",
            content="same",
        )
        second = self.catalog.register(
            run_id="run-1",
            stage_id="research",
            artifact_type="research_output",
            content="same",
        )
        self.assertEqual(first.artifact.artifact_id, second.artifact.artifact_id)
        self.assertEqual(second.version, 2)
        self.assertEqual(first.artifact.location, second.artifact.location)

    def test_tracks_parent_child_lineage(self) -> None:
        research = self.catalog.register(
            run_id="run-1",
            stage_id="research",
            artifact_type="research_output",
            content="research",
        )
        strategy = self.catalog.register(
            run_id="run-1",
            stage_id="strategy",
            artifact_type="strategy_output",
            content="strategy",
            parent_artifact_ids=[research.artifact.artifact_id],
        )
        ancestors = self.catalog.ancestors(strategy.artifact.artifact_id)
        self.assertEqual([item.artifact.artifact_id for item in ancestors], [research.artifact.artifact_id])

    def test_history_is_scoped_and_ordered(self) -> None:
        self.catalog.register(run_id="run-1", stage_id="research", artifact_type="output", content="one")
        self.catalog.register(run_id="run-1", stage_id="research", artifact_type="output", content="two")
        self.catalog.register(run_id="run-1", stage_id="strategy", artifact_type="output", content="other")
        history = self.catalog.history("run-1", "research", "output")
        self.assertEqual([item.version for item in history], [1, 2])

    def test_rejects_unsafe_identifiers(self) -> None:
        with self.assertRaises(ValueError):
            self.catalog.register(
                run_id="../run",
                stage_id="research",
                artifact_type="output",
                content="bad",
            )


if __name__ == "__main__":
    unittest.main()
