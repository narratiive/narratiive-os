from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from runtime.tony_command_service import CommandResponse


class TonyAdaptiveTestApprovalCommandService:
    """Carry a reviewed adaptive redesign into a truthful controlled-test handoff."""

    _APPROVAL_MARKERS = (
        "approve it",
        "approved",
        "looks good, approve it",
        "looks good approve it",
        "run the test",
        "go ahead with the test",
        "go ahead with that test",
        "let's test it",
        "lets test it",
    )

    def __init__(self, command_service) -> None:
        self.command_service = command_service
        self._adaptive_context: dict[str, Any] | None = None
        self._reviewed_test: dict[str, Any] | None = None

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split())
        lowered = normalized.casefold().strip().rstrip(".!?")
        artefacts = tuple(item for item in objects if isinstance(item, dict))

        if self._reviewed_test and self._is_approval(lowered):
            return self._prepare_controlled_test()

        response = self.command_service.execute(command, artefacts)
        self._observe(response)
        return response

    def _observe(self, response: CommandResponse) -> None:
        data = response.data if isinstance(response.data, dict) else {}
        if response.command == "executive_adaptation_handoff" and data.get("adaptation_status") == "worker_handoff_ready":
            handoff = data.get("handoff") if isinstance(data.get("handoff"), dict) else {}
            priority = handoff.get("priority") if isinstance(handoff.get("priority"), dict) else {}
            self._adaptive_context = {
                "priority": dict(priority),
                "handoff": dict(handoff),
            }
            self._reviewed_test = None
            return

        if response.command != "executive_adaptation_review":
            return

        status = str(data.get("adaptation_status") or "")
        if status == "revision_required":
            self._reviewed_test = None
            return
        if status != "ready_for_approval" or not self._adaptive_context:
            return

        review = data.get("review") if isinstance(data.get("review"), dict) else {}
        self._reviewed_test = {
            "priority": dict(self._adaptive_context.get("priority") or {}),
            "review": dict(review),
        }

    def _prepare_controlled_test(self) -> CommandResponse:
        assert self._reviewed_test is not None
        reviewed = dict(self._reviewed_test)
        priority = reviewed.get("priority") if isinstance(reviewed.get("priority"), dict) else {}
        review = reviewed.get("review") if isinstance(reviewed.get("review"), dict) else {}
        key = str(priority.get("key") or "adaptive-test")
        label = str(priority.get("label") or key or "the adapted priority")
        approved_at = datetime.now(timezone.utc).isoformat()
        action_id = f"adaptive:{key}:{approved_at}"

        package = {
            "action_id": action_id,
            "task_type": "controlled_adaptive_test",
            "priority": dict(priority),
            "owner": "Tony",
            "execution_router": "appropriate_execution_tool",
            "approved_design": {
                "recommendation": str(review.get("recommendation") or "").strip(),
                "changed_variable": str(review.get("changed_variable") or "").strip(),
                "success_signal": str(review.get("success_signal") or "").strip(),
            },
            "required_evidence": {
                "execution": "matching action_id plus verified execution evidence",
                "outcome": "matched business-outcome evidence against the declared success signal",
            },
            "status": "approved_awaiting_execution_confirmation",
            "external_action_taken": False,
        }
        self._reviewed_test = None
        self._adaptive_context = None
        return CommandResponse(
            command="executive_adaptive_test_approval",
            status="healthy",
            message=(
                f"Approved. I have turned the redesign for {label} into a controlled test package. "
                "The changed variable and success signal are locked into the handoff, so we can judge the result properly. "
                "It is approved for execution, but I will not call it executed or successful until matching evidence comes back."
            ),
            data={
                "intent": "execute_controlled_adaptive_test",
                "adaptation_status": "approved_test_handoff_ready",
                "execution_package": package,
                "execution_performed": False,
                "external_action_taken": False,
            },
        )

    @classmethod
    def _is_approval(cls, lowered: str) -> bool:
        return any(marker == lowered or lowered.endswith(f" {marker}") for marker in cls._APPROVAL_MARKERS)
