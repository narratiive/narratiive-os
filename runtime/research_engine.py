#!/usr/bin/env python3
"""Evidence-grounded research engine for Narratiive OS.

This module defines the provider-neutral evidence contracts, approved adapters
for web retrieval and local document ingestion, and immutable workspace-scoped
evidence pack persistence.
"""

from __future__ import annotations

import hashlib
import json
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAX_BYTES = 250_000
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_ALLOWED_SCHEMES = ("https",)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return cleaned or "workspace"


def normalise_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def truncate_text(value: str, limit: int = 400) -> str:
    text = normalise_text(value)
    return text[:limit]


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceSourcePolicy:
    approved: bool = False
    allowed_domains: tuple[str, ...] = ()
    allowed_schemes: tuple[str, ...] = DEFAULT_ALLOWED_SCHEMES
    max_bytes: int = DEFAULT_MAX_BYTES
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    allow_local_files: bool = False


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    workspace_id: str
    source_type: str
    uri: str
    title: str = ""
    policy: EvidenceSourcePolicy = field(default_factory=EvidenceSourcePolicy)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MaterialClaim:
    claim_id: str
    statement: str
    evidence_ids: tuple[str, ...] = ()
    importance: str = "material"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceRecord:
    evidence_id: str
    workspace_id: str
    source_id: str
    source_type: str
    uri: str
    title: str
    content: str
    excerpt: str
    published_at: str | None
    retrieved_at: str
    content_hash: str
    provenance: list[dict[str, Any]] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceBatch:
    source_id: str
    adapter: str
    records: list[EvidenceRecord] = field(default_factory=list)
    blocker: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchJob:
    job_id: str
    workspace_id: str
    query: str
    sources: tuple[EvidenceSource, ...] = ()
    claims: tuple[MaterialClaim, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)
    lineage: tuple[str, ...] = ()


@dataclass
class EvidencePack:
    pack_id: str
    workspace_id: str
    job_id: str
    query: str
    created_at: str
    previous_pack_id: str | None
    lineage: list[str]
    sources: list[dict[str, Any]]
    records: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    unsupported_claims: list[dict[str, Any]]
    evidence_aliases: dict[str, str]
    missing_inputs: list[str]
    blockers: list[str]
    status: str
    source_policy: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchRun:
    job: ResearchJob
    evidence_pack: EvidencePack
    pack_path: str
    status: str
    blockers: list[str]
    warnings: list[str]
    deduplicated_record_count: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class EvidenceAdapter(Protocol):
    name: str

    def supports(self, source: EvidenceSource) -> bool:
        ...

    def collect(self, job: ResearchJob, source: EvidenceSource) -> EvidenceBatch:
        ...


