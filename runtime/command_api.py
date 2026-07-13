from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from .blueprint_orchestrator import (
    BlueprintBlockedError,
    BlueprintOrchestrator,
    BlueprintRequest,
)
from .approvals import ApprovalConflict, ApprovalNotFound
from .composition import RuntimeComponents
from .definitions import load_workflow_definition
from .dispatch import JobNotFound
from .repositories import RunNotFound
from .revision_graph import RevisionIssue
from .serialization import workflow_to_dict
from .workspaces import (
    CrossWorkspaceReference,
    WorkspaceNotFound,
    WorkspaceRuntimeManager,
)


class CommandError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class RuntimeCommandAPI:
    """Structured application boundary for Tony, n8n and future interfaces."""

    def __init__(
        self,
        runtime: RuntimeComponents,
        blueprint_orchestrator: BlueprintOrchestrator | None = None,
    ) -> None:
        self.runtime = runtime
        self.blueprint_orchestrator = blueprint_orchestrator

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        command = str(request.get("command", "")).strip()
        if not command:
            raise CommandError("missing_command", "command is required")

        handlers = {
            "health": self._health,
            "runs.list": self._list_runs,
            "runs.get": self._get_run,
            "runs.create": self._create_run,
            "stages.dispatch": self._dispatch_stage,
            "jobs.get": self._get_job,
            "approvals.list": self._list_approvals,
            "approvals.get": self._get_approval,
            "approvals.approve": self._approve,
            "approvals.revise": self._revise,
            "approvals.comment": self._comment,
            "approvals.block": self._block,
            "blueprints.generate": self._blueprint_generate,
            "blueprints.get": self._blueprint_get,
            "blueprints.list": self._blueprint_list,
        }
        handler = handlers.get(command)
        if handler is None:
            raise CommandError("unknown_command", f"unsupported command: {command}", 404)
        return {"ok": True, "command": command, "data": handler(request)}

    def _health(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": "ok",
            "runs": len(self.runtime.run_repository.list_run_ids()),
            "paths": {
                "runtime_root": str(self.runtime.paths.root),
                "repository_root": str(self.runtime.paths.repository_root),
            },
        }

    def _list_runs(self, request: Mapping[str, Any]) -> dict[str, Any]:
        run_ids = self.runtime.run_repository.list_run_ids()
        return {"run_ids": run_ids, "count": len(run_ids)}

    def _get_run(self, request: Mapping[str, Any]) -> dict[str, Any]:
        run_id = self._required(request, "run_id")
        try:
            state = self.runtime.run_service.load_run(run_id)
        except RunNotFound as exc:
            raise CommandError("run_not_found", f"workflow run not found: {run_id}", 404) from exc
        return workflow_to_dict(state)

    def _create_run(self, request: Mapping[str, Any]) -> dict[str, Any]:
        run_id = self._required(request, "run_id")
        definition_path = self._repository_path(self._required(request, "definition_path"))
        inputs = request.get("available_inputs", [])
        if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
            raise CommandError("invalid_inputs", "available_inputs must be a list of strings")
        definition = load_workflow_definition(definition_path)
        try:
            state = self.runtime.run_service.create_run(definition, run_id, inputs)
        except ValueError as exc:
            raise CommandError("run_creation_failed", str(exc), 409) from exc
        return workflow_to_dict(state)

    def _dispatch_stage(self, request: Mapping[str, Any]) -> dict[str, Any]:
        run_id = self._required(request, "run_id")
        client_id = str(request.get("client_id", "")).strip()
        context = {"client_id": client_id} if client_id else None
        scoring_input = request.get("scoring_input")
        if scoring_input is not None and not isinstance(scoring_input, Mapping):
            raise CommandError(
                "invalid_scoring_input",
                "scoring_input must be an object",
            )
        if scoring_input is not None:
            context = {
                **dict(context or {}),
                "scoring_input": dict(scoring_input),
            }
        try:
            job = self.runtime.dispatch_service.enqueue_current_stage(
                run_id,
                context=context,
            )
        except RunNotFound as exc:
            raise CommandError("run_not_found", f"workflow run not found: {run_id}", 404) from exc
        except (ValueError, RuntimeError) as exc:
            raise CommandError("dispatch_failed", str(exc), 409) from exc
        return asdict(job)

    def _get_job(self, request: Mapping[str, Any]) -> dict[str, Any]:
        job_id = self._required(request, "job_id")
        try:
            job = self.runtime.dispatch_queue.get(job_id)
        except JobNotFound as exc:
            raise CommandError("job_not_found", f"dispatch job not found: {job_id}", 404) from exc
        payload = asdict(job)
        payload["status"] = job.status.value
        return payload

    def _list_approvals(self, request: Mapping[str, Any]) -> dict[str, Any]:
        records = [
            record.to_dict() for record in self.runtime.approval_service.queue()
        ]
        return {"approvals": records, "count": len(records)}

    def _get_approval(self, request: Mapping[str, Any]) -> dict[str, Any]:
        run_id = self._required(request, "run_id")
        try:
            current = self.runtime.approval_service.current(run_id)
            history = self.runtime.approval_service.history(run_id)
        except ApprovalNotFound as exc:
            raise CommandError(
                "approval_not_found",
                f"approval not found for workflow run: {run_id}",
                404,
            ) from exc
        return {
            "current": current.to_dict(),
            "history": [record.to_dict() for record in history],
        }

    def _approve(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._approval_decision(request, "approve")

    def _block(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self._approval_decision(request, "block")

    def _comment(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return self.runtime.approval_service.comment(
                self._required(request, "run_id"),
                self._required(request, "command_id"),
                self._required(request, "reviewer_id"),
                self._required(request, "comment"),
            ).to_dict()
        except (ApprovalConflict, ApprovalNotFound, ValueError) as exc:
            raise CommandError("approval_command_failed", str(exc), 409) from exc

    def _revise(self, request: Mapping[str, Any]) -> dict[str, Any]:
        raw_issue = request.get("revision")
        if not isinstance(raw_issue, Mapping):
            raise CommandError(
                "invalid_revision",
                "revision must be an object",
            )
        try:
            issue = RevisionIssue.from_dict(dict(raw_issue))
            if issue.run_id != self._required(request, "run_id"):
                raise ValueError("revision run_id must match command run_id")
            return self.runtime.approval_service.revise(
                issue,
                self._required(request, "command_id"),
                self._required(request, "reviewer_id"),
                self._required(request, "rationale"),
            ).to_dict()
        except (ApprovalConflict, ApprovalNotFound, KeyError, ValueError) as exc:
            raise CommandError("approval_command_failed", str(exc), 409) from exc

    def _approval_decision(
        self,
        request: Mapping[str, Any],
        decision: str,
    ) -> dict[str, Any]:
        try:
            handler = getattr(self.runtime.approval_service, decision)
            return handler(
                self._required(request, "run_id"),
                self._required(request, "command_id"),
                self._required(request, "reviewer_id"),
                self._required(request, "rationale"),
            ).to_dict()
        except (ApprovalConflict, ApprovalNotFound, ValueError) as exc:
            raise CommandError("approval_command_failed", str(exc), 409) from exc

    def _blueprint_generate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        orchestrator = self._blueprint_orchestrator()
        payload = self._blueprint_payload(request)
        try:
            result = orchestrator.generate(BlueprintRequest.from_dict(payload))
        except BlueprintBlockedError as exc:
            raise CommandError("blueprint_blocked", str(exc), 409) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise CommandError("invalid_blueprint_request", str(exc), 400) from exc
        return result.to_dict()

    def _blueprint_get(self, request: Mapping[str, Any]) -> dict[str, Any]:
        orchestrator = self._blueprint_orchestrator()
        workspace_id = self._required(request, "workspace_id")
        client_id = self._required(request, "client_id")
        blueprint_id = str(request.get("blueprint_id", "")).strip() or client_id
        version_value = request.get("version")
        version = int(version_value) if version_value is not None and str(version_value).strip() else None
        try:
            return orchestrator.get(workspace_id, client_id, blueprint_id, version).to_dict()
        except KeyError as exc:
            raise CommandError("blueprint_not_found", str(exc), 404) from exc

    def _blueprint_list(self, request: Mapping[str, Any]) -> dict[str, Any]:
        orchestrator = self._blueprint_orchestrator()
        workspace_id = self._required(request, "workspace_id")
        client_id = self._required(request, "client_id")
        blueprint_id = str(request.get("blueprint_id", "")).strip() or client_id
        versions = [record.to_dict() for record in orchestrator.list(workspace_id, client_id, blueprint_id)]
        return {"versions": versions, "count": len(versions)}

    def _repository_path(self, relative: str) -> Path:
        root = self.runtime.paths.repository_root.resolve()
        target = (root / relative).resolve()
        if target != root and root not in target.parents:
            raise CommandError("unsafe_path", "definition_path must remain inside repository_root")
        if not target.is_file():
            raise CommandError("definition_not_found", f"workflow definition not found: {relative}", 404)
        return target

    @staticmethod
    def _required(request: Mapping[str, Any], field: str) -> str:
        value = str(request.get(field, "")).strip()
        if not value:
            raise CommandError("missing_field", f"{field} is required")
        return value

    def _blueprint_orchestrator(self) -> BlueprintOrchestrator:
        if self.blueprint_orchestrator is None:
            raise CommandError(
                "blueprint_engine_unavailable",
                "blueprint orchestration is not configured",
                503,
            )
        return self.blueprint_orchestrator

    @staticmethod
    def _blueprint_payload(request: Mapping[str, Any]) -> dict[str, Any]:
        payload = request.get("request")
        if payload is None:
            payload = {key: value for key, value in request.items() if key != "command"}
        if not isinstance(payload, Mapping):
            raise CommandError("invalid_blueprint_request", "request must be an object")
        return dict(payload)


class WorkspaceCommandAPI:
    """Workspace router for Tony/n8n with legacy request compatibility."""

    def __init__(
        self,
        legacy_runtime: RuntimeComponents,
        manager: WorkspaceRuntimeManager,
        blueprint_orchestrator: BlueprintOrchestrator | None = None,
    ) -> None:
        self.legacy_api = RuntimeCommandAPI(
            legacy_runtime,
            blueprint_orchestrator=blueprint_orchestrator,
        )
        self.manager = manager
        self.blueprint_orchestrator = blueprint_orchestrator

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        command = str(request.get("command", "")).strip()
        if command == "workspaces.list":
            workspaces = [
                workspace.to_dict()
                for workspace in self.manager.repository.list()
            ]
            return {
                "ok": True,
                "command": command,
                "data": {"workspaces": workspaces, "count": len(workspaces)},
            }
        if command == "workspaces.create":
            try:
                workspace = self.manager.create(
                    self._required(request, "workspace_id"),
                    self._required(request, "client_id"),
                    self._required(request, "display_name"),
                )
            except ValueError as exc:
                raise CommandError("workspace_creation_failed", str(exc), 409) from exc
            return {"ok": True, "command": command, "data": workspace.to_dict()}
        if command == "workspaces.get":
            try:
                workspace = self.manager.repository.get(
                    self._required(request, "workspace_id")
                )
            except WorkspaceNotFound as exc:
                raise CommandError("workspace_not_found", str(exc), 404) from exc
            return {"ok": True, "command": command, "data": workspace.to_dict()}
        if command == "workspaces.migrate_legacy":
            try:
                workspace = self.manager.migrate_legacy(
                    workspace_id=self._required(request, "workspace_id"),
                    client_id=self._required(request, "client_id"),
                    display_name=self._required(request, "display_name"),
                )
            except ValueError as exc:
                raise CommandError("workspace_migration_failed", str(exc), 409) from exc
            return {"ok": True, "command": command, "data": workspace.to_dict()}

        workspace_id = str(request.get("workspace_id", "")).strip()
        if not workspace_id:
            return self.legacy_api.handle(request)
        try:
            workspace = self.manager.repository.get(workspace_id)
        except WorkspaceNotFound as exc:
            raise CommandError(
                "workspace_not_found",
                f"workspace not found: {workspace_id}",
                404,
            ) from exc

        supplied_client = str(request.get("client_id", "")).strip()
        if supplied_client and supplied_client != workspace.client_id:
            raise CommandError(
                "cross_workspace_reference",
                "client_id belongs to a different workspace",
                409,
            )
        scoped_request = dict(request)
        scoped_request["client_id"] = workspace.client_id
        self._reject_cross_workspace_run(scoped_request, workspace_id)
        result = RuntimeCommandAPI(
            self.manager.runtime(workspace_id),
            blueprint_orchestrator=self.blueprint_orchestrator,
        ).handle(scoped_request)
        result["workspace_id"] = workspace_id
        return result

    def _reject_cross_workspace_run(
        self,
        request: Mapping[str, Any],
        workspace_id: str,
    ) -> None:
        run_id = str(request.get("run_id", "")).strip()
        if not run_id:
            job_id = str(request.get("job_id", "")).strip()
            if "--" in job_id:
                run_id = job_id.split("--", 1)[0]
        if not run_id or str(request.get("command")) == "runs.create":
            return
        selected = self.manager.runtime(workspace_id)
        if selected.run_repository.exists(run_id):
            return
        owner = self.manager.locate_run(run_id)
        if owner and owner != workspace_id:
            raise CommandError(
                "cross_workspace_reference",
                str(
                    CrossWorkspaceReference(
                        f"run {run_id} belongs to workspace {owner}"
                    )
                ),
                409,
            )

    @staticmethod
    def _required(request: Mapping[str, Any], field: str) -> str:
        value = str(request.get(field, "")).strip()
        if not value:
            raise CommandError("missing_field", f"{field} is required")
        return value
