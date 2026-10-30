from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib import parse, request
from urllib.error import HTTPError, URLError


class FieldworkPaymentError(RuntimeError):
    """A payment boundary failed closed."""


class StripeSignatureError(FieldworkPaymentError):
    """A Stripe webhook signature is missing, stale or invalid."""


class StripeCheckoutGateway(Protocol):
    def create_checkout(self, payload: Mapping[str, str], *, idempotency_key: str) -> Mapping[str, Any]: ...
    def retrieve_checkout(self, session_id: str) -> Mapping[str, Any]: ...


Action = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _synchronised(method):
    def wrapped(self, *args, **kwargs):
        with self._service_lock:
            return method(self, *args, **kwargs)
    return wrapped


@dataclass(frozen=True, slots=True)
class ApprovedFieldworkProposal:
    proposal_id: str
    workspace_id: str
    client_id: str
    client_name: str
    client_contact_name: str
    client_email: str
    proposal_url: str
    proposal_checksum: str
    scope_summary: str
    total_amount_minor: int
    deposit_amount_minor: int
    currency: str
    balance_terms: str
    service_terms_url: str
    founder_approval_id: str
    founder_approved_at: str
    parent_workflow_run_id: str
    commercial_record_id: str
    required_inputs: tuple[str, ...] = ()
    received_inputs: tuple[str, ...] = ()
    workflow_inputs: Mapping[str, Any] = field(default_factory=dict)
    target_workflow_id: str = "growth_sprint_to_research_engine"
    delivery_commitment_days: int = 7

    def __post_init__(self) -> None:
        required = {
            "proposal_id": self.proposal_id,
            "workspace_id": self.workspace_id,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "client_contact_name": self.client_contact_name,
            "client_email": self.client_email,
            "proposal_url": self.proposal_url,
            "proposal_checksum": self.proposal_checksum,
            "scope_summary": self.scope_summary,
            "balance_terms": self.balance_terms,
            "service_terms_url": self.service_terms_url,
            "founder_approval_id": self.founder_approval_id,
            "founder_approved_at": self.founder_approved_at,
            "parent_workflow_run_id": self.parent_workflow_run_id,
            "commercial_record_id": self.commercial_record_id,
            "target_workflow_id": self.target_workflow_id,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"approved proposal is missing: {', '.join(missing)}")
        if self.total_amount_minor <= 0 or self.deposit_amount_minor <= 0:
            raise ValueError("proposal amounts must be positive")
        if self.deposit_amount_minor > self.total_amount_minor:
            raise ValueError("deposit cannot exceed total investment")
        if len(self.currency.strip()) != 3:
            raise ValueError("currency must be a three-letter code")
        if self.delivery_commitment_days <= 0:
            raise ValueError("delivery commitment must be positive")
        if not self.client_email.strip() or "@" not in self.client_email:
            raise ValueError("client email is invalid")
        if not self.proposal_url.lower().startswith("https://") or not self.service_terms_url.lower().startswith("https://"):
            raise ValueError("proposal and service terms URLs must use HTTPS")
        try:
            approved_at = datetime.fromisoformat(self.founder_approved_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("founder approval timestamp is invalid") from exc
        if approved_at.tzinfo is None:
            raise ValueError("founder approval timestamp must be timezone-aware")

    @property
    def prerequisites_complete(self) -> bool:
        return set(self.required_inputs).issubset(self.received_inputs)

    @property
    def outstanding_inputs(self) -> tuple[str, ...]:
        received = set(self.received_inputs)
        return tuple(item for item in self.required_inputs if item not in received)


class StripeApiClient:
    """Minimal Stripe Checkout client; credentials remain runtime-only."""

    def __init__(
        self,
        secret_key: str,
        *,
        api_base: str = "https://api.stripe.com/v1",
        api_version: str = "2026-09-30.endive",
        timeout_seconds: float = 15.0,
        opener: Callable[..., Any] = request.urlopen,
    ) -> None:
        if not secret_key.startswith("sk_test_"):
            raise FieldworkPaymentError("FIELDWORK requires a Stripe test secret key until production activation")
        self.secret_key = secret_key
        self.api_base = api_base.rstrip("/")
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds
        self.opener = opener

    def create_checkout(self, payload: Mapping[str, str], *, idempotency_key: str) -> Mapping[str, Any]:
        return self._call("/checkout/sessions", payload, idempotency_key=idempotency_key)

    def retrieve_checkout(self, session_id: str) -> Mapping[str, Any]:
        safe_id = parse.quote(session_id, safe="")
        return self._call(f"/checkout/sessions/{safe_id}", None)

    def _call(
        self,
        path: str,
        payload: Mapping[str, str] | None,
        *,
        idempotency_key: str = "",
    ) -> Mapping[str, Any]:
        data = parse.urlencode(dict(payload)).encode("utf-8") if payload is not None else None
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Accept": "application/json",
            "Stripe-Version": self.api_version,
        }
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        req = request.Request(self.api_base + path, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with self.opener(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise FieldworkPaymentError(f"Stripe returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise FieldworkPaymentError(f"Stripe request failed: {exc}") from exc
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FieldworkPaymentError("Stripe returned invalid JSON") from exc
        if not isinstance(value, dict) or not str(value.get("id") or "").strip():
            raise FieldworkPaymentError("Stripe response lacks a verified object identifier")
        return value


class FieldworkPaymentStore:
    """Atomic current state plus hash-chained, append-only payment evidence."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.state_path = root / "fieldwork-payments.json"
        self.events_path = root / "fieldwork-payment-events.jsonl"
        self._lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        with self._lock:
            try:
                value = json.loads(self.state_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return {"proposals": {}, "processed_events": {}, "payments": {}}
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FieldworkPaymentError("payment state is unreadable") from exc
            if not isinstance(value, dict):
                raise FieldworkPaymentError("payment state is invalid")
            value.setdefault("proposals", {})
            value.setdefault("processed_events", {})
            value.setdefault("payments", {})
            return value

    def save(self, state: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            previous = self._last_checksum()
            record = {**dict(event), "recorded_at": _now(), "previous_checksum": previous}
            checksum_input = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
            record["checksum"] = hashlib.sha256(checksum_input).hexdigest()
            with self.events_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(self.events_path, 0o600)
            tmp = self.state_path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as stream:
                json.dump(dict(state), stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            tmp.replace(self.state_path)
            os.chmod(self.state_path, 0o600)
            return record

    def _last_checksum(self) -> str:
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return ""
        if not lines:
            return ""
        try:
            value = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise FieldworkPaymentError("payment event journal is corrupt") from exc
        return str(value.get("checksum") or "")


class FieldworkPaymentService:
    SUCCESS_EVENTS = {"checkout.session.completed", "checkout.session.async_payment_succeeded"}
    FAILURE_EVENTS = {"checkout.session.async_payment_failed", "payment_intent.payment_failed"}
    ABANDONED_EVENTS = {"checkout.session.expired"}

    def __init__(
        self,
        store: FieldworkPaymentStore,
        stripe: StripeCheckoutGateway,
        *,
        webhook_secret: str,
        success_url: str,
        cancel_url: str,
        crm_update: Action | None = None,
        founder_notification: Action | None = None,
        workflow_authorisation: Action | None = None,
        client_confirmation: Action | None = None,
        clock: Callable[[], float] = time.time,
        signature_tolerance_seconds: int = 300,
    ) -> None:
        if not webhook_secret.startswith("whsec_"):
            raise FieldworkPaymentError("a Stripe test webhook signing secret is required")
        if not success_url.lower().startswith("https://") or not cancel_url.lower().startswith("https://"):
            raise FieldworkPaymentError("Stripe Checkout return URLs must use HTTPS")
        self.store = store
        self.stripe = stripe
        self.webhook_secret = webhook_secret
        self.success_url = success_url
        self.cancel_url = cancel_url
        self.crm_update = crm_update
        self.founder_notification = founder_notification
        self.workflow_authorisation = workflow_authorisation
        self.client_confirmation = client_confirmation
        self.clock = clock
        self.signature_tolerance_seconds = signature_tolerance_seconds
        self._service_lock = threading.RLock()

    @_synchronised
    def create_checkout(self, proposal: ApprovedFieldworkProposal) -> dict[str, Any]:
        state = self.store.load()
        existing = state["proposals"].get(proposal.proposal_id)
        proposal_record = self._proposal_record(proposal)
        if existing:
            immutable_existing = {key: existing.get(key) for key in proposal_record}
            if immutable_existing != proposal_record:
                raise FieldworkPaymentError("proposal identity or commercial terms changed after registration")
            checkout = existing.get("checkout") if isinstance(existing.get("checkout"), dict) else {}
            if checkout.get("session_id") and checkout.get("url"):
                return {"proposal": proposal_record, "checkout": dict(checkout), "replay": True, "email": self._proposal_email(proposal, str(checkout["url"]))}

        payload = self._checkout_payload(proposal)
        stripe_session = self.stripe.create_checkout(
            payload,
            idempotency_key=f"fieldwork-checkout:{proposal.workspace_id}:{proposal.proposal_id}:{proposal.proposal_checksum}",
        )
        session_id = str(stripe_session.get("id") or "").strip()
        checkout_url = str(stripe_session.get("url") or "").strip()
        if not session_id or not checkout_url:
            raise FieldworkPaymentError("Stripe did not return a Checkout session and URL")
        checkout = {
            "session_id": session_id,
            "url": checkout_url,
            "status": str(stripe_session.get("status") or "open"),
            "payment_status": str(stripe_session.get("payment_status") or "unpaid"),
            "created_at": _now(),
            "mode": "test",
        }
        state["proposals"][proposal.proposal_id] = {**proposal_record, "checkout": checkout}
        self.store.save(state, {"kind": "checkout_created", "proposal_id": proposal.proposal_id, "session_id": session_id, "mode": "test"})
        return {"proposal": proposal_record, "checkout": checkout, "replay": False, "email": self._proposal_email(proposal, checkout_url)}

    @_synchronised
    def handle_webhook(self, raw_body: bytes, signature_header: str) -> dict[str, Any]:
        self.verify_signature(raw_body, signature_header)
        try:
            event = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FieldworkPaymentError("Stripe webhook body is invalid JSON") from exc
        if not isinstance(event, dict):
            raise FieldworkPaymentError("Stripe webhook event is invalid")
        event_id = str(event.get("id") or "").strip()
        event_type = str(event.get("type") or "").strip()
        livemode = event.get("livemode")
        if not event_id or not event_type:
            raise FieldworkPaymentError("Stripe webhook lacks event identity")
        if livemode is not False:
            raise FieldworkPaymentError("live-mode Stripe events are disabled")
        state = self.store.load()
        if event_id in state["processed_events"]:
            return {**dict(state["processed_events"][event_id]), "replay": True}
        obj = ((event.get("data") or {}).get("object") if isinstance(event.get("data"), dict) else None)
        if not isinstance(obj, dict):
            raise FieldworkPaymentError("Stripe webhook lacks an event object")
        if event_type in self.SUCCESS_EVENTS:
            result = self._accept_paid_checkout(state, event_id, event_type, obj, raw_body)
        elif event_type in self.FAILURE_EVENTS:
            result = self._record_non_success(state, event_id, event_type, obj, "failed")
        elif event_type in self.ABANDONED_EVENTS:
            result = self._record_non_success(state, event_id, event_type, obj, "abandoned")
        else:
            result = {"event_id": event_id, "event_type": event_type, "status": "ignored", "work_authorised": False}
            state["processed_events"][event_id] = dict(result)
            self.store.save(state, {"kind": "webhook_ignored", **result})
        return result

    @_synchronised
    def reconcile(self, proposal_id: str) -> dict[str, Any]:
        state = self.store.load()
        proposal = state["proposals"].get(proposal_id)
        if not isinstance(proposal, dict):
            raise FieldworkPaymentError("proposal is not registered")
        checkout = proposal.get("checkout") if isinstance(proposal.get("checkout"), dict) else {}
        session_id = str(checkout.get("session_id") or "")
        if not session_id:
            raise FieldworkPaymentError("proposal has no Checkout session")
        remote = dict(self.stripe.retrieve_checkout(session_id))
        if str(remote.get("payment_status") or "") != "paid":
            checkout.update({"status": str(remote.get("status") or "unknown"), "payment_status": str(remote.get("payment_status") or "unknown"), "reconciled_at": _now()})
            proposal["checkout"] = checkout
            self.store.save(state, {"kind": "checkout_reconciled", "proposal_id": proposal_id, "session_id": session_id, "payment_status": checkout["payment_status"]})
            return {"proposal_id": proposal_id, "status": checkout["payment_status"], "work_authorised": False}
        synthetic_id = f"reconcile:{session_id}:{str(remote.get('payment_intent') or '')}"
        if synthetic_id in state["processed_events"]:
            return {**dict(state["processed_events"][synthetic_id]), "replay": True}
        raw = json.dumps(remote, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return self._accept_paid_checkout(state, synthetic_id, "checkout.session.reconciled", remote, raw)

    def verify_signature(self, raw_body: bytes, signature_header: str) -> None:
        parts: dict[str, list[str]] = {}
        for component in signature_header.split(","):
            key, separator, value = component.strip().partition("=")
            if separator:
                parts.setdefault(key, []).append(value)
        try:
            timestamp = int(parts.get("t", [""])[0])
        except ValueError as exc:
            raise StripeSignatureError("Stripe signature timestamp is invalid") from exc
        if abs(int(self.clock()) - timestamp) > self.signature_tolerance_seconds:
            raise StripeSignatureError("Stripe signature timestamp is outside the allowed tolerance")
        signed = str(timestamp).encode("ascii") + b"." + raw_body
        expected = hmac.new(self.webhook_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in parts.get("v1", [])):
            raise StripeSignatureError("Stripe webhook signature verification failed")

    def _accept_paid_checkout(
        self,
        state: dict[str, Any],
        event_id: str,
        event_type: str,
        session: Mapping[str, Any],
        raw_body: bytes,
    ) -> dict[str, Any]:
        metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
        proposal_id = str(metadata.get("proposal_id") or "").strip()
        proposal = state["proposals"].get(proposal_id)
        if not isinstance(proposal, dict):
            return self._reject_event(state, event_id, event_type, "proposal_not_found", raw_body)
        checks = self._payment_checks(proposal, session, metadata)
        failures = [name for name, passed in checks.items() if not passed]
        if failures:
            result = self._reject_event(state, event_id, event_type, "validation_failed:" + ",".join(failures), raw_body, proposal_id=proposal_id)
            result["checks"] = checks
            return result
        payment_intent = str(session.get("payment_intent") or "").strip()
        existing = state["payments"].get(proposal_id)
        if isinstance(existing, dict) and str(existing.get("payment_intent") or "") != payment_intent:
            return self._reject_event(state, event_id, event_type, "duplicate_payment_conflict", raw_body, proposal_id=proposal_id)

        evidence = {
            "proposal_id": proposal_id,
            "workspace_id": proposal["workspace_id"],
            "client_id": proposal["client_id"],
            "stripe_event_id": event_id,
            "stripe_event_type": event_type,
            "checkout_session_id": str(session.get("id") or ""),
            "payment_intent": payment_intent,
            "invoice_id": str(session.get("invoice") or ""),
            "amount_minor": int(session.get("amount_total") or 0),
            "currency": str(session.get("currency") or "").lower(),
            "terms_accepted": True,
            "proposal_checksum": proposal["proposal_checksum"],
            "raw_event_sha256": hashlib.sha256(raw_body).hexdigest(),
            "verified_at": _now(),
            "mode": "test",
        }
        if isinstance(existing, dict):
            if not evidence["invoice_id"]:
                evidence["invoice_id"] = str(existing.get("invoice_id") or "")
            previous_actions = existing.get("follow_through") if isinstance(existing.get("follow_through"), dict) else {}
            actions = self._run_actions(proposal, evidence, previous=previous_actions)
            evidence["follow_through"] = actions
            state["payments"][proposal_id] = evidence
            prerequisites_complete = bool(proposal.get("prerequisites_complete"))
            work_authorised = prerequisites_complete and actions["crm"]["verified"] and actions["workflow"]["verified"]
            result = {
                "event_id": event_id,
                "event_type": event_type,
                "proposal_id": proposal_id,
                "status": "payment_verified",
                "payment": evidence,
                "actions": actions,
                "prerequisites_complete": prerequisites_complete,
                "outstanding_inputs": list(proposal.get("outstanding_inputs") or []),
                "work_authorised": work_authorised,
                "payment_replay": True,
                "replay": False,
            }
            state["processed_events"][event_id] = result
            self.store.save(state, {"kind": "payment_reconciled", "event_id": event_id, "proposal_id": proposal_id, "work_authorised": work_authorised, "actions": actions})
            return result
        state["payments"][proposal_id] = evidence
        proposal["checkout"].update({"status": "complete", "payment_status": "paid", "paid_at": evidence["verified_at"]})
        state["proposals"][proposal_id] = proposal
        self.store.save(state, {"kind": "payment_verified", **evidence})

        actions = self._run_actions(proposal, evidence)
        evidence["follow_through"] = actions
        prerequisites_complete = bool(proposal.get("prerequisites_complete"))
        work_authorised = prerequisites_complete and actions["crm"]["verified"] and actions["workflow"]["verified"]
        result = {
            "event_id": event_id,
            "event_type": event_type,
            "proposal_id": proposal_id,
            "status": "payment_verified",
            "payment": evidence,
            "actions": actions,
            "prerequisites_complete": prerequisites_complete,
            "outstanding_inputs": list(proposal.get("outstanding_inputs") or []),
            "work_authorised": work_authorised,
            "replay": False,
        }
        state = self.store.load()
        state["payments"][proposal_id] = evidence
        state["processed_events"][event_id] = result
        self.store.save(state, {"kind": "payment_follow_through_recorded", "event_id": event_id, "proposal_id": proposal_id, "work_authorised": work_authorised, "actions": actions})
        return result

    def _run_actions(
        self,
        proposal: Mapping[str, Any],
        evidence: Mapping[str, Any],
        *,
        previous: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        prior = previous or {}
        context = {
            "proposal": dict(proposal),
            "payment": dict(evidence),
            "acceptance": {
                "accepted": True,
                "terms_accepted": True,
                "accepted_at": evidence["verified_at"],
                "source": "stripe_checkout_verified",
            },
        }
        crm = self._action_once(prior.get("crm"), self.crm_update, context, required=True)
        notify = self._action_once(prior.get("founder_notification"), self.founder_notification, context, required=False)
        workflow = {"verified": False, "status": "blocked_missing_prerequisites"}
        if proposal.get("prerequisites_complete") and crm["verified"]:
            workflow = self._action_once(prior.get("workflow"), self.workflow_authorisation, context, required=True)
        confirmation_context = {
            **context,
            "delivery_commitment_days": proposal.get("delivery_commitment_days", 7),
            "delivery_clock_started": bool(workflow.get("verified")),
            "outstanding_inputs": list(proposal.get("outstanding_inputs") or []),
            "invoice_id": evidence.get("invoice_id", ""),
        }
        confirmation = self._action_once(prior.get("client_confirmation"), self.client_confirmation, confirmation_context, required=False)
        return {"crm": crm, "founder_notification": notify, "workflow": workflow, "client_confirmation": confirmation}

    @classmethod
    def _action_once(cls, previous: Any, action: Action | None, context: Mapping[str, Any], *, required: bool) -> dict[str, Any]:
        if isinstance(previous, Mapping) and previous.get("verified") is True:
            return dict(previous)
        return cls._action(action, context, required=required)

    @staticmethod
    def _action(action: Action | None, context: Mapping[str, Any], *, required: bool) -> dict[str, Any]:
        if action is None:
            return {"verified": False, "status": "unavailable" if required else "not_configured"}
        try:
            result = action(context)
        except Exception as exc:
            return {"verified": False, "status": "failed", "error": str(exc)[:300]}
        if not isinstance(result, Mapping):
            return {"verified": False, "status": "unverified_result"}
        verified = result.get("verified") is True
        return {**dict(result), "verified": verified, "status": str(result.get("status") or ("verified" if verified else "unverified"))}

    def _record_non_success(self, state: dict[str, Any], event_id: str, event_type: str, obj: Mapping[str, Any], status: str) -> dict[str, Any]:
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        result = {
            "event_id": event_id,
            "event_type": event_type,
            "proposal_id": str(metadata.get("proposal_id") or ""),
            "status": status,
            "work_authorised": False,
            "replay": False,
        }
        state["processed_events"][event_id] = result
        self.store.save(state, {"kind": "payment_not_completed", **result})
        return result

    def _reject_event(
        self,
        state: dict[str, Any],
        event_id: str,
        event_type: str,
        reason: str,
        raw_body: bytes,
        *,
        proposal_id: str = "",
    ) -> dict[str, Any]:
        result = {
            "event_id": event_id,
            "event_type": event_type,
            "proposal_id": proposal_id,
            "status": "rejected",
            "reason": reason,
            "raw_event_sha256": hashlib.sha256(raw_body).hexdigest(),
            "work_authorised": False,
            "replay": False,
        }
        state["processed_events"][event_id] = result
        self.store.save(state, {"kind": "payment_rejected", **result})
        return result

    @staticmethod
    def _payment_checks(proposal: Mapping[str, Any], session: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, bool]:
        checkout = proposal.get("checkout") if isinstance(proposal.get("checkout"), dict) else {}
        consent = session.get("consent") if isinstance(session.get("consent"), dict) else {}
        return {
            "checkout_session": str(session.get("id") or "") == str(checkout.get("session_id") or ""),
            "client_reference": str(session.get("client_reference_id") or "") == str(proposal.get("client_id") or ""),
            "workspace": str(metadata.get("workspace_id") or "") == str(proposal.get("workspace_id") or ""),
            "client": str(metadata.get("client_id") or "") == str(proposal.get("client_id") or ""),
            "proposal_checksum": str(metadata.get("proposal_checksum") or "") == str(proposal.get("proposal_checksum") or ""),
            "amount": int(session.get("amount_total") or -1) == int(proposal.get("deposit_amount_minor") or 0),
            "currency": str(session.get("currency") or "").lower() == str(proposal.get("currency") or "").lower(),
            "paid": str(session.get("payment_status") or "") == "paid",
            "payment_mode": str(session.get("mode") or "") == "payment",
            "terms": str(consent.get("terms_of_service") or "") == "accepted",
        }

    @staticmethod
    def _proposal_record(proposal: ApprovedFieldworkProposal) -> dict[str, Any]:
        value = asdict(proposal)
        value["currency"] = proposal.currency.lower()
        value["required_inputs"] = list(proposal.required_inputs)
        value["received_inputs"] = list(proposal.received_inputs)
        value["workflow_inputs"] = dict(proposal.workflow_inputs)
        value["prerequisites_complete"] = proposal.prerequisites_complete
        value["outstanding_inputs"] = list(proposal.outstanding_inputs)
        return value

    def _checkout_payload(self, proposal: ApprovedFieldworkProposal) -> dict[str, str]:
        total = _money(proposal.total_amount_minor, proposal.currency)
        deposit = _money(proposal.deposit_amount_minor, proposal.currency)
        balance = _money(proposal.total_amount_minor - proposal.deposit_amount_minor, proposal.currency)
        description = (
            f"{proposal.scope_summary} Total investment: {total}. Due now: {deposit}. "
            f"Remaining balance: {balance}. {proposal.balance_terms}"
        )
        if len(description) > 500:
            raise FieldworkPaymentError("agreed Checkout description exceeds Stripe's safe display limit")
        metadata = {
            "proposal_id": proposal.proposal_id,
            "workspace_id": proposal.workspace_id,
            "client_id": proposal.client_id,
            "proposal_checksum": proposal.proposal_checksum,
        }
        identifier_digest = hashlib.sha256(
            f"{proposal.workspace_id}:{proposal.proposal_id}:{proposal.proposal_checksum}".encode("utf-8")
        ).digest()
        identifier_suffix = "".join(chr(ord("a") + value % 26) for value in identifier_digest[:8])
        payload = {
            "mode": "payment",
            "integration_identifier": f"fieldwork_{identifier_suffix}",
            "client_reference_id": proposal.client_id,
            "customer_email": proposal.client_email,
            "success_url": self.success_url,
            "cancel_url": self.cancel_url,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": proposal.currency.lower(),
            "line_items[0][price_data][unit_amount]": str(proposal.deposit_amount_minor),
            "line_items[0][price_data][product_data][name]": "FIELDWORK — agreed deposit",
            "line_items[0][price_data][product_data][description]": description,
            "consent_collection[terms_of_service]": "required",
            "custom_text[submit][message]": f"This payment is the agreed FIELDWORK deposit. The remaining balance follows the terms shown above.",
            "custom_text[terms_of_service_acceptance][message]": f"I accept the agreed FIELDWORK proposal and the applicable service terms at {proposal.service_terms_url}.",
            "invoice_creation[enabled]": "true",
            "payment_intent_data[description]": f"FIELDWORK deposit — proposal {proposal.proposal_id}",
        }
        for key, value in metadata.items():
            payload[f"metadata[{key}]"] = value
            payload[f"payment_intent_data[metadata][{key}]"] = value
        return payload

    @staticmethod
    def _proposal_email(proposal: ApprovedFieldworkProposal, checkout_url: str) -> dict[str, str]:
        outstanding = ", ".join(proposal.outstanding_inputs)
        input_note = (
            f"Before the seven-day delivery window begins, we still need: {outstanding}."
            if outstanding
            else "We have the agreed starting inputs; we will confirm the delivery window after payment verification."
        )
        safe_client = html.escape(proposal.client_name)
        safe_contact = html.escape(proposal.client_contact_name)
        safe_proposal_url = html.escape(proposal.proposal_url, quote=True)
        safe_checkout_url = html.escape(checkout_url, quote=True)
        safe_input_note = html.escape(input_note)
        html_body = f"""<!doctype html>
<html><body style="margin:0;background:#f3f0ea;font-family:Arial,sans-serif;color:#17211f">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f0ea;padding:32px 16px"><tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border-radius:18px;overflow:hidden">
<tr><td style="background:#17211f;padding:28px 36px;color:#ffffff"><div style="font-size:12px;letter-spacing:2.4px">NARRATIIVE</div><h1 style="margin:18px 0 0;font-size:30px;line-height:1.15">FIELDWORK, ready when you are.</h1></td></tr>
<tr><td style="padding:34px 36px"><p style="font-size:17px;line-height:1.65;margin-top:0">Hello {safe_contact},</p>
<p style="font-size:17px;line-height:1.65">Thank you for the conversation and the clarity you have shared with us. Your approved FIELDWORK proposal for {safe_client} is ready to review.</p>
<p style="font-size:16px;line-height:1.6"><a href="{safe_proposal_url}" style="color:#9b4b2f;font-weight:700">View the approved two-page proposal →</a></p>
<table role="presentation" cellspacing="0" cellpadding="0" style="margin:30px 0"><tr><td style="border-radius:999px;background:#c85f3d"><a href="{safe_checkout_url}" style="display:inline-block;padding:16px 28px;color:#ffffff;text-decoration:none;font-size:17px;font-weight:700">Let’s get started</a></td></tr></table>
<p style="font-size:14px;line-height:1.6;color:#53605d">{safe_input_note}</p>
<p style="font-size:14px;line-height:1.6;color:#53605d">Once payment and the required inputs are verified, we will confirm that the seven-day delivery window has started.</p>
<p style="font-size:17px;line-height:1.65;margin-bottom:0">Narratiive</p></td></tr></table>
</td></tr></table></body></html>"""
        return {
            "subject": f"Your FIELDWORK proposal — {proposal.client_name}",
            "recipient": proposal.client_email,
            "body": (
                f"Hello {proposal.client_contact_name},\n\nThank you for the conversation and the clarity you have shared with us. "
                f"Your approved two-page FIELDWORK proposal is here: {proposal.proposal_url}\n\n"
                f"When you are ready, use the secure test-mode payment link below to accept the applicable service terms and pay the agreed deposit:\n\n"
                f"Let’s get started: {checkout_url}\n\n{input_note}\n\n"
                "Once payment and the required inputs are verified, we will confirm that the seven-day delivery window has started.\n\nNarratiive"
            ),
            "html_body": html_body,
        }


def stripe_signature(raw_body: bytes, webhook_secret: str, timestamp: int) -> str:
    """Test helper matching Stripe's v1 signing algorithm."""
    signed = str(timestamp).encode("ascii") + b"." + raw_body
    digest = hmac.new(webhook_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def _money(amount_minor: int, currency: str) -> str:
    symbol = "£" if currency.lower() == "gbp" else f"{currency.upper()} "
    return f"{symbol}{amount_minor / 100:,.2f}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
