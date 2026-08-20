from __future__ import annotations

from typing import Any, Mapping


SURFACE_WORKERS = {
    "gmail": "Gmail",
    "calendar": "Google Calendar",
    "notion": "Notion",
    "drive": "Google Drive",
    "github": "GitHub",
    "n8n": "n8n",
    "replit": "Replit",
}

_EVIDENCE_KEYS = {
    "gmail": ("message_id", "thread_id"),
    "calendar": ("event_id", "calendar_event_id"),
    "notion": ("record_id", "page_id"),
    "drive": ("file_id", "url"),
    "github": ("commit_sha", "pr_url", "issue_url", "url"),
    "n8n": ("execution_id", "run_id"),
    "replit": ("deployment_id", "url"),
}


class StructuredActionExecutionError(ValueError):
    pass


class TonyStructuredActionExecutor:
    """Execute one already-approved structured action through Narratiive dispatchers.

    This class does not interpret human language and does not grant approval. It is a
    deterministic consequence boundary for OpenClaw after native single-use approval.
    """

    def __init__(self, dispatchers: Mapping[str, callable] | None = None) -> None:
        self.dispatchers = dict(dispatchers or {})

    def execute(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action") or "").strip()
        surface = str(payload.get("surface") or "").strip().casefold()
        kind = str(payload.get("kind") or "").strip().casefold()
        target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
        approval = str(payload.get("approval") or "").strip().casefold()

        if not action:
            raise StructuredActionExecutionError("action is required")
        if kind != "write":
            raise StructuredActionExecutionError("structured execution accepts consequential write actions only")
        if approval != "openclaw_allow_once":
            raise StructuredActionExecutionError("single-use OpenClaw approval evidence is required")
        worker = SURFACE_WORKERS.get(surface)
        if worker is None:
            raise StructuredActionExecutionError(f"unsupported execution surface: {surface or 'missing'}")
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
            "execution_mode": "approved_write",
            "approval": "openclaw_allow_once",
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
                "execution_truth": "not_verified",
            }
        if not isinstance(evidence, dict):
            return {
                "ok": False,
                "status": "invalid_evidence",
                "surface": surface,
                "worker": worker,
                "execution_truth": "not_verified",
            }
        verified, reason = self._verify_evidence(surface, evidence)
        if not verified:
            return {
                "ok": False,
                "status": "unverified_execution",
                "surface": surface,
                "worker": worker,
                "reason": reason,
                "evidence": dict(evidence),
                "execution_truth": "not_verified",
            }
        return {
            "ok": True,
            "status": "executed_verified",
            "surface": surface,
            "worker": worker,
            "evidence": dict(evidence),
            "execution_truth": "verified_executed",
        }

    @staticmethod
    def _verify_evidence(surface: str, evidence: Mapping[str, Any]) -> tuple[bool, str]:
        for key in ("ok", "success", "verified", "executed", "sent", "created", "updated"):
            if key in evidence and evidence.get(key) is False:
                return False, f"worker explicitly reported {key}=false"
        keys = _EVIDENCE_KEYS.get(surface, ())
        if not any(str(evidence.get(key) or "").strip() for key in keys):
            return False, f"missing decision-grade {surface} execution identifier"
        return True, "decision-grade execution evidence returned"
