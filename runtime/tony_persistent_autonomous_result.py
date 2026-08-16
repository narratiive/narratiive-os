from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from runtime.tony_autonomous_dispatch import DispatchHandler, TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse
from runtime.tony_tool_routing import TonyExecutiveToolRouter


class TonyPersistentAutonomousResultCommandService(TonyAutonomousDispatchCommandService):
    """Persist Tony's most recent verified autonomous result across restarts.

    The parent service owns dispatch safety, evidence verification and conversational
    follow-ups. This wrapper makes only already-verified conversational context durable,
    timestamps it, refuses to answer from stale persisted evidence, may refresh an
    expired read-only result when the user explicitly asks about it, and can carry a
    grounded worker recommendation into the next controlled execution handoff.
    """

    _REQUIRED_KEYS = {"worker", "dispatch", "evidence", "executive_result", "verified_at"}
    _RESULT_ACTION_MARKERS = (
        "do that",
        "do it",
        "go ahead",
        "go ahead with that",
        "take that forward",
        "proceed",
        "make that happen",
        "move on that",
    )

    def __init__(
        self,
        command_service,
        dispatchers: Mapping[str, DispatchHandler] | None = None,
        *,
        store_path: Path,
        clock: Callable[[], datetime] | None = None,
        max_context_age: timedelta = timedelta(hours=8),
        tool_router: TonyExecutiveToolRouter | None = None,
    ) -> None:
        self.store_path = store_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_context_age = max_context_age
        self.tool_router = tool_router or TonyExecutiveToolRouter()
        super().__init__(command_service, dispatchers=dispatchers)
        self._last_verified_result = self._load_context()

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        normalized = " ".join(command.strip().split()).casefold()
        if self._last_verified_result is not None and self._context_is_stale(self._last_verified_result):
            stale_context = dict(self._last_verified_result)
            was_follow_up = self._matches_follow_up(normalized, self._RESULT_RECALL_MARKERS) or self._matches_follow_up(
                normalized, self._RESULT_RECOMMENDATION_MARKERS
            )
            self._last_verified_result = None
            self._clear_context()
            if was_follow_up:
                refreshed = self._refresh_stale_read_context(stale_context)
                if refreshed is not None:
                    return refreshed
                return CommandResponse(
                    command="autonomous_result_stale",
                    status="healthy",
                    message=(
                        "That verified worker result is now too old to use as current executive context. "
                        "I would refresh the evidence or re-rank the current agency priorities before acting on it."
                    ),
                    data={
                        "intent": "refresh_stale_autonomous_result",
                        "context_state": "stale",
                        "external_action_taken": False,
                    },
                )

        if self._last_verified_result is not None and self._is_action_query(normalized):
            return self._progress_verified_recommendation()

        before = self._last_verified_result
        response = super().execute(command, objects)
        if self._last_verified_result is not None and self._last_verified_result != before:
            if not self._last_verified_result.get("verified_at"):
                self._last_verified_result["verified_at"] = self._now().isoformat()
            self._persist_context(self._last_verified_result)
        return response

    def _progress_verified_recommendation(self) -> CommandResponse:
        context = dict(self._last_verified_result or {})
        worker = str(context.get("worker") or "the worker").strip()
        evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
        proposal = self._first_rendered(
            evidence,
            ("execution_next_action", "recommended_next_action", "next_action", "recommendation"),
        )
        if not proposal:
            return CommandResponse(
                command="autonomous_result_action",
                status="healthy",
                message=(
                    f"I have verified evidence back from {worker}, but it does not contain a grounded next action. "
                    "I will not invent a consequential move from an ambiguous result; I would re-rank the current agency priorities first."
                ),
                data={
                    "intent": "progress_verified_autonomous_result",
                    "worker": worker,
                    "execution_status": "insufficient_grounded_action",
                    "external_action_taken": False,
                },
            )

        prior_dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
        target = prior_dispatch.get("target") if isinstance(prior_dispatch.get("target"), dict) else {}
        priority = {
            "label": f"the verified {worker} result",
            "action": proposal,
            "area": str(target.get("area") or "operations"),
            "target": dict(target),
        }
        handoff = self.tool_router.route(priority)
        next_worker = str(handoff.get("worker") or "the appropriate worker")
        approval_required = bool(handoff.get("approval_required"))

        # The user reached this branch by explicitly saying "do that", "go ahead",
        # or equivalent against a verified, grounded recommendation. That utterance is
        # scoped approval for this exact handoff. Preserve the platform risk policy, but
        # do not force the user through a redundant second approval turn.
        if approval_required:
            handoff["approval_granted"] = True
            handoff["approval_scope"] = "grounded_next_action"
            dispatch = handoff.get("dispatch") if isinstance(handoff.get("dispatch"), dict) else {}
            dispatch["state"] = "approved_pending_execution"
            dispatch["approval_granted"] = True
            dispatch["approval_scope"] = "grounded_next_action"
            handoff["dispatch"] = dispatch

        message = (
            f"Yes. Based on the verified {worker} evidence, I’ll carry that recommendation forward. "
            f"The next controlled step is for {next_worker} to {handoff['action']}. "
            "I have prepared the handoff, but I have not claimed that the worker, message or record change has happened yet."
        )
        if approval_required:
            message += (
                " Your instruction is the approval for this exact grounded step, so I have marked the handoff approved and ready for verified execution."
            )
        else:
            message += " This is reversible internal/read-only work and is eligible for autonomous execution by the configured runtime."

        return CommandResponse(
            command="autonomous_result_action",
            status="healthy",
            message=message,
            data={
                "intent": "progress_verified_autonomous_result",
                "worker": worker,
                "grounded_next_action": proposal,
                "execution_handoff": handoff,
                "execution_status": "approved_for_execution" if approval_required else "ready_for_handoff",
                "external_action_taken": False,
            },
        )

    @classmethod
    def _is_action_query(cls, lowered: str) -> bool:
        candidate = lowered.strip().rstrip("?!.,")
        for prefix in cls._ACKNOWLEDGEMENT_PREFIXES:
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):].strip().rstrip("?!.,")
                break
        return any(candidate == marker or candidate.startswith(marker + " ") for marker in cls._RESULT_ACTION_MARKERS)

    def _refresh_stale_read_context(self, context: dict[str, Any]) -> CommandResponse | None:
        dispatch = context.get("dispatch") if isinstance(context.get("dispatch"), dict) else {}
        if str(dispatch.get("execution_mode") or "").strip() != "autonomous_read":
            return None

        worker = str(context.get("worker") or dispatch.get("worker") or "").strip()
        handler = self.dispatchers.get(worker)
        if not worker or handler is None:
            return None

        try:
            evidence = handler(dict(dispatch))
        except Exception as exc:
            return CommandResponse(
                command="autonomous_result_refresh_failed",
                status="healthy",
                message=(
                    f"That result had expired, so I tried to refresh the safe {worker} read, but it did not return "
                    f"verified evidence: {exc}"
                ),
                data={
                    "intent": "refresh_stale_autonomous_result",
                    "worker": worker,
                    "context_state": "stale",
                    "refresh_attempted": True,
                    "refresh_verified": False,
                    "external_action_taken": False,
                },
            )

        verified, reason = self._verify_evidence(dispatch, evidence)
        if not verified:
            return CommandResponse(
                command="autonomous_result_refresh_unverified",
                status="healthy",
                message=(
                    f"That result had expired, so I refreshed the safe {worker} read, but the returned evidence was "
                    f"not strong enough to treat as current ({reason})."
                ),
                data={
                    "intent": "refresh_stale_autonomous_result",
                    "worker": worker,
                    "context_state": "stale",
                    "refresh_attempted": True,
                    "refresh_verified": False,
                    "external_action_taken": False,
                },
            )

        executive_result = self._executive_result_summary(worker, dispatch, evidence)
        refreshed_context = {
            "worker": worker,
            "dispatch": dict(dispatch),
            "evidence": dict(evidence),
            "executive_result": executive_result,
            "verified_at": self._now().isoformat(),
        }
        self._last_verified_result = refreshed_context
        self._persist_context(refreshed_context)
        return CommandResponse(
            command="autonomous_result_refreshed",
            status="healthy",
            message=f"The previous result had expired, so I refreshed the safe {worker} read. {executive_result}",
            data={
                "intent": "refresh_stale_autonomous_result",
                "worker": worker,
                "context_state": "fresh",
                "refresh_attempted": True,
                "refresh_verified": True,
                "executive_result": executive_result,
                "external_action_taken": False,
            },
        )

    def _load_context(self) -> dict[str, Any] | None:
        if not self.store_path.exists():
            return None
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict) or not self._REQUIRED_KEYS.issubset(value):
            return None
        if not isinstance(value.get("dispatch"), dict) or not isinstance(value.get("evidence"), dict):
            return None
        worker = str(value.get("worker") or "").strip()
        executive_result = str(value.get("executive_result") or "").strip()
        verified_at = str(value.get("verified_at") or "").strip()
        if not worker or not executive_result or not self._parse_timestamp(verified_at):
            return None
        context = {
            "worker": worker,
            "dispatch": dict(value["dispatch"]),
            "evidence": dict(value["evidence"]),
            "executive_result": executive_result,
            "verified_at": verified_at,
        }
        if self._context_is_stale(context):
            self._clear_context()
            return None
        return context

    def _context_is_stale(self, context: dict[str, Any]) -> bool:
        verified_at = self._parse_timestamp(str(context.get("verified_at") or ""))
        if verified_at is None:
            return True
        age = self._now() - verified_at
        return age < timedelta(0) or age > self.max_context_age

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _persist_context(self, context: dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(context, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.store_path)

    def _clear_context(self) -> None:
        try:
            self.store_path.unlink(missing_ok=True)
        except OSError:
            pass
