from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any, Callable, Mapping

from runtime.fieldwork_payments import (
    ApprovedFieldworkProposal,
    FieldworkPaymentError,
    FieldworkPaymentService,
    StripeSignatureError,
)


ProposalLoader = Callable[[str], ApprovedFieldworkProposal]


class FieldworkPaymentApplication:
    """Isolated WSGI boundary; Tony's conversational bridge remains unchanged."""

    def __init__(self, service: FieldworkPaymentService, *, bridge_token: str, proposal_loader: ProposalLoader) -> None:
        if not bridge_token.strip():
            raise ValueError("FIELDWORK payment bridge token is required")
        self.service = service
        self.bridge_token = bridge_token
        self.proposal_loader = proposal_loader

    def __call__(self, environ: Mapping[str, Any], start_response):
        method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        path = str(environ.get("PATH_INFO") or "/")
        if method == "GET" and path == "/health":
            return self._respond(start_response, HTTPStatus.OK, {"ok": True, "mode": "stripe_test"})
        if method == "POST" and path == "/fieldwork/stripe/webhook":
            return self._webhook(environ, start_response)
        denied = self._authorise(environ, start_response)
        if denied is not None:
            return denied
        if method == "POST" and path == "/fieldwork/checkout":
            return self._checkout(environ, start_response)
        if method == "POST" and path == "/fieldwork/reconcile":
            return self._reconcile(environ, start_response)
        return self._respond(start_response, HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def _checkout(self, environ: Mapping[str, Any], start_response):
        try:
            payload = self._read_json(environ)
            proposal_id = str(payload.get("proposal_id") or "").strip()
            if not proposal_id:
                raise FieldworkPaymentError("proposal_id is required")
            proposal = self.proposal_loader(proposal_id)
            result = self.service.create_checkout(proposal)
        except (FieldworkPaymentError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        return self._respond(start_response, HTTPStatus.OK, {"ok": True, **result})

    def _webhook(self, environ: Mapping[str, Any], start_response):
        try:
            raw = self._read_body(environ)
            signature = str(environ.get("HTTP_STRIPE_SIGNATURE") or "")
            result = self.service.handle_webhook(raw, signature)
        except StripeSignatureError as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except (FieldworkPaymentError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        return self._respond(start_response, HTTPStatus.OK, {"ok": True, **result})

    def _reconcile(self, environ: Mapping[str, Any], start_response):
        try:
            payload = self._read_json(environ)
            proposal_id = str(payload.get("proposal_id") or "").strip()
            if not proposal_id:
                raise FieldworkPaymentError("proposal_id is required")
            result = self.service.reconcile(proposal_id)
        except (FieldworkPaymentError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._respond(start_response, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        return self._respond(start_response, HTTPStatus.OK, {"ok": True, **result})

    def _authorise(self, environ: Mapping[str, Any], start_response):
        if str(environ.get("HTTP_AUTHORIZATION") or "") == f"Bearer {self.bridge_token}":
            return None
        return self._respond(start_response, HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorised"})

    @staticmethod
    def _read_body(environ: Mapping[str, Any]) -> bytes:
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except (TypeError, ValueError) as exc:
            raise FieldworkPaymentError("invalid content length") from exc
        if length < 0 or length > 1_000_000:
            raise FieldworkPaymentError("request body is too large")
        stream = environ.get("wsgi.input")
        if stream is None:
            raise FieldworkPaymentError("request body is unavailable")
        return stream.read(length)

    @classmethod
    def _read_json(cls, environ: Mapping[str, Any]) -> dict[str, Any]:
        value = json.loads(cls._read_body(environ).decode("utf-8") or "{}")
        if not isinstance(value, dict):
            raise FieldworkPaymentError("request must be a JSON object")
        return value

    @staticmethod
    def _respond(start_response, status: HTTPStatus, payload: Mapping[str, Any]):
        body = json.dumps(dict(payload), sort_keys=True).encode("utf-8")
        start_response(f"{status.value} {status.phrase}", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
        return [body]
