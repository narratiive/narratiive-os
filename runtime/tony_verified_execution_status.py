from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from runtime.tony_command_service import CommandResponse


class TonyVerifiedExecutionStatusCommandService:
    """Answer execution-status questions and keep verified writes outcome-accountable.

    This layer never infers that an action happened from intent or approval. It only
    confirms execution from verified dispatch context, deliberately separates execution
    proof from business-outcome proof, and keeps a lightweight persistent watch on the
    most recent approved write until outcome evidence exists elsewhere in the system.
    """

    _EXECUTION_MARKERS = (
        "did that send",
        "did it send",
        "was that sent",
        "has that been sent",
        "did that go out",
        "did it go out",
        "did that happen",
        "has that happened",
        "is that done",
        "was that done",
        "has that been done",
    )
    _OUTCOME_MARKERS = (
        "did that work",
        "did it work",
        "was that successful",
        "was it successful",
        "did that achieve the result",
        "did it achieve the result",
    )
    _ACKNOWLEDGEMENT_PREFIXES = ("ok, ", "okay, ", "yes, ", "right, ", "great, ", "fine, ")
    _RESULT_ID_KEYS = ("message_id", "page_id", "record_id", "event_id", "commit_sha", "deployment_id", "id")

    def __init__(
        self,
        command_service,
        *,
        store_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
        check_after: timedelta = timedelta(hours=24),
    ) -> None:
        self.command_service = command_service
        self.store_path = store_path or Path(".runtime/verified-write-outcome-watch.json")
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.check_after = check_after
        self._awaiting_write_outcome = self._load_watch()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold()
        execution_query = self._matches(normalized, self._EXECUTION_MARKERS)
        outcome_query = self._matches(normalized, self._OUTCOME_MARKERS)
        if execution_query or outcome_query:
            status_response = self._status_response(outcome_query=outcome_query)
            if status_response is not None:
                return status_response

        response = self.command_service.execute(command, objects)
        self._capture_verified_approved_write(response)
        if response.command in {"morning", "evening"}:
            response = self._augment_brief_with_outcome_watch(response)
        return response

    def _status_response(self, *, outcome_query: bool) -> CommandResponse | None:
        context = getattr(self.command_service, "_last_verified_result", None)
        if not isinstance(context, dict):
            return None

        stale_check = getattr(self.command_service, "_context_is_stale", None)
        if callable(stale_check) and stale_check(context):
            setattr(self.command_service, "_last_verified_result", None)
            clear = getattr(self.command_service, "_clear_context", None)
            if callable(clear):
                clear()
            return CommandResponse(
                command="verified_execution_status",
                status="healthy",
                message=(
                    "I have an older execution record, but it is too stale to use as current confirmation. "
                    "I would refresh the evidence before making a claim about the action."
                ),
                data={
                    "intent": "verify_recent_execution",
                    "execution_verified": False,
                    "context_state": "stale",
                    "business_outcome_verified": False,
                    "external_action_taken": False,
                },
            )

        dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
        evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
        if str(dispatch.get("execution_mode") or "").strip() != "approval_gated_write":
            return None

        worker = str(context.get("worker") or dispatch.get("worker") or "the worker").strip()
        result_id = self._result_id(evidence)
        mutation = self._mutation_label(worker, evidence)

        if outcome_query:
            return CommandResponse(
                command="verified_execution_outcome",
                status="healthy",
                message=(
                    f"The {mutation} is verified from {worker}'s returned execution evidence. "
                    "That proves the action happened; it does not prove the business outcome worked. "
                    "I am keeping the outcome open until there is evidence such as a reply, booking, conversion or other agreed success signal."
                ),
                data={
                    "intent": "separate_execution_from_outcome",
                    "worker": worker,
                    "execution_verified": True,
                    "execution_result_id": result_id,
                    "business_outcome_verified": False,
                    "outcome_state": "unverified",
                    "outcome_watch_active": bool(self._awaiting_write_outcome),
                    "external_action_taken": True,
                },
            )

        return CommandResponse(
            command="verified_execution_status",
            status="healthy",
            message=(
                f"Yes. {worker} returned verified evidence that the {mutation} completed. "
                "I am treating the execution as confirmed, while keeping the business outcome separate until there is outcome evidence."
            ),
            data={
                "intent": "confirm_verified_execution",
                "worker": worker,
                "execution_verified": True,
                "execution_result_id": result_id,
                "business_outcome_verified": False,
                "outcome_watch_active": bool(self._awaiting_write_outcome),
                "external_action_taken": True,
            },
        )

    def _capture_verified_approved_write(self, response: CommandResponse) -> None:
        data = response.data if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "approved_step_verified":
            return
        result = data.get("dispatch_result") if isinstance(data.get("dispatch_result"), dict) else {}
        evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
        handoff = data.get("execution_handoff") if isinstance(data.get("execution_handoff"), dict) else {}
        dispatch = handoff.get("dispatch") if isinstance(handoff.get("dispatch"), dict) else {}
        worker = str(result.get("worker") or dispatch.get("worker") or "").strip()
        if not worker or not evidence or str(dispatch.get("execution_mode") or "") != "approval_gated_write":
            return

        action = str(handoff.get("action") or dispatch.get("action") or "approved action").strip()
        target = dispatch.get("target") if isinstance(dispatch.get("target"), dict) else {}
        self._awaiting_write_outcome = {
            "worker": worker,
            "action": action,
            "target": dict(target),
            "execution_result_id": self._result_id(evidence),
            "verified_at": self._now().isoformat(),
            "execution_evidence_summary": str(data.get("executive_result") or response.message).strip(),
        }
        self._persist_watch()

    def _augment_brief_with_outcome_watch(self, response: CommandResponse) -> CommandResponse:
        if not self._awaiting_write_outcome or not self._watch_due():
            return response
        watch = dict(self._awaiting_write_outcome)
        worker = str(watch.get("worker") or "the worker")
        action = str(watch.get("action") or "the approved action")
        data = dict(response.data) if isinstance(response.data, dict) else {}
        data["verified_write_outcome_watch"] = {
            "status": "business_outcome_unverified",
            "worker": worker,
            "action": action,
            "verified_at": watch.get("verified_at"),
        }
        message = (
            f"Outcome check: {worker} completed the approved action to {action}, but I still do not have evidence of the business effect. "
            "Before we repeat or scale that move, I would get the result evidence and judge whether it actually worked.\n"
            f"{response.message}"
        )
        return CommandResponse(response.command, "attention", message, data)

    def _watch_due(self) -> bool:
        if not self._awaiting_write_outcome:
            return False
        value = str(self._awaiting_write_outcome.get("verified_at") or "").strip()
        try:
            verified = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        if verified.tzinfo is None:
            verified = verified.replace(tzinfo=timezone.utc)
        return self._now() - verified.astimezone(timezone.utc) >= self.check_after

    def _load_watch(self) -> dict[str, Any] | None:
        if not self.store_path.exists():
            return None
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        worker = str(raw.get("worker") or "").strip()
        verified_at = str(raw.get("verified_at") or "").strip()
        if not worker or not verified_at:
            return None
        return dict(raw)

    def _persist_watch(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._awaiting_write_outcome, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _matches(cls, lowered: str, markers: tuple[str, ...]) -> bool:
        candidate = lowered.strip().rstrip("?!.,")
        for prefix in cls._ACKNOWLEDGEMENT_PREFIXES:
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):].strip().rstrip("?!.,")
                break
        return any(candidate == marker or candidate.startswith(marker + " ") for marker in markers)

    @classmethod
    def _result_id(cls, evidence: dict[str, Any]) -> str:
        for key in cls._RESULT_ID_KEYS:
            value = str(evidence.get(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _mutation_label(worker: str, evidence: dict[str, Any]) -> str:
        if evidence.get("sent") is True or worker.casefold() == "gmail":
            return "approved message send"
        if evidence.get("updated") is True:
            return "approved update"
        if evidence.get("created") is True:
            return "approved creation"
        if evidence.get("published") is True:
            return "approved publication"
        if evidence.get("deployed") is True:
            return "approved deployment"
        if evidence.get("merged") is True or evidence.get("committed") is True:
            return "approved repository change"
        return "approved action"
