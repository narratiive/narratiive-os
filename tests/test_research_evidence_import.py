from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.research_engine import (
    EvidenceSource,
    EvidenceSourcePolicy,
    ResearchEngine,
    ResearchJob,
)
from runtime.research_evidence_import import (
    OpenClawResearchEvidenceImporter,
    ResearchEvidenceImportError,
)


class OpenClawResearchEvidenceImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.openclaw = self.root / "openclaw"
        self.sessions = self.openclaw / "agents" / "research" / "sessions"
        self.sessions.mkdir(parents=True)
        self.runtime_root = self.root / "runtime"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _session(self, path: Path | None = None) -> Path:
        target = path or self.sessions / "safe-session.jsonl"
        words = " ".join(f"evidence-{index}" for index in range(120))
        records = [
            {
                "type": "message",
                "id": "draft",
                "message": {
                    "role": "assistant",
                    "stopReason": "toolUse",
                    "content": [{"type": "text", "text": "draft"}],
                },
            },
            {
                "type": "message",
                "id": "final-message",
                "timestamp": "2026-09-16T00:00:00Z",
                "message": {
                    "role": "assistant",
                    "stopReason": "stop",
                    "content": [{"type": "text", "text": words}],
                },
            },
        ]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
        return target

    def test_completed_result_is_promoted_immutably_and_ingested(self) -> None:
        importer = OpenClawResearchEvidenceImporter(self.runtime_root, self.openclaw)
        arguments = {
            "workspace_id": "agency",
            "client_id": "safe-client",
            "source_id": "safe-specialist-report",
            "title": "SAFE specialist research report",
            "approved_by": "engineering-acceptance",
            "approval_rationale": "SAFE synthetic acceptance evidence",
        }

        first = importer.import_session(self._session(), **arguments)
        replay = importer.import_session(self.sessions / "safe-session.jsonl", **arguments)

        self.assertFalse(first.replay)
        self.assertTrue(replay.replay)
        self.assertEqual(first.import_id, replay.import_id)
        self.assertEqual(first.source["metadata"]["evidence_tier"], "specialist_synthesis")
        self.assertTrue(first.source["policy"]["approved"])

        scoped_root = Path(first.document_path).parents[4]
        engine = ResearchEngine(scoped_root)
        source = EvidenceSource(
            source_id=first.source["source_id"],
            workspace_id="agency",
            source_type=first.source["source_type"],
            uri=first.source["uri"],
            title=first.source["title"],
            policy=EvidenceSourcePolicy(approved=True, allow_local_files=True),
            metadata=first.source["metadata"],
        )
        run = engine.run(ResearchJob(job_id="safe-import", workspace_id="agency", query="SAFE", sources=(source,)))
        self.assertEqual(run.status, "partial")
        self.assertEqual(run.blockers, [])
        self.assertEqual(run.evidence_pack.records[0]["source_id"], "safe-specialist-report")

    def test_interrupted_pair_is_recovered_without_rewriting_existing_evidence(self) -> None:
        importer = OpenClawResearchEvidenceImporter(self.runtime_root, self.openclaw)
        arguments = {
            "workspace_id": "agency",
            "client_id": "safe-client",
            "source_id": "safe-recovery-report",
            "title": "SAFE recovery report",
            "approved_by": "engineering-acceptance",
            "approval_rationale": "SAFE recovery test",
        }
        first = importer.import_session(self._session(), **arguments)
        Path(first.manifest_path).unlink()

        recovered = importer.import_session(self.sessions / "safe-session.jsonl", **arguments)

        self.assertTrue(recovered.replay)
        self.assertTrue(Path(recovered.document_path).is_file())
        self.assertTrue(Path(recovered.manifest_path).is_file())

    def test_session_outside_research_store_is_rejected(self) -> None:
        outside = self._session(self.root / "outside.jsonl")
        with self.assertRaisesRegex(ResearchEvidenceImportError, "inside the OpenClaw research session store"):
            OpenClawResearchEvidenceImporter(self.runtime_root, self.openclaw).import_session(
                outside,
                workspace_id="agency",
                client_id="safe-client",
                source_id="unsafe",
                title="Unsafe",
                approved_by="test",
                approval_rationale="test",
            )

    def test_unfinished_session_is_rejected(self) -> None:
        session = self.sessions / "unfinished.jsonl"
        session.write_text(
            json.dumps(
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "stopReason": "toolUse",
                        "content": [],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ResearchEvidenceImportError, "no completed final work product"):
            OpenClawResearchEvidenceImporter(self.runtime_root, self.openclaw).import_session(
                session,
                workspace_id="agency",
                client_id="safe-client",
                source_id="unfinished",
                title="Unfinished",
                approved_by="test",
                approval_rationale="test",
            )


if __name__ == "__main__":
    unittest.main()
