from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.models import WorkflowState


PILOT_WORKFLOWS = (
    "growth_diagnostic_to_blueprint_lite",
    "blueprint_lite_to_discovery_preparation",
    "discovery_evidence_to_growth_sprint_proposal",
    "growth_sprint_to_research_engine",
    "research_to_growth_blueprint",
)
PILOT_APPROVAL_GATES = (
    "growth_diagnostic_to_blueprint_lite",
    "blueprint_lite_to_discovery_preparation",
    "discovery_evidence_to_growth_sprint_proposal",
    "research_to_growth_blueprint",
)
_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,127}$")
_SECRET_MARKERS = ("password", "secret", "token", "api_key", "apikey", "credential")


class PilotValidationError(ValueError):
    """A pilot manifest or acceptance state failed a fixed, non-sensitive check."""


@dataclass(frozen=True, slots=True)
class PilotManifest:
    pilot_id: str
    workspace_id: str
    client_id: str
    synthetic_contact_email: str
    company_label: str
    approved_by: str
    approved_at: str
    purpose: str
    evidence_sources: tuple[dict[str, Any], ...]
    workflow_ids: tuple[str, ...]
    approval_gates: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PilotManifest":
        if int(value.get("schema_version") or 0) != 1:
            raise PilotValidationError("pilot_manifest_schema_unsupported")
        if _contains_secret_field(value):
            raise PilotValidationError("pilot_manifest_contains_secret_field")
        pilot_id = _safe_id(value.get("pilot_id"), "pilot_id")
        workspace_id = _safe_id(value.get("workspace_id"), "workspace_id")
        client_id = _safe_id(value.get("client_id"), "client_id")
        label = str(value.get("label") or "").strip()
        if not label.startswith("AUTHORISED REAL-EVIDENCE PILOT"):
            raise PilotValidationError("pilot_label_not_explicit")
        email = str(value.get("synthetic_contact_email") or "").strip().casefold()
        if "@" not in email or not email.endswith(".invalid"):
            raise PilotValidationError("pilot_contact_must_use_invalid_domain")
        authorisation = value.get("authorisation")
        if not isinstance(authorisation, Mapping) or authorisation.get("status") != "approved":
            raise PilotValidationError("pilot_authorisation_missing")
        approved_by = str(authorisation.get("approved_by") or "").strip()
        approved_at = str(authorisation.get("approved_at") or "").strip()
        purpose = str(authorisation.get("purpose") or "").strip()
        if not approved_by or not approved_at or len(purpose.split()) < 5:
            raise PilotValidationError("pilot_authorisation_incomplete")
        if value.get("external_actions_allowed") is not False:
            raise PilotValidationError("pilot_external_actions_must_be_disabled")
        workflow_ids = tuple(str(item) for item in value.get("workflow_ids", ()))
        if workflow_ids != PILOT_WORKFLOWS:
            raise PilotValidationError("pilot_workflow_sequence_invalid")
        approval_gates = tuple(str(item) for item in value.get("approval_gates", ()))
        if approval_gates != PILOT_APPROVAL_GATES:
            raise PilotValidationError("pilot_approval_gates_invalid")
        raw_sources = value.get("evidence_sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise PilotValidationError("pilot_evidence_sources_missing")
        sources = tuple(_validate_source(item) for item in raw_sources)
        source_ids = [item["source_id"] for item in sources]
        if len(source_ids) != len(set(source_ids)):
            raise PilotValidationError("pilot_evidence_source_ids_duplicate")
        return cls(
            pilot_id=pilot_id,
            workspace_id=workspace_id,
            client_id=client_id,
            synthetic_contact_email=email,
            company_label=label,
            approved_by=approved_by,
            approved_at=approved_at,
            purpose=purpose,
            evidence_sources=sources,
            workflow_ids=workflow_ids,
            approval_gates=approval_gates,
        )

    @classmethod
    def load(cls, path: str | Path) -> "PilotManifest":
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PilotValidationError("pilot_manifest_unreadable") from exc
        if not isinstance(value, Mapping):
            raise PilotValidationError("pilot_manifest_must_be_object")
        return cls.from_mapping(value)

    def fingerprint(self) -> str:
        material = {
            "pilot_id": self.pilot_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "synthetic_contact_email": self.synthetic_contact_email,
            "company_label": self.company_label,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "purpose": self.purpose,
            "evidence_sources": list(self.evidence_sources),
            "workflow_ids": list(self.workflow_ids),
            "approval_gates": list(self.approval_gates),
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PilotAuditLedger:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def record_preflight(self, manifest: PilotManifest) -> dict[str, Any]:
        scope = hashlib.sha256(f"{manifest.workspace_id}:{manifest.client_id}".encode()).hexdigest()[:24]
        path = self.root / scope / f"{manifest.pilot_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(path.suffix + ".lock")
        with lock_path.open("a", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            events = self._load(path)
            fingerprint = manifest.fingerprint()
            event_id = f"pilot-preflight-{fingerprint[:24]}"
            for event in events:
                if event.get("event_id") == event_id:
                    return {"status": "duplicate_suppressed", "event_id": event_id, "ledger": str(path)}
            previous_hash = str(events[-1].get("event_hash") or "") if events else ""
            event = {
                "event_id": event_id,
                "event_type": "pilot.preflight_passed",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "manifest_fingerprint": fingerprint,
                "pilot_id": manifest.pilot_id,
                "workspace_id": manifest.workspace_id,
                "client_id": manifest.client_id,
                "approved_by": manifest.approved_by,
                "approved_at": manifest.approved_at,
                "source_ids": [item["source_id"] for item in manifest.evidence_sources],
                "workflow_ids": list(manifest.workflow_ids),
                "approval_gates": list(manifest.approval_gates),
                "external_actions_allowed": False,
                "previous_hash": previous_hash,
            }
            event["event_hash"] = _event_hash(event)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return {"status": "recorded", "event_id": event_id, "ledger": str(path)}

    @staticmethod
    def _load(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        previous_hash = ""
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if not isinstance(event, dict) or event.get("previous_hash") != previous_hash:
                    raise PilotValidationError("pilot_ledger_integrity_failed")
                expected = _event_hash({key: value for key, value in event.items() if key != "event_hash"})
                if event.get("event_hash") != expected:
                    raise PilotValidationError("pilot_ledger_integrity_failed")
                events.append(event)
                previous_hash = expected
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PilotValidationError("pilot_ledger_unreadable") from exc
        return events


def inspect_pilot(manifest: PilotManifest, states: Iterable[WorkflowState]) -> dict[str, Any]:
    scoped = [
        state
        for state in states
        if state.workspace_id == manifest.workspace_id and state.client_id == manifest.client_id
    ]
    results: list[dict[str, Any]] = []
    all_passed = True
    for workflow_id in manifest.workflow_ids:
        candidates = sorted(
            (state for state in scoped if state.workflow_id == workflow_id),
            key=lambda state: state.updated_at,
            reverse=True,
        )
        if not candidates:
            results.append({"workflow_id": workflow_id, "present": False, "accepted": False})
            all_passed = False
            continue
        state = candidates[0]
        stage = state.stages[-1]
        quality_passed = bool(stage.quality_result and stage.quality_result.get("passed") is True)
        artifact_present = bool(stage.output_artifacts)
        approval_required = workflow_id in manifest.approval_gates
        approval_evidenced = bool(state.approval_history) if approval_required else True
        status_ok = state.status.value in ({"complete", "awaiting_approval"} if approval_required else {"complete"})
        accepted = all(
            (
                quality_passed,
                artifact_present,
                approval_evidenced or state.status.value == "awaiting_approval",
                status_ok,
                state.external_action_taken is False,
            )
        )
        all_passed = all_passed and accepted
        results.append(
            {
                "workflow_id": workflow_id,
                "run_id": state.run_id,
                "present": True,
                "status": state.status.value,
                "quality_passed": quality_passed,
                "artifact_present": artifact_present,
                "approval_required": approval_required,
                "approval_status": state.approval_status,
                "approval_evidenced": approval_evidenced,
                "external_action_taken": state.external_action_taken,
                "accepted": accepted,
            }
        )
    return {
        "pilot_id": manifest.pilot_id,
        "ready": all_passed,
        "external_action_taken": any(state.external_action_taken for state in scoped),
        "workflows": results,
    }


def _validate_source(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PilotValidationError("pilot_evidence_source_invalid")
    source_id = _safe_id(value.get("source_id"), "source_id")
    source_type = str(value.get("source_type") or "").strip()
    location = str(value.get("uri") or value.get("location") or "").strip()
    policy = value.get("policy")
    provenance = value.get("provenance")
    if source_type not in {"document", "web", "transcript", "notes"} or not location:
        raise PilotValidationError("pilot_evidence_source_invalid")
    if not isinstance(policy, Mapping) or policy.get("approved") is not True:
        raise PilotValidationError("pilot_evidence_source_not_approved")
    if not isinstance(provenance, Mapping) or not all(
        str(provenance.get(key) or "").strip() for key in ("origin", "captured_at", "permitted_use")
    ):
        raise PilotValidationError("pilot_evidence_provenance_incomplete")
    return dict(value)


def _safe_id(value: Any, field: str) -> str:
    rendered = str(value or "").strip()
    if not _SAFE_ID.fullmatch(rendered):
        raise PilotValidationError(f"pilot_{field}_invalid")
    return rendered


def _contains_secret_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).casefold()
            if any(marker in lowered for marker in _SECRET_MARKERS):
                return True
            if _contains_secret_field(item):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_field(item) for item in value)
    return False


def _event_hash(event: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(event), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
