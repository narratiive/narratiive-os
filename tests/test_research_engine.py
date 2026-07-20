from __future__ import annotations

import hashlib
import io
import shutil
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "research"
from runtime.research_engine import (  # noqa: E402
    EvidenceSource,
    EvidenceSourcePolicy,
    MaterialClaim,
    LocalDocumentIngestionAdapter,
    ResearchEngine,
    ResearchJob,
    WebRetrievalAdapter,
    sha256_hex,
    normalise_text,
)


class ResearchEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "research").mkdir(parents=True, exist_ok=True)
        (self.root / "research" / "workspaces" / "rave").mkdir(parents=True, exist_ok=True)
        self.sample_doc = self.root / "research" / "workspaces" / "rave" / "sample_local_source.md"
        shutil.copy2(FIXTURE_ROOT / "sample_local_source.md", self.sample_doc)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_run_deduplicates_repeated_evidence_and_persists_lineage(self) -> None:
        workspace_id = "Rave"
        text = normalise_text((FIXTURE_ROOT / "sample_local_source.md").read_text(encoding="utf-8"))
        web_source = EvidenceSource(
            source_id="web-source-1",
            workspace_id=workspace_id,
            source_type="web",
            uri="https://example.com/rave",
            title="Rave web source",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("example.com",),
                max_bytes=10_000,
                timeout_seconds=2,
            ),
            metadata={"published_at": "2026-07-01T00:00:00+00:00"},
        )
        local_source = EvidenceSource(
            source_id="doc-source-1",
            workspace_id=workspace_id,
            source_type="document",
            uri="sample_local_source.md",
            title="Rave local source",
            policy=EvidenceSourcePolicy(
                approved=True,
                allow_local_files=True,
                max_bytes=10_000,
                timeout_seconds=2,
            ),
            metadata={"published_at": "2026-07-02T00:00:00+00:00"},
        )
        expected_evidence_id = f"ev_{sha256_hex(f'{workspace_id}|{web_source.source_id}|{sha256_hex(text)}')[:16]}"
        claim = MaterialClaim(
            claim_id="claim-1",
            statement="Rave Coffee is positioned around premium ritual and design.",
            evidence_ids=(expected_evidence_id,),
        )

        engine = ResearchEngine(
            root=self.root,
            adapters=[
                WebRetrievalAdapter(fetcher=lambda uri, timeout: text.encode("utf-8")),
                LocalDocumentIngestionAdapter(self.root),
            ],
        )
        job_one = ResearchJob(
            job_id="job-001",
            workspace_id=workspace_id,
            query="Rave research",
            sources=(web_source, local_source),
            claims=(claim,),
        )
        first = engine.run(job_one)

        self.assertEqual(first.status, "complete")
        self.assertEqual(first.deduplicated_record_count, 1)
        self.assertTrue(Path(first.pack_path).exists())
        self.assertEqual(len(first.evidence_pack.records), 1)
        record = first.evidence_pack.records[0]
        self.assertEqual(record["evidence_id"], expected_evidence_id)
        self.assertEqual(set(record["source_ids"]), {"web-source-1", "doc-source-1"})
        self.assertEqual(len(record["provenance"]), 2)
        self.assertIsNone(first.evidence_pack.previous_pack_id)

        job_two = ResearchJob(
            job_id="job-002",
            workspace_id=workspace_id,
            query="Rave research follow-up",
            sources=(web_source,),
            claims=(claim,),
        )
        second = engine.run(job_two)

        self.assertEqual(second.status, "complete")
        self.assertTrue(second.evidence_pack.previous_pack_id)
        self.assertIn(first.evidence_pack.pack_id, second.evidence_pack.lineage)

    def test_run_records_unsupported_claims_and_missing_inputs(self) -> None:
        workspace_id = "Rave"
        source = EvidenceSource(
            source_id="web-source-2",
            workspace_id=workspace_id,
            source_type="web",
            uri="https://example.com/other",
            title="Other source",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("example.com",),
                max_bytes=10_000,
                timeout_seconds=2,
            ),
        )
        engine = ResearchEngine(
            root=self.root,
            adapters=[WebRetrievalAdapter(fetcher=lambda uri, timeout: b"Claim-backed evidence from example.com.")],
        )
        job = ResearchJob(
            job_id="job-003",
            workspace_id=workspace_id,
            query="Rave research with gaps",
            sources=(source,),
            claims=(
                MaterialClaim(
                    claim_id="claim-unsupported",
                    statement="This material claim has no evidence ids.",
                    evidence_ids=(),
                ),
                MaterialClaim(
                    claim_id="claim-missing",
                    statement="This claim references missing evidence ids.",
                    evidence_ids=("ev_missing",),
                ),
            ),
            missing_inputs=("Customer interview notes",),
        )

        run = engine.run(job)

        self.assertEqual(run.status, "partial")
        self.assertIn("Customer interview notes", run.evidence_pack.missing_inputs)
        self.assertEqual(len(run.evidence_pack.unsupported_claims), 2)
        self.assertTrue(any("does not reference any evidence IDs" in item["reason"] for item in run.evidence_pack.unsupported_claims))
        self.assertTrue(any(item["missing_evidence_ids"] for item in run.evidence_pack.unsupported_claims))

    def test_run_rejects_cross_workspace_sources_without_persisting_foreign_state(self) -> None:
        engine = ResearchEngine(
            root=self.root,
            adapters=[WebRetrievalAdapter(fetcher=lambda uri, timeout: b"cross-workspace evidence")],
        )
        source = EvidenceSource(
            source_id="foreign-web",
            workspace_id="OtherWorkspace",
            source_type="web",
            uri="https://example.com/foreign",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("example.com",),
                max_bytes=10_000,
                timeout_seconds=2,
            ),
        )

        run = engine.run(
            ResearchJob(
                job_id="job-foreign",
                workspace_id="Rave",
                query="cross workspace",
                sources=(source,),
            )
        )

        self.assertEqual(run.status, "blocked")
        self.assertTrue(any("workspace_id does not match" in blocker for blocker in run.blockers))
        self.assertEqual(run.deduplicated_record_count, 0)
        self.assertEqual(run.evidence_pack.sources, [])
        self.assertFalse((self.root / "research" / "workspaces" / "otherworkspace").exists())

    def test_run_references_aliases_for_duplicate_evidence_ids(self) -> None:
        workspace_id = "Rave"
        text = "Duplicate content that should collapse into a canonical record."
        source_one = EvidenceSource(
            source_id="web-source-1",
            workspace_id=workspace_id,
            source_type="web",
            uri="https://example.com/one",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("example.com",),
                max_bytes=10_000,
                timeout_seconds=2,
            ),
        )
        source_two = EvidenceSource(
            source_id="web-source-2",
            workspace_id=workspace_id,
            source_type="web",
            uri="https://example.com/two",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("example.com",),
                max_bytes=10_000,
                timeout_seconds=2,
            ),
        )
        second_evidence_id = f"ev_{sha256_hex(f'{workspace_id}|{source_two.source_id}|{sha256_hex(text)}')[:16]}"
        claim = MaterialClaim(
            claim_id="claim-alias",
            statement="The duplicate claim should still resolve via the second evidence ID.",
            evidence_ids=(second_evidence_id,),
        )
        engine = ResearchEngine(
            root=self.root,
            adapters=[WebRetrievalAdapter(fetcher=lambda uri, timeout: text.encode("utf-8"))],
        )

        run = engine.run(
            ResearchJob(
                job_id="job-alias",
                workspace_id=workspace_id,
                query="duplicate evidence",
                sources=(source_one, source_two),
                claims=(claim,),
            )
        )

        self.assertEqual(run.status, "complete")
        self.assertEqual(run.deduplicated_record_count, 1)
        self.assertEqual(len(run.evidence_pack.records), 1)
        self.assertEqual(run.evidence_pack.evidence_aliases.get(second_evidence_id), run.evidence_pack.records[0]["evidence_id"])
        self.assertEqual(run.evidence_pack.claims[0]["resolved_evidence_ids"], [run.evidence_pack.records[0]["evidence_id"]])

    def test_web_and_local_adapters_enforce_safety_rules(self) -> None:
        web_source = EvidenceSource(
            source_id="web-source-3",
            workspace_id="Rave",
            source_type="web",
            uri="https://blocked.example.com/path",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("example.com",),
                max_bytes=10_000,
                timeout_seconds=1,
            ),
        )
        local_source = EvidenceSource(
            source_id="doc-source-3",
            workspace_id="Rave",
            source_type="document",
            uri="../outside.md",
            policy=EvidenceSourcePolicy(
                approved=True,
                allow_local_files=True,
                max_bytes=10_000,
                timeout_seconds=1,
            ),
        )

        web_batch = WebRetrievalAdapter(fetcher=lambda uri, timeout: b"ignored").collect(
            ResearchJob(job_id="job-004", workspace_id="Rave", query="test", sources=(web_source,)),
            web_source,
        )
        local_batch = LocalDocumentIngestionAdapter(self.root).collect(
            ResearchJob(job_id="job-005", workspace_id="Rave", query="test", sources=(local_source,)),
            local_source,
        )

        self.assertIsNotNone(web_batch.blocker)
        self.assertIn("not approved", web_batch.blocker or "")
        self.assertIsNotNone(local_batch.blocker)
        self.assertIn("escapes the workspace scope", local_batch.blocker or "")

    def test_web_adapter_rejects_private_address_destinations(self) -> None:
        source = EvidenceSource(
            source_id="web-source-private",
            workspace_id="Rave",
            source_type="web",
            uri="https://127.0.0.1/private",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("127.0.0.1",),
                max_bytes=5_000,
                timeout_seconds=1,
            ),
        )
        batch = WebRetrievalAdapter(fetcher=lambda uri, timeout: b"ignored").collect(
            ResearchJob(job_id="job-private", workspace_id="Rave", query="test", sources=(source,)),
            source,
        )
        self.assertIsNotNone(batch.blocker)
        self.assertIn("unsafe address", batch.blocker or "")

    def test_web_adapter_rejects_private_redirect_targets_before_following_them(self) -> None:
        source = EvidenceSource(
            source_id="web-source-private-redirect",
            workspace_id="Rave",
            source_type="web",
            uri="https://example.com/start",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("example.com", "internal.example.com"),
                max_bytes=5_000,
                timeout_seconds=1,
            ),
        )

        calls: list[str] = []

        class RedirectingOpener:
            def open(self, request, timeout=None):  # noqa: ANN001
                calls.append(request.full_url)
                headers = Message()
                headers["Location"] = "https://internal.example.com/private"
                raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, io.BytesIO(b""))

        batch = WebRetrievalAdapter(
            resolver=lambda host: ["93.184.216.34"] if host == "example.com" else ["127.0.0.1"],
            opener_factory=lambda: RedirectingOpener(),
        ).collect(
            ResearchJob(job_id="job-private-redirect", workspace_id="Rave", query="test", sources=(source,)),
            source,
        )
        self.assertIsNotNone(batch.blocker)
        self.assertIn("unsafe address", batch.blocker or "")
        self.assertEqual(calls, ["https://example.com/start"])

    def test_web_adapter_rejects_redirects_outside_allowlist_without_following_them(self) -> None:
        source = EvidenceSource(
            source_id="web-source-redirect",
            workspace_id="Rave",
            source_type="web",
            uri="https://example.com/start",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("example.com",),
                max_bytes=5_000,
                timeout_seconds=1,
            ),
        )

        calls: list[str] = []

        class RedirectingOpener:
            def open(self, request, timeout=None):  # noqa: ANN001
                calls.append(request.full_url)
                headers = Message()
                headers["Location"] = "https://malicious.example.net/landing"
                raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, io.BytesIO(b""))

        batch = WebRetrievalAdapter(
            resolver=lambda host: ["93.184.216.34"],
            opener_factory=lambda: RedirectingOpener(),
        ).collect(
            ResearchJob(job_id="job-redirect", workspace_id="Rave", query="test", sources=(source,)),
            source,
        )
        self.assertIsNotNone(batch.blocker)
        self.assertIn("not approved", batch.blocker or "")
        self.assertEqual(calls, ["https://example.com/start"])

    def test_web_adapter_enforces_size_limit(self) -> None:
        source = EvidenceSource(
            source_id="web-source-4",
            workspace_id="Rave",
            source_type="web",
            uri="https://example.com/large",
            policy=EvidenceSourcePolicy(
                approved=True,
                allowed_domains=("example.com",),
                max_bytes=5,
                timeout_seconds=1,
            ),
        )
        batch = WebRetrievalAdapter(fetcher=lambda uri, timeout: b"this payload is too large").collect(
            ResearchJob(job_id="job-006", workspace_id="Rave", query="test", sources=(source,)),
            source,
        )
        self.assertIsNotNone(batch.blocker)
        self.assertIn("size limit", batch.blocker or "")


if __name__ == "__main__":
    unittest.main()
