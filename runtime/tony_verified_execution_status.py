from __future__ import annotations

from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyVerifiedExecutionStatusCommandService:
    """Answer natural execution-status questions from already-verified worker evidence.

    This layer never infers that an action happened from intent or approval. It only
    answers from the most recent verified dispatch context and deliberately separates
    execution proof from business-outcome proof.
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

    def __init__(self, command_service) -> None:
        self.command_service = command_service

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
        if not execution_query and not outcome_query:
            return self.command_service.execute(command, objects)

        context = getattr(self.command_service, "_last_verified_result", None)
        if not isinstance(context, dict):
            return self.command_service.execute(command, objects)

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
            return self.command_service.execute(command, objects)

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
                    "I would wait for outcome evidence such as a reply, booking, conversion or other agreed success signal before calling it successful."
                ),
                data={
                    "intent": "separate_execution_from_outcome",
                    "worker": worker,
                    "execution_verified": True,
                    "execution_result_id": result_id,
                    "business_outcome_verified": False,
                    "outcome_state": "unverified",
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
                "external_action_taken": True,
            },
        )

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
