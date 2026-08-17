from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.tony_autonomous_dispatch import TonyAutonomousDispatchCommandService
from runtime.tony_command_service import CommandResponse


class TonyDeliveryCommissioningCommandService:
    """Commission a bounded internal delivery kickoff after a verified Drive workspace exists."""

    def __init__(self, command_service, dispatchers: Mapping[str, Any] | None = None, *, store_path: Path) -> None:
        self.command_service = command_service
        self.dispatchers = dict(dispatchers or {})
        self.store_path = store_path
        self.state = self._load()

    @property
    def mission_control_loader(self):
        return self.command_service.mission_control_loader

    @property
    def github_configured(self) -> bool:
        return bool(getattr(self.command_service, "github_configured", False))

    def execute(self, command: str, objects: Iterable[dict[str, Any]]) -> CommandResponse:
        response = self.command_service.execute(command, objects)
        return self._capture_and_commission(response)

    def _capture_and_commission(self, response: CommandResponse) -> CommandResponse:
        data = dict(response.data) if isinstance(response.data, dict) else {}
        if data.get("execution_status") != "drive_workspace_verified":
            return response
        workspace = data.get("drive_workspace") if isinstance(data.get("drive_workspace"), dict) else {}
        project_id = str(workspace.get("delivery_project_record_id") or "").strip()
        folder_id = str(workspace.get("drive_folder_id") or "").strip()
        folder_url = str(workspace.get("drive_folder_url") or "").strip()
        if not project_id or not folder_id or not folder_url:
            return response

        completed = set(str(item) for item in self.state.get("completed", []) if item)
        if project_id in completed:
            return response

        context = {
            "delivery_project_record_id": project_id,
            "drive_folder_id": folder_id,
            "drive_folder_url": folder_url,
            "onboarding_record_id": str(workspace.get("onboarding_record_id") or ""),
            "lead_id": str(workspace.get("lead_id") or ""),
            "contact": str(workspace.get("contact") or ""),
            "company": str(workspace.get("company") or ""),
        }
        return self._commission(context, prefix=response.message + " ")

    def _commission(self, context: dict[str, Any], *, prefix: str = "") -> CommandResponse:
        claude = self.dispatchers.get("Claude")
        label = str(context.get("company") or context.get("contact") or "the client")
        if claude is None:
            self.state["pending"] = dict(context)
            self._persist()
            return CommandResponse(
                "delivery_commissioning",
                "healthy",
                prefix + f"{label}'s verified delivery workspace is ready for bounded delivery commissioning, but no live Claude dispatcher is configured. I have not commissioned any work.",
                {
                    "execution_status": "delivery_commission_dispatcher_unavailable",
                    "delivery_commissioning": {**context, "state": "ready", "commissioned": False},
                    "external_action_taken": False,
                },
            )

        dispatch = {
            "worker": "Claude",
            "state": "ready_for_autonomous_dispatch",
            "eligible": True,
            "execution_mode": "autonomous_prepare",
            "execution_truth": "not_dispatched",
            "target": {
                **context,
                "area": "delivery",
                "workspace_access": "reference_only",
            },
            "instruction": (
                "Prepare the internal delivery kickoff package for this newly onboarded Narratiive client. "
                "Use only the verified context supplied here. Produce: (1) a concise delivery objective, "
                "(2) known facts, (3) explicit evidence gaps and questions that must be resolved before strategic claims are made, "
                "(4) a bounded research plan for the Growth Blueprint, (5) an initial workplan mapped to Strategy, Research, Creative, Client Deliverables and Reporting, "
                "and (6) Tony's proposed review gate before any client-facing deliverable is created. "
                "Do not invent client objectives, audiences, commercial terms, research findings or campaign facts. "
                "Do not write to Google Drive, Notion or any other external system and do not send client communications."
            ),
            "expected_evidence": "verified internal delivery kickoff work product with explicit evidence gaps and no external mutation",
            "return_to": "Tony",
        }
        try:
            evidence = claude(dict(dispatch))
        except Exception as exc:
            self.state["pending"] = dict(context)
            self._persist()
            return CommandResponse(
                "delivery_commissioning",
                "healthy",
                prefix + f"I attempted the safe Claude delivery commissioning for {label}, but it did not return verified evidence: {exc}. No delivery work has been treated as commissioned.",
                {
                    "execution_status": "delivery_commission_dispatch_failed",
                    "delivery_commissioning": {**context, "state": "dispatch_attempted_unverified", "commissioned": False},
                    "external_action_taken": False,
                },
            )

        verified, reason = TonyAutonomousDispatchCommandService._verify_evidence(dispatch, evidence)
        if not verified:
            self.state["pending"] = dict(context)
            self._persist()
            return CommandResponse(
                "delivery_commissioning",
                "healthy",
                prefix + f"Claude returned delivery commissioning material, but the evidence was insufficient ({reason}). I am not treating the work as commissioned.",
                {
                    "execution_status": "delivery_commission_dispatch_unverified",
                    "delivery_commissioning": {**context, "state": "dispatch_attempted_unverified", "commissioned": False},
                    "claude_evidence": dict(evidence) if isinstance(evidence, dict) else {},
                    "external_action_taken": False,
                },
            )

        gaps = evidence.get("evidence_gaps") if isinstance(evidence, dict) else None
        if gaps is None:
            self.state["pending"] = dict(context)
            self._persist()
            return CommandResponse(
                "delivery_commissioning",
                "healthy",
                prefix + "Claude returned a work product without explicit evidence gaps. Tony will not progress delivery until uncertainty is surfaced explicitly.",
                {
                    "execution_status": "delivery_commission_quality_gate_failed",
                    "delivery_commissioning": {**context, "state": "revision_required", "commissioned": False},
                    "claude_evidence": dict(evidence),
                    "external_action_taken": False,
                },
            )

        completed = [str(item) for item in self.state.get("completed", []) if item]
        project_id = str(context.get("delivery_project_record_id") or "")
        if project_id and project_id not in completed:
            completed.append(project_id)
        commissioned = {
            **context,
            "state": "commissioned_verified",
            "commissioned": True,
            "work_product": dict(evidence),
        }
        self.state = {"pending": None, "completed": completed[-100:], "commissioned": commissioned}
        self._persist()
        return CommandResponse(
            "delivery_commissioning",
            "healthy",
            prefix + f"Claude has returned a verified internal delivery kickoff package for {label}. Tony has not written it to Drive or sent anything to the client. The next step is to review the evidence gaps and workplan before creating client-facing delivery outputs.",
            {
                "execution_status": "delivery_commission_verified",
                "delivery_commissioning": dict(commissioned),
                "claude_evidence": dict(evidence),
                "external_action_taken": False,
            },
        )

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"pending": None, "completed": []}
        return value if isinstance(value, dict) else {"pending": None, "completed": []}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        temp.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.store_path)
