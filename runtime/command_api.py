from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from .composition import RuntimeComponents
from .definitions import load_workflow_definition
from .dispatch import JobNotFound
from .repositories import RunNotFound
from .serialization import workflow_to_dict


class CommandError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class RuntimeCommandAPI:
    """Structured application boundary for Tony, n8n and future interfaces."""

    def __init__(self, runtime: RuntimeComponents) -> None:
        self.runtime = runtime

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
