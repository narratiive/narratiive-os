from __future__ import annotations

from typing import Any, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService


SAFE_READ_WORKERS = {
    "gmail": "Gmail",
    "calendar": "Google Calendar",
    "notion": "Notion",
    "drive": "Google Drive",
    "github": "GitHub",
    "n8n": "n8n",
    "replit": "Replit",
}


class StructuredSafeReadError(ValueError):
    pass


class TonyStructuredSafeReadExecutor:
    """Execute one already-bounded read-only action through Narratiive dispatchers.

    OpenClaw remains responsible for understanding natural language. This boundary does
    not classify user wording and does not grant approval. It accepts only structured
    read actions, dispatches them to an explicitly configured worker, and reuses Tony's
    existing autonomous evidence verifier before reporting a verified read.

    Internal preparation stays with OpenClaw specialist agents; consequential writes go
    through the separate native-approval executor.
    """

    def __init__(self, dispatchers: Mapping[str, callable] | None = None) -> None:
        self.dispatchers = dict(dispatchers or {})

    def execute(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action") or "").strip()
        surface = str(payload.get("surface") or "").strip().casefold()
        kind = str(payload.get("kind") or "").strip().casefold()
        target = payload.get("target") if isinstance(payload.get("target"), dict) else {}

        if not action:
            raise StructuredSafeReadError("action is required")
        if kind != "read":
            raise StructuredSafeReadError("safe execution accepts read-only actions only")
        worker = SAFE_READ_WORKERS.get(surface)
        if worker is None:
            raise StructuredSafeReadError(f"unsupported safe-read surface: {surface or 'missing'}")
        dispatcher = self.dispatchers.get(worker)
        if dispatcher is None:
            return {
                "ok": False,
                "status": "dispatcher_unavailable",
                "surface": surface,
                "worker": worker,
                "execution_truth": "not_dispatched",
            }

        contract = {
            "worker": worker,
            "surface": surface,
            "action": action,
            "instruction": action,
            "target": dict(target),
            "execution_mode": "autonomous_read",
            "eligible": True,
            "state": "ready_for_autonomous_dispatch",
            "execution_truth": "not_dispatched",
            "source": "openclaw_native_tool",
        }
        try:
            evidence = dispatcher(contract)
        except Exception as exc:
            return {
                "ok": False,
                "status": "dispatch_failed",
                "surface": surface,
                "worker": worker,
                "error": str(exc),
                "execution_truth": "dispatch_attempted_unverified",
            }

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(contract, evidence)
        if not verified:
            return {
                "ok": False,
                "status": "unverified_safe_read",
                "surface": surface,
                "worker": worker,
                "reason": reason,
                "evidence": dict(evidence) if isinstance(evidence, dict) else {},
                "execution_truth": "dispatch_attempted_unverified",
            }
        return {
            "ok": True,
            "status": "safe_read_verified",
            "surface": surface,
            "worker": worker,
            "evidence": dict(evidence),
            "execution_truth": "verified_read",
        }