class WebRetrievalAdapter:
    name = "web_retrieval"

    def __init__(self, fetcher: Any | None = None) -> None:
        self.fetcher = fetcher

    def supports(self, source: EvidenceSource) -> bool:
        if source.source_type not in {"web", "webpage", "url"}:
            return False
        parsed = urllib.parse.urlparse(source.uri)
        return parsed.scheme in {"http", "https"}

    def collect(self, job: ResearchJob, source: EvidenceSource) -> EvidenceBatch:
        policy = source.policy
        if not policy.approved:
            return EvidenceBatch(source_id=source.source_id, adapter=self.name, blocker="Web source is not approved.")
        if not source.uri:
            return EvidenceBatch(source_id=source.source_id, adapter=self.name, blocker="Web source URI is missing.")

        original_url = self._validate_web_url(source.uri, policy, context="source URL")
        parsed = urllib.parse.urlparse(source.uri)

        try:
            raw, final_url = self._fetch_bytes(source.uri, policy.timeout_seconds, policy.max_bytes)
            if final_url:
                self._validate_web_url(final_url, policy, context="redirect destination")
        except Exception as exc:  # noqa: BLE001
            return EvidenceBatch(source_id=source.source_id, adapter=self.name, blocker=str(exc))
        text = self._decode_web_bytes(raw)
        content_hash = sha256_hex(text)
        evidence_id = self._evidence_id(job.workspace_id, source.source_id, content_hash)
        provenance = [
            {
                "adapter": self.name,
                "source_id": source.source_id,
                "workspace_id": job.workspace_id,
                "uri": original_url,
                "retrieved_at": utc_now(),
                "content_hash": content_hash,
            }
        ]
        record = EvidenceRecord(
            evidence_id=evidence_id,
            workspace_id=source.workspace_id,
            source_id=source.source_id,
            source_type=source.source_type,
            uri=source.uri,
            title=source.title or source.metadata.get("title") or parsed.netloc,
            content=text,
            excerpt=truncate_text(text),
            published_at=source.metadata.get("published_at"),
            retrieved_at=utc_now(),
            content_hash=content_hash,
            provenance=provenance,
            source_ids=[source.source_id],
        )
        return EvidenceBatch(source_id=source.source_id, adapter=self.name, records=[record])

    def _fetch_bytes(self, uri: str, timeout_seconds: int, max_bytes: int) -> tuple[bytes, str | None]:
        if self.fetcher is not None:
            payload = self.fetcher(uri, timeout_seconds)
            final_url = None
            if isinstance(payload, dict) and "content" in payload:
                final_url = payload.get("final_url") or payload.get("url")
                payload = payload["content"]
            elif isinstance(payload, tuple):
                if len(payload) == 2:
                    payload, final_url = payload
                elif len(payload) > 2:
                    payload, final_url = payload[0], payload[1]
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            if not isinstance(payload, (bytes, bytearray)):
                raise RuntimeError("Web fetcher must return bytes or text.")
            data = bytes(payload)
            if len(data) > max_bytes:
                raise RuntimeError(f"Web source exceeded size limit of {max_bytes} bytes.")
            return data, (str(final_url) if final_url is not None else None)

        request = urllib.request.Request(uri, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(f"Web source exceeded size limit of {max_bytes} bytes.")
            final_url = getattr(response, "geturl", lambda: uri)()
        return b"".join(chunks), final_url

    def _decode_web_bytes(self, data: bytes) -> str:
        text = data.decode("utf-8", errors="replace")
        text = re.sub(r"<script.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return normalise_text(text)

    def _evidence_id(self, workspace_id: str, source_id: str, content_hash: str) -> str:
        return f"ev_{sha256_hex(f'{workspace_id}|{source_id}|{content_hash}')[:16]}"

    def _validate_web_url(self, url: str, policy: EvidenceSourcePolicy, *, context: str) -> str:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in policy.allowed_schemes:
            raise RuntimeError(f"Web {context} scheme '{parsed.scheme}' is not permitted.")
        if not parsed.hostname:
            raise RuntimeError(f"Web {context} is missing a hostname.")
        hostname = parsed.hostname
        if policy.allowed_domains and hostname not in set(policy.allowed_domains):
            raise RuntimeError(f"Web {context} domain '{hostname}' is not approved.")
        self._reject_unsafe_destination(hostname, context)
        return url

    def _reject_unsafe_destination(self, hostname: str, context: str) -> None:
        candidates: list[ipaddress._BaseAddress] = []
        try:
            candidates.append(ipaddress.ip_address(hostname))
        except ValueError:
            try:
                resolved = socket.getaddrinfo(hostname, None)
            except socket.gaierror as exc:
                raise RuntimeError(f"Web {context} could not be resolved: {hostname}") from exc
            for family, _, _, _, sockaddr in resolved:
                address = sockaddr[0]
                try:
                    candidates.append(ipaddress.ip_address(address))
                except ValueError:
                    continue

        if not candidates:
            raise RuntimeError(f"Web {context} could not be resolved: {hostname}")

        for candidate in candidates:
            if candidate.is_loopback or candidate.is_private or candidate.is_link_local or candidate.is_reserved or candidate.is_multicast or candidate.is_unspecified:
                raise RuntimeError(f"Web {context} resolves to an unsafe address: {hostname}")


class LocalDocumentIngestionAdapter:
    name = "local_document_ingestion"

    def __init__(self, root: Path = REPO_ROOT) -> None:
        self.root = root

    def supports(self, source: EvidenceSource) -> bool:
        return source.source_type in {"document", "local_document", "file", "markdown", "text"}

    def collect(self, job: ResearchJob, source: EvidenceSource) -> EvidenceBatch:
        policy = source.policy
        if not policy.approved:
            return EvidenceBatch(source_id=source.source_id, adapter=self.name, blocker="Document source is not approved.")
        if not policy.allow_local_files:
            return EvidenceBatch(source_id=source.source_id, adapter=self.name, blocker="Local file ingestion is not permitted.")
        if source.workspace_id.strip() != job.workspace_id.strip():
            return EvidenceBatch(
                source_id=source.source_id,
                adapter=self.name,
                blocker="Document source workspace does not match the research job workspace.",
            )

        workspace_root = (self.root / "research" / "workspaces" / slugify(job.workspace_id)).resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        path = self._resolve_path(workspace_root, source.uri)
        if path is None:
            return EvidenceBatch(source_id=source.source_id, adapter=self.name, blocker="Document path escapes the workspace scope.")
        if not path.exists():
            return EvidenceBatch(source_id=source.source_id, adapter=self.name, blocker=f"Document not found: {path}")
        if not path.is_file():
            return EvidenceBatch(source_id=source.source_id, adapter=self.name, blocker=f"Document is not a file: {path}")
        size = path.stat().st_size
        if size > policy.max_bytes:
            return EvidenceBatch(
                source_id=source.source_id,
                adapter=self.name,
                blocker=f"Document exceeded size limit of {policy.max_bytes} bytes.",
            )

        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")

        text = normalise_text(text)
        content_hash = sha256_hex(text)
        evidence_id = self._evidence_id(job.workspace_id, source.source_id, content_hash)
        provenance = [
            {
                "adapter": self.name,
                "source_id": source.source_id,
                "workspace_id": job.workspace_id,
                "uri": str(path.relative_to(workspace_root)),
                "retrieved_at": utc_now(),
                "content_hash": content_hash,
                "file_size": size,
            }
        ]
        record = EvidenceRecord(
            evidence_id=evidence_id,
            workspace_id=source.workspace_id,
            source_id=source.source_id,
            source_type=source.source_type,
            uri=str(path.relative_to(workspace_root)),
            title=source.title or source.metadata.get("title") or path.stem,
            content=text,
            excerpt=truncate_text(text),
            published_at=source.metadata.get("published_at") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            retrieved_at=utc_now(),
            content_hash=content_hash,
            provenance=provenance,
            source_ids=[source.source_id],
        )
        return EvidenceBatch(source_id=source.source_id, adapter=self.name, records=[record])

    def _resolve_path(self, workspace_root: Path, uri: str) -> Path | None:
        if not uri:
            return None
        parsed = urllib.parse.urlparse(uri)
        if parsed.scheme == "file":
            candidate = Path(parsed.path)
        else:
            candidate = Path(uri)
        if not candidate.is_absolute():
            candidate = workspace_root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(workspace_root)
        except ValueError:
            return None
        return resolved

    def _evidence_id(self, workspace_id: str, source_id: str, content_hash: str) -> str:
        return f"ev_{sha256_hex(f'{workspace_id}|{source_id}|{content_hash}')[:16]}"


class EvidencePackStore:
    def __init__(self, root: Path = REPO_ROOT) -> None:
        self.root = root

    def workspace_dir(self, workspace_id: str) -> Path:
        return self.root / "research" / "workspaces" / slugify(workspace_id) / "evidence_packs"

    def latest_pack(self, workspace_id: str) -> dict[str, Any] | None:
        workspace_dir = self.workspace_dir(workspace_id)
        if not workspace_dir.exists():
            return None
        packs = sorted(workspace_dir.glob("*.json"))
        if not packs:
            return None
        latest = packs[-1]
        return json.loads(latest.read_text(encoding="utf-8"))

    def save(self, pack: EvidencePack) -> Path:
        workspace_dir = self.workspace_dir(pack.workspace_id)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{pack.created_at.replace(':', '').replace('-', '')}_{pack.pack_id}.json"
        path = workspace_dir / filename
        if path.exists():
            raise RuntimeError(f"Evidence pack already exists: {path}")
        path.write_text(json.dumps(pack.as_dict(), indent=2, sort_keys=True, default=str), encoding="utf-8")
        return path


class ResearchEngine:
    def __init__(
        self,
        root: Path = REPO_ROOT,
        adapters: list[EvidenceAdapter] | None = None,
        store: EvidencePackStore | None = None,
    ) -> None:
        self.root = root
        self.adapters = adapters or [WebRetrievalAdapter(), LocalDocumentIngestionAdapter(root)]
        self.store = store or EvidencePackStore(root)

    def run(self, job: ResearchJob) -> ResearchRun:
        if not job.workspace_id.strip():
            raise ValueError("workspace_id is required.")
        if not job.query.strip():
            raise ValueError("query is required.")

        blockers: list[str] = []
        warnings: list[str] = []
        collected: list[EvidenceRecord] = []
        accepted_sources: list[EvidenceSource] = []

        if not job.sources:
            blockers.append("No evidence sources supplied.")

        for source in job.sources:
            if source.workspace_id.strip() != job.workspace_id.strip():
                blockers.append(
                    f"{source.source_id}: source workspace_id does not match research job workspace_id."
                )
                continue
            accepted_sources.append(source)
            adapter = self._select_adapter(source)
            if adapter is None:
                blockers.append(f"No adapter available for {source.source_id} ({source.source_type}).")
                continue
            try:
                batch = adapter.collect(job, source)
            except Exception as exc:  # noqa: BLE001
                blockers.append(f"{source.source_id}: {exc}")
                continue
            if batch.blocker:
                blockers.append(f"{source.source_id}: {batch.blocker}")
            warnings.extend(batch.warnings)
            collected.extend(batch.records)

        deduped_records, evidence_aliases = self._dedupe_records(collected)
        records_by_id = {record.evidence_id: record for record in deduped_records}
        claims, unsupported_claims, claim_missing_inputs = self._validate_claims(job.claims, records_by_id, evidence_aliases)
        missing_inputs = list(dict.fromkeys([*job.missing_inputs, *claim_missing_inputs]))

        latest_pack = self.store.latest_pack(job.workspace_id)
        previous_pack_id = None
        lineage = list(job.lineage)
        if latest_pack:
            previous_pack_id = str(latest_pack.get("pack_id") or "")
            if latest_pack.get("lineage"):
                lineage.extend(str(item) for item in latest_pack.get("lineage") or [])
            if previous_pack_id:
                lineage.append(previous_pack_id)

        pack_status = self._pack_status(blockers, missing_inputs, unsupported_claims, deduped_records)
        accepted_job = ResearchJob(
            job_id=job.job_id,
            workspace_id=job.workspace_id,
            query=job.query,
            sources=tuple(accepted_sources),
            claims=job.claims,
            missing_inputs=job.missing_inputs,
            created_at=job.created_at,
            lineage=job.lineage,
        )
        pack = EvidencePack(
            pack_id=self._pack_id(job, deduped_records),
            workspace_id=job.workspace_id,
            job_id=job.job_id,
            query=job.query,
            created_at=job.created_at,
            previous_pack_id=previous_pack_id,
            lineage=list(dict.fromkeys(lineage)),
            sources=[self._source_as_dict(source) for source in accepted_sources],
            records=[record.as_dict() for record in deduped_records],
            claims=claims,
            unsupported_claims=unsupported_claims,
            evidence_aliases=evidence_aliases,
            missing_inputs=missing_inputs,
            blockers=list(dict.fromkeys(blockers)),
            status=pack_status,
            source_policy=self._job_policy(accepted_job),
        )
        pack_path = self.store.save(pack)
        return ResearchRun(
            job=job,
            evidence_pack=pack,
            pack_path=str(pack_path),
            status=pack_status,
            blockers=list(dict.fromkeys(blockers)),
            warnings=list(dict.fromkeys(warnings)),
            deduplicated_record_count=len(deduped_records),
        )

    def _select_adapter(self, source: EvidenceSource) -> EvidenceAdapter | None:
        for adapter in self.adapters:
            if adapter.supports(source):
                return adapter
        return None

    def _dedupe_records(self, records: list[EvidenceRecord]) -> tuple[list[EvidenceRecord], dict[str, str]]:
        deduped: dict[str, EvidenceRecord] = {}
        aliases: dict[str, str] = {}
        for record in records:
            existing = deduped.get(record.content_hash)
            if existing is None:
                deduped[record.content_hash] = record
                continue
            existing.source_ids = self._unique(existing.source_ids + record.source_ids)
            existing.provenance = self._unique_dicts(existing.provenance + record.provenance)
            existing.aliases = self._unique(existing.aliases + [record.evidence_id] + record.aliases)
            aliases[record.evidence_id] = existing.evidence_id
            for alias in record.aliases:
                aliases[alias] = existing.evidence_id
        for record in deduped.values():
            aliases[record.evidence_id] = record.evidence_id
            for alias in record.aliases:
                aliases[alias] = record.evidence_id
        return list(deduped.values()), aliases

    def _validate_claims(
        self,
        claims: tuple[MaterialClaim, ...],
        records_by_id: dict[str, EvidenceRecord],
        evidence_aliases: dict[str, str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        supported: list[dict[str, Any]] = []
        unsupported: list[dict[str, Any]] = []
        missing_inputs: list[str] = []

        for claim in claims:
            evidence_ids = [evidence_id for evidence_id in claim.evidence_ids if evidence_id]
            resolved_evidence_ids = [evidence_aliases.get(evidence_id, evidence_id) for evidence_id in evidence_ids]
            missing_evidence_ids = [evidence_id for evidence_id, resolved in zip(evidence_ids, resolved_evidence_ids) if resolved not in records_by_id]
            if claim.importance == "material" and not evidence_ids:
                unsupported.append(
                    {
                        "claim_id": claim.claim_id,
                        "statement": claim.statement,
                        "reason": "Material claim does not reference any evidence IDs.",
                        "evidence_ids": [],
                        "missing_evidence_ids": [],
                    }
                )
                continue
            if missing_evidence_ids:
                unsupported.append(
                    {
                        "claim_id": claim.claim_id,
                        "statement": claim.statement,
                        "reason": "Referenced evidence IDs were not collected for this research job.",
                        "evidence_ids": evidence_ids,
                        "resolved_evidence_ids": resolved_evidence_ids,
                        "missing_evidence_ids": missing_evidence_ids,
                    }
                )
                continue
            supported.append(
                {
                    "claim_id": claim.claim_id,
                    "statement": claim.statement,
                    "evidence_ids": evidence_ids,
                    "resolved_evidence_ids": resolved_evidence_ids,
                    "importance": claim.importance,
                    "metadata": claim.metadata,
                }
            )

        if not claims:
            missing_inputs.append("No material claims were supplied.")
        return supported, unsupported, missing_inputs

    def _pack_status(
        self,
        blockers: list[str],
        missing_inputs: list[str],
        unsupported_claims: list[dict[str, Any]],
        records: list[EvidenceRecord],
    ) -> str:
        if blockers and not records:
            return "blocked"
        if missing_inputs or unsupported_claims or blockers:
            return "partial" if records else "blocked"
        return "complete"

    def _pack_id(self, job: ResearchJob, records: list[EvidenceRecord]) -> str:
        fingerprint = "|".join(
            [
                job.workspace_id,
                job.job_id,
                job.query,
                ",".join(record.evidence_id for record in records),
            ]
        )
        return f"pack_{sha256_hex(fingerprint)[:16]}"

    def _job_policy(self, job: ResearchJob) -> dict[str, Any]:
        policies = [self._source_policy_as_dict(source.policy) for source in job.sources]
        return {
            "sources": policies,
            "workspace_scoped": True,
        }

    def _source_policy_as_dict(self, policy: EvidenceSourcePolicy) -> dict[str, Any]:
        return asdict(policy)

    def _source_as_dict(self, source: EvidenceSource) -> dict[str, Any]:
        data = asdict(source)
        data["policy"] = self._source_policy_as_dict(source.policy)
        return data

    def _unique(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    def _unique_dicts(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in values:
            marker = json.dumps(value, sort_keys=True, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            unique.append(value)
        return unique
