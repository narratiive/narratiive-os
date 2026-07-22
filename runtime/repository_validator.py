from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_OBJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
_APPROVED_STATUSES = {"approved", "active", "superseded", "archived"}


@dataclass(frozen=True)
class ValidationFinding:
    severity: str
    code: str
    message: str
    object_id: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    status: str
    objects_validated: int
    errors: tuple[ValidationFinding, ...]
    warnings: tuple[ValidationFinding, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "objects_validated": self.objects_validated,
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
        }


class GrowthObjectValidator:
    """Validate canonical Growth Objects using the shared schema as the contract source."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self.required = tuple(schema.get("required", ()))
        properties = schema.get("properties", {})
        self.object_types = set(properties.get("object_type", {}).get("enum", ()))
        self.lifecycle_statuses = set(
            schema.get("$defs", {}).get("lifecycleStatus", {}).get("enum", ())
        )

    @classmethod
    def from_path(cls, schema_path: str | Path) -> "GrowthObjectValidator":
        with Path(schema_path).open(encoding="utf-8") as handle:
            return cls(json.load(handle))

    def validate(self, objects: Iterable[dict[str, Any]]) -> ValidationReport:
        records = list(objects)
        findings: list[ValidationFinding] = []
        records_by_id: dict[str, dict[str, Any]] = {}

        for record in records:
            findings.extend(self._validate_record(record))
            object_id = record.get("id")
            if isinstance(object_id, str):
                if object_id in records_by_id:
                    findings.append(
                        self._error("duplicate_id", f"duplicate object id: {object_id}", record)
                    )
                else:
                    records_by_id[object_id] = record

        findings.extend(self._validate_relationships(records_by_id))
        errors = tuple(item for item in findings if item.severity == "error")
        warnings = tuple(item for item in findings if item.severity == "warning")
        return ValidationReport(
            status="fail" if errors else "pass",
            objects_validated=len(records),
            errors=errors,
            warnings=warnings,
        )

    def _validate_record(self, record: dict[str, Any]) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for field in self.required:
            if field not in record:
                findings.append(self._error("missing_required_field", f"missing required field: {field}", record))

        object_id = record.get("id")
        if not isinstance(object_id, str) or not _OBJECT_ID.fullmatch(object_id):
            findings.append(self._error("invalid_id", "id must match the canonical object-id format", record))

        object_type = record.get("object_type")
        if object_type not in self.object_types:
            findings.append(self._error("invalid_object_type", f"unsupported object_type: {object_type}", record))

        version = record.get("version")
        if not isinstance(version, str) or not _VERSION.fullmatch(version):
            findings.append(self._error("invalid_version", "version must use semantic numeric form such as 1.0", record))

        status = record.get("status")
        if status not in self.lifecycle_statuses:
            findings.append(self._error("invalid_status", f"unsupported lifecycle status: {status}", record))

        for field in ("created_at", "updated_at"):
            if not self._is_datetime(record.get(field)):
                findings.append(self._error("invalid_datetime", f"{field} must be an ISO-8601 date-time", record))

        approved_by = record.get("approved_by")
        approved_at = record.get("approved_at")
        if status in _APPROVED_STATUSES:
            if not isinstance(approved_by, str) or not approved_by.strip():
                findings.append(self._error("missing_approval", "approved objects require approved_by", record))
            if not self._is_datetime(approved_at):
                findings.append(self._error("missing_approval", "approved objects require approved_at", record))
        elif approved_at is not None and not self._is_datetime(approved_at):
            findings.append(self._error("invalid_datetime", "approved_at must be null or an ISO-8601 date-time", record))

        parent_id = record.get("parent_object_id")
        if object_type == "growth_specification" and parent_id is not None:
            findings.append(self._error("invalid_parent", "growth_specification cannot have a parent", record))
        if object_type in self.object_types - {"growth_specification"}:
            if not isinstance(parent_id, str) or not parent_id.strip():
                findings.append(self._error("missing_parent", f"{object_type} requires parent_object_id", record))

        for field in ("source_object_ids", "child_object_ids"):
            value = record.get(field)
            if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
                findings.append(self._error("invalid_reference_list", f"{field} must be a list of non-empty strings", record))
            elif len(value) != len(set(value)):
                findings.append(self._error("duplicate_reference", f"{field} must contain unique ids", record))

        repository_path = record.get("repository_path")
        if not isinstance(repository_path, str) or not repository_path or repository_path.startswith("/") or ".." in Path(repository_path).parts or "\\" in repository_path:
            findings.append(self._error("invalid_repository_path", "repository_path must be a safe repository-relative path", record))

        commit_sha = record.get("commit_sha")
        if commit_sha is not None and (not isinstance(commit_sha, str) or not _COMMIT_SHA.fullmatch(commit_sha)):
            findings.append(self._error("invalid_commit_sha", "commit_sha must be null or a lowercase 40-character SHA", record))

        return findings

    def _validate_relationships(self, records: dict[str, dict[str, Any]]) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for object_id, record in records.items():
            parent_id = record.get("parent_object_id")
            if isinstance(parent_id, str):
                parent = records.get(parent_id)
                if parent is None:
                    findings.append(self._error("missing_parent_object", f"parent object not found: {parent_id}", record))
                elif object_id not in parent.get("child_object_ids", []):
                    findings.append(self._error("non_reciprocal_parent", f"parent {parent_id} does not list {object_id} as a child", record))

            for child_id in record.get("child_object_ids", []):
                child = records.get(child_id)
                if child is None:
                    findings.append(self._error("missing_child_object", f"child object not found: {child_id}", record))
                elif child.get("parent_object_id") != object_id:
                    findings.append(self._error("non_reciprocal_child", f"child {child_id} does not identify {object_id} as parent", record))

            for source_id in record.get("source_object_ids", []):
                if source_id not in records:
                    findings.append(self._warning("missing_source_object", f"source object not present in validation set: {source_id}", record))

        return findings

    @staticmethod
    def _is_datetime(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True

    @staticmethod
    def _error(code: str, message: str, record: dict[str, Any]) -> ValidationFinding:
        return ValidationFinding("error", code, message, record.get("id"), record.get("repository_path"))

    @staticmethod
    def _warning(code: str, message: str, record: dict[str, Any]) -> ValidationFinding:
        return ValidationFinding("warning", code, message, record.get("id"), record.get("repository_path"))


def load_object_records(root: str | Path) -> list[dict[str, Any]]:
    """Load JSON object records recursively from a repository directory."""
    records: list[dict[str, Any]] = []
    for path in sorted(Path(root).rglob("*.json")):
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            records.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            records.append(payload)
    return records
