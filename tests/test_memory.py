import json
import tempfile
import unittest
from pathlib import Path

from runtime.dispatch import DispatchJob
from runtime.execution_package import ExecutionPackageBuilder
from runtime.memory import (
    FileMemoryStore,
    MemoryIntegrityError,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    SpecialistMemorySelector,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def record(
    memory_id,
    *,
    client_id="rave",
    run_id="run-1",
    kind=MemoryKind.CONTEXT,
    scope=MemoryScope.RUN,
    stage_ids=(),
):
    return MemoryRecord(
        memory_id=memory_id,
        client_id=client_id,
        run_id=run_id if scope == MemoryScope.RUN else None,
        kind=kind,
        scope=scope,
        content=f"content for {memory_id}",
        stage_ids=stage_ids,
        metadata={"fixture": True},
    )


class FileMemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = FileMemoryStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_supports_all_required_memory_kinds(self):
        self.assertEqual(
            {kind.value for kind in MemoryKind},
            {
                "decision",
                "assumption",
                "evidence",
                "revision",
                "approval",
                "context",
            },
        )

    def test_append_order_and_checksum_chain_survive_restart(self):
        first = self.store.append(
            record("client-context", scope=MemoryScope.CLIENT)
        )
        second = self.store.append(record("run-decision", kind=MemoryKind.DECISION))

        restarted = FileMemoryStore(self.root)
        loaded = restarted.read("rave", "run-1")

        self.assertEqual(
            [item.memory_id for item in loaded],
            ["client-context", "run-decision"],
        )
        self.assertEqual([item.sequence for item in loaded], [1, 2])
        self.assertEqual(second.previous_checksum, first.checksum)
        self.assertTrue(all(item.checksum for item in loaded))

    def test_duplicate_ids_are_rejected_and_metadata_is_immutable(self):
        new_record = record("immutable")
        with self.assertRaises(TypeError):
            new_record.metadata["changed"] = True
        self.store.append(new_record)
        with self.assertRaises(ValueError):
            self.store.append(record("immutable"))

    def test_checksum_chain_detects_tampering(self):
        self.store.append(record("audited"))
        path = self.root / "rave.jsonl"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["content"] = "silently changed"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        with self.assertRaises(MemoryIntegrityError):
            FileMemoryStore(self.root).read("rave", "run-1")

    def test_run_and_client_scopes_do_not_leak(self):
        self.store.append(record("rave-shared", scope=MemoryScope.CLIENT))
        self.store.append(record("rave-run-one"))
        self.store.append(record("rave-run-two", run_id="run-2"))
        self.store.append(
            record(
                "maeving-run-one",
                client_id="maeving",
            )
        )

        self.assertEqual(
            [item.memory_id for item in self.store.read("rave", "run-1")],
            ["rave-shared", "rave-run-one"],
        )
        self.assertEqual(
            [item.memory_id for item in self.store.read("rave", "run-2")],
            ["rave-shared", "rave-run-two"],
        )
        self.assertEqual(
            [item.memory_id for item in self.store.read("maeving", "run-1")],
            ["maeving-run-one"],
        )


class SpecialistMemorySelectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileMemoryStore(Path(self.tmp.name))
        self.selector = SpecialistMemorySelector(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_applies_specialist_kind_and_explicit_stage_rules(self):
        self.store.append(record("context", kind=MemoryKind.CONTEXT))
        self.store.append(record("evidence", kind=MemoryKind.EVIDENCE))
        self.store.append(record("approval", kind=MemoryKind.APPROVAL))
        self.store.append(
            record(
                "creative-revision",
                kind=MemoryKind.REVISION,
                stage_ids=("creative_director",),
            )
        )

        campaign = self.selector.select(
            client_id="rave",
            run_id="run-1",
            stage_id="campaign_world_generator",
        )
        creative = self.selector.select(
            client_id="rave",
            run_id="run-1",
            stage_id="creative_director",
        )
        quality = self.selector.select(
            client_id="rave",
            run_id="run-1",
            stage_id="quality_reviewer",
        )

        self.assertEqual(
            [item.memory_id for item in campaign],
            ["context", "approval"],
        )
        self.assertEqual(
            [item.memory_id for item in creative],
            ["context", "approval", "creative-revision"],
        )
        self.assertEqual(
            [item.memory_id for item in quality],
            ["context", "evidence", "approval"],
        )

    def test_retrieval_is_deterministic(self):
        for memory_id in ("first", "second", "third"):
            self.store.append(record(memory_id))
        first = self.selector.select(
            client_id="rave",
            run_id="run-1",
            stage_id="quality_reviewer",
        )
        second = SpecialistMemorySelector(
            FileMemoryStore(Path(self.tmp.name))
        ).select(
            client_id="rave",
            run_id="run-1",
            stage_id="quality_reviewer",
        )
        self.assertEqual(
            [item.memory_id for item in first],
            [item.memory_id for item in second],
        )


class ExecutionPackageMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FileMemoryStore(Path(self.tmp.name) / "memory")
        self.store.append(
            record("client-context", scope=MemoryScope.CLIENT)
        )
        self.store.append(
            record("run-evidence", kind=MemoryKind.EVIDENCE)
        )
        self.store.append(
            record("other-run", run_id="run-2", kind=MemoryKind.EVIDENCE)
        )
        self.builder = ExecutionPackageBuilder(
            REPOSITORY_ROOT,
            {"research_analyst": "completed_research_inputs"},
            memory_selector=SpecialistMemorySelector(self.store),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_injects_only_selected_client_and_run_memory(self):
        job = DispatchJob(
            job_id="run-1--research_analyst",
            run_id="run-1",
            stage_id="research_analyst",
            agent_ref="agents/research_analyst.md",
            payload={"client_id": "rave"},
        )
        package = self.builder.build(job)

        self.assertEqual(
            [item["memory_id"] for item in package.memory_records],
            ["client-context", "run-evidence"],
        )
        self.assertNotIn("other-run", package.to_json())

    def test_missing_client_identity_receives_no_memory(self):
        job = DispatchJob(
            job_id="run-1--research_analyst",
            run_id="run-1",
            stage_id="research_analyst",
            agent_ref="agents/research_analyst.md",
            payload={},
        )
        self.assertEqual(self.builder.build(job).memory_records, ())


if __name__ == "__main__":
    unittest.main()
