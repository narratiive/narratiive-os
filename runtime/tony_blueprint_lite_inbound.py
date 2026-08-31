from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from runtime.inbound_leads import InboundLead
from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_tool_routing import TonyExecutiveToolRouter


DispatchHandler = Callable[[dict[str, Any]], dict[str, Any]]

_BLUEPRINT_LITE_SOURCES = {"growth diagnostic", "tally", "website"}
_REQUIRED_LINEAGE_KEYS = ("fact", "interpretation", "hypothesis")
_FALSE_EXECUTION_MARKERS = (
    "email sent",
    "sent to the client",
    "sent to the prospect",
    "shared with the client",
    "calendar event created",
    "meeting booked",
    "updated notion",
)


class FileBlueprintLitePreparationStore:
    """Durable idempotent state for inbound Blueprint Lite preparation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def read_all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                return {}
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Blueprint Lite state is unreadable: {exc}") from exc
            if not isinstance(raw, dict):
                raise RuntimeError("Blueprint Lite state must be a JSON object")
            return {str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)}

    def get(self, lead_id: str) -> dict[str, Any] | None:
        value = self.read_all().get(lead_id)
        return dict(value) if value is not None else None

    def put(self, lead_id: str, state: Mapping[str, Any]) -> None:
        with self._lock:
            records = self.read_all()
            records[lead_id] = dict(state)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(self.path)


class TonyInboundBlueprintLiteService:
    """Queue and execute safe Blueprint Lite preparation after lead ingestion.

    Tony acknowledges the inbound request without waiting for a model call. One
    durable preparation job is keyed to the stable lead identity and input
    fingerprint. A daemon worker then consumes Tony's existing router, explicitly
    configured Claude dispatcher and existing evidence verifier. No external write
    permission is added here.
    """

    def __init__(
        self,
        store: FileBlueprintLitePreparationStore,
        *,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        router: TonyExecutiveToolRouter | None = None,
    ) -> None:
        self.store = store
        self.dispatchers = dict(dispatchers or {})
        self.router = router or TonyExecutiveToolRouter()
        self._active: set[str] = set()
        self._active_lock = threading.Lock()

    def enqueue(self, lead: InboundLead, raw_payload: Mapping[str, Any]) -> dict[str, Any]:
        source = lead.source.strip().casefold()
        if source not in _BLUEPRINT_LITE_SOURCES:
            return {
                "state": "not_applicable",
                "lead_id": lead.lead_id,
                "reason": "source_not_growth_diagnostic",
                "external_action_taken": False,
            }

        payload = _json_safe_mapping(raw_payload)
        fingerprint = _fingerprint(payload)
        existing = self.store.get(lead.lead_id)

        if existing is not None and existing.get("input_fingerprint") == fingerprint:
            if existing.get("state") == "dispatcher_unavailable" and "Claude" in self.dispatchers:
                existing["state"] = "preparation_queued"
                existing["blocker"] = ""
                existing["updated_at"] = _now()
                self.store.put(lead.lead_id, existing)
            return self._public_state(existing, replay=True)

        versions = []
        if existing is not None and isinstance(existing.get("versions"), list):
            versions = list(existing["versions"])

        state: dict[str, Any] = {
            "lead_id": lead.lead_id,
            "contact": lead.contact,
            "company": lead.company,
            "email": lead.email,
            "source": lead.source,
            "input_fingerprint": fingerprint,
            "diagnostic_input_package": payload,
            "state": "preparation_queued",
            "attempt_count": 0,
            "versions": versions,
            "approval_required": False,
            "external_action_taken": False,
            "updated_at": _now(),
        }
        if "Claude" not in self.dispatchers:
            state["state"] = "dispatcher_unavailable"
            state["blocker"] = "claude_dispatcher_not_configured"
        self.store.put(lead.lead_id, state)
        return self._public_state(state)

    def enqueue_and_start(self, lead: InboundLead, raw_payload: Mapping[str, Any]) -> dict[str, Any]:
        result = self.enqueue(lead, raw_payload)
        if result.get("state") == "preparation_queued":
            self.start(lead.lead_id)
        return result

    def start(self, lead_id: str) -> bool:
        with self._active_lock:
            if lead_id in self._active:
                return False
            state = self.store.get(lead_id)
            if state is None or state.get("state") != "preparation_queued":
                return False
            self._active.add(lead_id)
        thread = threading.Thread(
            target=self._run,
            args=(lead_id,),
            name=f"blueprint-lite-{lead_id[:24]}",
            daemon=True,
        )
        thread.start()
        return True

    def recover_pending(self) -> int:
        recovered = 0
        for lead_id, state in self.store.read_all().items():
            current = str(state.get("state") or "")
            if current == "dispatching":
                state["state"] = "preparation_queued"
                state["blocker"] = "recovered_after_runtime_restart"
                state["updated_at"] = _now()
                self.store.put(lead_id, state)
                current = "preparation_queued"
            if current == "dispatcher_unavailable" and "Claude" in self.dispatchers:
                state["state"] = "preparation_queued"
                state["blocker"] = ""
                state["updated_at"] = _now()
                self.store.put(lead_id, state)
                current = "preparation_queued"
            if current == "preparation_queued" and self.start(lead_id):
                recovered += 1
        return recovered

    def process(self, lead_id: str) -> dict[str, Any]:
        state = self.store.get(lead_id)
        if state is None:
            return {"state": "missing", "lead_id": lead_id, "external_action_taken": False}
        if state.get("state") != "preparation_queued":
            return self._public_state(state)

        handler = self.dispatchers.get("Claude")
        if handler is None:
            state.update(
                {
                    "state": "dispatcher_unavailable",
                    "blocker": "claude_dispatcher_not_configured",
                    "updated_at": _now(),
                }
            )
            self.store.put(lead_id, state)
            return self._public_state(state)

        lead = InboundLead.from_mapping(
            {
                "lead_id": lead_id,
                "contact": state.get("contact"),
                "company": state.get("company"),
                "email": state.get("email"),
                "source": state.get("source"),
                "status": "New",
            }
        )
        payload = state.get("diagnostic_input_package")
        if not isinstance(payload, dict):
            state.update(
                {
                    "state": "blocked",
                    "blocker": "diagnostic_input_package_missing",
                    "updated_at": _now(),
                }
            )
            self.store.put(lead_id, state)
            return self._public_state(state)

        handoff = self.router.route(
            {
                "area": "commercial",
                "label": f"Blueprint Lite for {lead.company or lead.contact}",
                "action": self._instruction(lead),
                "target": {
                    "lead_id": lead.lead_id,
                    "contact": lead.contact,
                    "company": lead.company,
                    "email": lead.email,
                    "source": lead.source,
                    "diagnostic_input_package": payload,
                    "product": "Blueprint Lite",
                },
            }
        )
        dispatch = handoff.get("dispatch") if isinstance(handoff.get("dispatch"), dict) else {}
        state["dispatch"] = dict(dispatch)

        if not (
            dispatch.get("worker") == "Claude"
            and dispatch.get("execution_mode") == "autonomous_prepare"
            and dispatch.get("eligible") is True
            and dispatch.get("state") == "ready_for_autonomous_dispatch"
        ):
            state.update(
                {
                    "state": "blocked",
                    "blocker": "unsafe_or_invalid_dispatch_contract",
                    "updated_at": _now(),
                }
            )
            self.store.put(lead_id, state)
            return self._public_state(state)

        state["attempt_count"] = int(state.get("attempt_count") or 0) + 1
        state["state"] = "dispatching"
        state["updated_at"] = _now()
        self.store.put(lead_id, state)

        try:
            evidence = handler(dict(dispatch))
        except Exception as exc:
            state.update(
                {
                    "state": "dispatch_failed",
                    "blocker": "claude_dispatch_failed",
                    "failure": str(exc)[:500],
                    "updated_at": _now(),
                }
            )
            self.store.put(lead_id, state)
            return self._public_state(state)

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            state.update(
                {
                    "state": "dispatch_unverified",
                    "blocker": "claude_evidence_unverified",
                    "failure": reason,
                    "updated_at": _now(),
                }
            )
            self.store.put(lead_id, state)
            return self._public_state(state)

        quality = self._quality_gate(evidence)
        state["quality_gate"] = quality
        if not quality["passed"]:
            state.update(
                {
                    "state": "blocked",
                    "blocker": "blueprint_lite_quality_gate",
                    "failed_checks": list(quality["failed_checks"]),
                    "updated_at": _now(),
                }
            )
            self.store.put(lead_id, state)
            return self._public_state(state)

        versions = list(state.get("versions") or [])
        version_number = len(versions) + 1
        version = {
            "version": version_number,
            "created_at": _now(),
            "input_fingerprint": state.get("input_fingerprint"),
            "dispatch": dict(dispatch),
            "evidence": dict(evidence),
            "quality_gate": quality,
        }
        versions.append(version)
        state.update(
            {
                "state": "awaiting_review",
                "blocker": "human_review_required",
                "versions": versions,
                "current_version": version_number,
                "approval_required": True,
                "updated_at": _now(),
            }
        )
        state.pop("failure", None)
        state.pop("failed_checks", None)
        self.store.put(lead_id, state)
        return self._public_state(state)

    def status(self, lead_id: str) -> dict[str, Any] | None:
        state = self.store.get(lead_id)
        return self._public_state(state) if state is not None else None

    def _run(self, lead_id: str) -> None:
        try:
            self.process(lead_id)
        finally:
            with self._active_lock:
                self._active.discard(lead_id)

    @staticmethod
    def _instruction(lead: InboundLead) -> str:
        subject = lead.company or lead.contact
        return (
            f"Prepare the canonical Blueprint Lite for {subject} from the completed Growth Diagnostic input package supplied in target context. "
            "This is reversible internal preparation only. Do not send anything. "
            "Use only the supplied diagnostic evidence and genuinely verified public sources. Preserve source lineage and clearly separate facts, "
            "interpretations and hypotheses. Explicitly report whether the supplied diagnostic package contains enough information to represent the "
            "diagnostic faithfully; do not silently fill missing diagnostic inputs. Identify one company-specific growth tension, one consequential "
            "but provisional opportunity, and 3–4 meaningful questions to answer next. Produce only the internal human-review-ready Blueprint Lite "
            "defined by the canonical product contract. Do not create the paid Growth Blueprint, share a file, update Notion, create a Calendar event, "
            "book Discovery, or change any external state."
        )

    @classmethod
    def _quality_gate(cls, evidence: Any) -> dict[str, Any]:
        if not isinstance(evidence, dict):
            return {"passed": False, "failed_checks": ["structured evidence missing"], "checks": {}}

        lineage = evidence.get("fact_interpretation_hypothesis_lineage")
        lineage_ok = isinstance(lineage, dict) and all(_meaningful(lineage.get(key)) for key in _REQUIRED_LINEAGE_KEYS)
        questions = evidence.get("questions_to_answer_next")
        questions_ok = isinstance(questions, list) and 3 <= len([item for item in questions if _meaningful(item)]) <= 4
        sources = evidence.get("source_backed_evidence") or evidence.get("sources")
        returned_gate = evidence.get("quality_gate") if isinstance(evidence.get("quality_gate"), dict) else {}
        coverage = evidence.get("diagnostic_input_coverage") if isinstance(evidence.get("diagnostic_input_coverage"), dict) else {}
        recommendation = str(evidence.get("recommendation") or "").strip().casefold()
        rendered = json.dumps(evidence, sort_keys=True).casefold()

        checks = {
            "blueprint_lite_present": _meaningful(evidence.get("blueprint_lite")),
            "diagnostic_signals_used": _meaningful(evidence.get("diagnostic_signals_used")),
            "diagnostic_input_coverage_complete": coverage.get("complete") is True,
            "outside_in_evidence_present": _meaningful(sources),
            "evidence_gaps_explicit": "evidence_gaps" in evidence,
            "fact_interpretation_hypothesis_lineage": lineage_ok,
            "growth_tension_present": _meaningful(evidence.get("growth_tension")),
            "provisional_opportunity_present": _meaningful(evidence.get("provisional_opportunity")),
            "three_to_four_next_questions": questions_ok,
            "worker_marks_human_review_ready": returned_gate.get("human_review_ready") is True,
            "recommendation_is_advance": recommendation == "advance",
            "no_false_external_execution_claim": not any(marker in rendered for marker in _FALSE_EXECUTION_MARKERS),
        }
        failed = [name.replace("_", " ") for name, passed in checks.items() if not passed]
        return {"passed": not failed, "failed_checks": failed, "checks": checks}

    @staticmethod
    def _public_state(state: Mapping[str, Any], *, replay: bool = False) -> dict[str, Any]:
        return {
            "state": str(state.get("state") or "unknown"),
            "lead_id": str(state.get("lead_id") or ""),
            "current_version": state.get("current_version"),
            "attempt_count": int(state.get("attempt_count") or 0),
            "approval_required": bool(state.get("approval_required")),
            "blocker": str(state.get("blocker") or ""),
            "failed_checks": list(state.get("failed_checks") or []),
            "replay": replay,
            "external_action_taken": False,
        }


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value), sort_keys=True, default=str))


def _meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
