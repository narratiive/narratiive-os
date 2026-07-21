from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


class TonyGatewayError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class TonyCommand:
    action: str
    workspace_id: str
    client_id: str
    command_id: str
    reviewer_id: str = ""
    rationale: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("action", "workspace_id", "client_id", "command_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True, slots=True)
class TonyResponse:
    ok: bool
    message: str
    data: Mapping[str, Any]
    correlation_id: str
    command: str


@runtime_checkable
class GatewayTransport(Protocol):
    def send(
        self,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> Mapping[str, Any]: ...


class HttpGatewayTransport:
    """Calls the authenticated Narratiive OS command gateway.

    The bearer token is read by the caller and used only in the Authorization header.
    It is never included in payloads, responses, exceptions or persisted state.
    """

    def __init__(self, endpoint: str, bearer_token: str, timeout_seconds: float = 30.0) -> None:
        if not endpoint.startswith("https://") and not endpoint.startswith("http://127.0.0.1") and not endpoint.startswith("http://localhost"):
            raise ValueError("gateway endpoint must use HTTPS except on loopback")
        if not bearer_token:
            raise ValueError("bearer_token is required")
        self.endpoint = endpoint
        self._bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds

    def send(
        self,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> Mapping[str, Any]:
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(dict(payload), sort_keys=True).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._bearer_token}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
                "X-Correlation-ID": correlation_id,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            retryable = exc.code >= 500 or exc.code == 429
            raise TonyGatewayError(
                "gateway_http_error",
                f"Narratiive OS rejected the command with HTTP {exc.code}",
                retryable=retryable,
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TonyGatewayError(
                "gateway_unavailable",
                "Narratiive OS is temporarily unavailable",
                retryable=True,
            ) from exc
        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise TonyGatewayError(
                "invalid_gateway_response",
                "Narratiive OS returned an invalid response",
            ) from exc
        if not isinstance(result, Mapping):
            raise TonyGatewayError("invalid_gateway_response", "Narratiive OS returned an invalid response")
        return result


class FakeGatewayTransport:
    def __init__(self, responses: list[Mapping[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def send(
        self,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "payload": dict(payload),
                "idempotency_key": idempotency_key,
                "correlation_id": correlation_id,
            }
        )
        if self.responses:
            return self.responses.pop(0)
        return {"ok": True, "command": payload.get("command", ""), "data": dict(payload)}


class TonyOrchestrationAdapter:
    """Maps manager-facing Tony actions onto the public command gateway only."""

    ACTIONS = {
        "health": "health",
        "workspace.create": "workspaces.create",
        "workspace.get": "workspaces.get",
        "workspace.list": "workspaces.list",
        "run.create": "runs.create",
        "run.status": "runs.get",
        "run.list": "runs.list",
        "dispatch": "stages.dispatch",
        "job.get": "jobs.get",
        "approval.list": "approvals.list",
        "approval.get": "approvals.get",
        "approve": "approvals.approve",
        "revise": "approvals.revise",
        "comment": "approvals.comment",
        "block": "approvals.block",
        "blueprint.generate": "blueprints.generate",
        "blueprint.get": "blueprints.get",
        "blueprint.list": "blueprints.list",
        "blueprint.export": "blueprints.export",
        "export.get": "blueprint-exports.get",
        "export.list": "blueprint-exports.list",
    }

    def __init__(self, transport: GatewayTransport) -> None:
        self.transport = transport

    def execute(self, command: TonyCommand) -> TonyResponse:
        gateway_command = self.ACTIONS.get(command.action)
        if gateway_command is None:
            raise TonyGatewayError("unsupported_action", f"Tony action is not supported: {command.action}")
        payload = dict(command.payload)
        self._reject_identity_mismatch(payload, command.workspace_id, command.client_id)
        payload.update(
            {
                "command": gateway_command,
                "workspace_id": command.workspace_id,
                "client_id": command.client_id,
                "command_id": command.command_id,
            }
        )
        if command.reviewer_id:
            payload["reviewer_id"] = command.reviewer_id
        if command.rationale:
            payload["rationale"] = command.rationale
        correlation_id = f"tony-{command.command_id}"
        result = self.transport.send(
            payload,
            idempotency_key=command.command_id,
            correlation_id=correlation_id,
        )
        if not bool(result.get("ok", False)):
            error = result.get("error", {})
            if not isinstance(error, Mapping):
                error = {}
            raise TonyGatewayError(
                str(error.get("code", "command_failed")),
                str(error.get("message", "Narratiive OS could not complete the command")),
                retryable=bool(error.get("retryable", False)),
            )
        data = result.get("data", {})
        if not isinstance(data, Mapping):
            data = {"value": data}
        return TonyResponse(
            ok=True,
            message=self._manager_message(command.action, data),
            data=dict(data),
            correlation_id=str(result.get("correlation_id", correlation_id)),
            command=gateway_command,
        )

    def create_growth_blueprint(
        self,
        *,
        workspace_id: str,
        client_id: str,
        command_id: str,
        run_id: str,
        definition_path: str,
        available_inputs: list[str],
    ) -> tuple[TonyResponse, TonyResponse]:
        """Starts the approved workflow sequence without bypassing its gates."""
        created = self.execute(
            TonyCommand(
                action="run.create",
                workspace_id=workspace_id,
                client_id=client_id,
                command_id=f"{command_id}-create",
                payload={
                    "run_id": run_id,
                    "definition_path": definition_path,
                    "available_inputs": list(available_inputs),
                },
            )
        )
        dispatched = self.execute(
            TonyCommand(
                action="dispatch",
                workspace_id=workspace_id,
                client_id=client_id,
                command_id=f"{command_id}-dispatch",
                payload={"run_id": run_id},
            )
        )
        return created, dispatched

    @staticmethod
    def _reject_identity_mismatch(payload: Mapping[str, Any], workspace_id: str, client_id: str) -> None:
        nested_workspace = str(payload.get("workspace_id", "")).strip()
        nested_client = str(payload.get("client_id", "")).strip()
        if nested_workspace and nested_workspace != workspace_id:
            raise TonyGatewayError("cross_workspace_reference", "payload workspace_id does not match Tony context")
        if nested_client and nested_client != client_id:
            raise TonyGatewayError("cross_workspace_reference", "payload client_id does not match Tony context")
        nested = payload.get("request")
        if isinstance(nested, Mapping):
            TonyOrchestrationAdapter._reject_identity_mismatch(nested, workspace_id, client_id)

    @staticmethod
    def _manager_message(action: str, data: Mapping[str, Any]) -> str:
        if action == "health":
            return f"Narratiive OS health: {data.get('status', 'unknown')}."
        if action == "run.status":
            status = data.get("status") or data.get("workflow_status") or "available"
            return f"Workflow status: {status}."
        if action == "job.get":
            return f"Job status: {data.get('status', 'available')}."
        if action == "approval.list":
            return f"Approval queue: {data.get('count', 0)} item(s)."
        if action == "approval.get":
            current = data.get("current", {})
            status = current.get("status", "available") if isinstance(current, Mapping) else "available"
            return f"Approval status: {status}."
        if action == "blueprint.export":
            status = data.get("status", "submitted")
            url = data.get("presentation_url", "")
            return f"Blueprint export {status}." + (f" {url}" if url else "")
        if action in {"approve", "revise", "comment", "block"}:
            return f"Approval action '{action}' recorded."
        return f"Narratiive OS completed '{action}'."
