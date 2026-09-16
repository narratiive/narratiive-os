from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from runtime.research_engine import slugify


class ResearchEvidenceImportError(ValueError):
    """Raised when specialist research cannot be promoted safely."""


@dataclass(frozen=True, slots=True)
class ImportedResearchEvidence:
    import_id: str
    document_path: str
    manifest_path: str
    source: dict[str, Any]
    replay: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class OpenClawResearchEvidenceImporter:
    """Promote one completed OpenClaw research result into scoped evidence.

    OpenClaw session history is conversational execution evidence, not a
    canonical Narratiive research source. This importer selects only the final
    completed assistant work product, records its origin and checksums, and
    writes an immutable document inside the target Research Engine workspace.
    """

    def __init__(self, runtime_root: str | Path, openclaw_root: str | Path) -> None:
        self.runtime_root = Path(runtime_root).resolve()
        self.sessions_root = (
            Path(openclaw_root).resolve() / "agents" / "research" / "sessions"
        ).resolve()

    def import_session(
        self,
        session_path: str | Path,
        *,
        workspace_id: str,
        client_id: str,
        source_id: str,
        title: str,
        approved_by: str,
        approval_rationale: str,
    ) -> ImportedResearchEvidence:
        values = {
            "workspace_id": workspace_id,
            "client_id": client_id,
            "source_id": source_id,
            "title": title,
            "approved_by": approved_by,
            "approval_rationale": approval_rationale,
        }
        for label, value in values.items():
            if not str(value).strip():
                raise ResearchEvidenceImportError(f"{label} is required")

        session = Path(session_path).resolve()
        try:
            relative_session = session.relative_to(self.sessions_root)
        except ValueError as exc:
            raise ResearchEvidenceImportError(
                "research session must be inside the OpenClaw research session store"
            ) from exc
        if session.suffix != ".jsonl" or session.name.endswith(".trajectory.jsonl"):
            raise ResearchEvidenceImportError("research session must be a canonical JSONL session")
        try:
            raw = session.read_bytes()
        except OSError as exc:
            raise ResearchEvidenceImportError("research session is unreadable") from exc
        if not raw or len(raw) > 25_000_000:
            raise ResearchEvidenceImportError("research session is empty or exceeds the import limit")

        work_product, message_id, completed_at = self._final_work_product(raw)
        session_hash = hashlib.sha256(raw).hexdigest()
        content_hash = hashlib.sha256(work_product.encode("utf-8")).hexdigest()
        identity = hashlib.sha256(
            "\0".join(
                (
                    workspace_id.strip(),
                    client_id.strip(),
                    str(relative_session),
                    message_id,
                    content_hash,
                )
            ).encode("utf-8")
        ).hexdigest()
        import_id = f"openclaw-research-{identity[:20]}"
        scope = hashlib.sha256(
            f"{workspace_id.strip()}:{client_id.strip()}".encode("utf-8")
        ).hexdigest()[:24]
        workspace_root = (
            self.runtime_root
            / scope
            / "research"
            / "workspaces"
            / slugify(workspace_id)
        )
        imports_root = workspace_root / "imports"
        document = imports_root / f"{import_id}.md"
        manifest = imports_root / f"{import_id}.manifest.json"
        relative_document = str(document.relative_to(workspace_root))
        source = {
            "source_id": source_id.strip(),
            "source_type": "document",
            "uri": relative_document,
            "title": title.strip(),
            "policy": {
                "approved": True,
                "allow_local_files": True,
                "max_bytes": max(250_000, len(work_product.encode("utf-8")) + 1),
            },
            "metadata": {
                "evidence_tier": "specialist_synthesis",
                "claim_treatment": "verify_material_claims_against_cited_primary_sources",
                "origin": "openclaw_research_session",
                "origin_session": str(relative_session),
                "origin_message_id": message_id,
                "origin_completed_at": completed_at,
                "origin_session_sha256": session_hash,
                "content_sha256": content_hash,
                "approved_by": approved_by.strip(),
                "approval_rationale": approval_rationale.strip(),
            },
        }
        record = {
            "schema_version": 1,
            "import_id": import_id,
            "workspace_id": workspace_id.strip(),
            "client_id": client_id.strip(),
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
        }

        replay = document.exists() or manifest.exists()
        if document.exists():
            if document.read_text(encoding="utf-8") != work_product + "\n":
                raise ResearchEvidenceImportError("immutable research evidence collision")
        if manifest.exists():
            try:
                existing = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ResearchEvidenceImportError("research evidence manifest is unreadable") from exc
            if not isinstance(existing, Mapping) or existing.get("source") != source:
                raise ResearchEvidenceImportError("immutable research evidence manifest collision")

        imports_root.mkdir(parents=True, exist_ok=True)
        if not document.exists():
            self._write_immutable(document, (work_product + "\n").encode("utf-8"))
        if not manifest.exists():
            self._write_immutable(
                manifest,
                (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
        return ImportedResearchEvidence(import_id, str(document), str(manifest), source, replay)

    @staticmethod
    def _final_work_product(raw: bytes) -> tuple[str, str, str]:
        candidates: list[tuple[str, str, str]] = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ResearchEvidenceImportError(
                    f"research session contains invalid JSON at line {line_number}"
                ) from exc
            message = record.get("message") if isinstance(record, Mapping) else None
            if (
                not isinstance(message, Mapping)
                or message.get("role") != "assistant"
                or message.get("stopReason") != "stop"
            ):
                continue
            parts = message.get("content")
            if not isinstance(parts, list):
                continue
            text = "\n\n".join(
                str(part.get("text") or "").strip()
                for part in parts
                if isinstance(part, Mapping)
                and part.get("type") == "text"
                and str(part.get("text") or "").strip()
            ).strip()
            if text:
                candidates.append(
                    (
                        text,
                        str(record.get("id") or message.get("id") or f"line-{line_number}"),
                        str(record.get("timestamp") or message.get("timestamp") or ""),
                    )
                )
        if not candidates:
            raise ResearchEvidenceImportError("research session has no completed final work product")
        work_product, message_id, completed_at = candidates[-1]
        if len(work_product.split()) < 100:
            raise ResearchEvidenceImportError("completed research work product is not substantive enough to import")
        return work_product, message_id, completed_at

    @staticmethod
    def _write_immutable(path: Path, payload: bytes) -> None:
        if path.exists():
            if path.read_bytes() != payload:
                raise ResearchEvidenceImportError("immutable research evidence collision")
            return
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
