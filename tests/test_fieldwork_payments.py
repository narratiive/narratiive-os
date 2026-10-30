from __future__ import annotations

import json
import io
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from runtime.fieldwork_payment_integrations import (
    gmail_client_confirmation,
    gmail_proposal_delivery,
    notion_payment_recorder,
    tony_workflow_authoriser,
)
from runtime.fieldwork_payments import (
    ApprovedFieldworkProposal,
    FieldworkPaymentService,
    FieldworkPaymentStore,
    StripeSignatureError,
    stripe_signature,
)
from openclaw.fieldwork_payment_bridge import FieldworkPaymentApplication


NOW = 1_800_000_000
WEBHOOK_SECRET = "whsec_test_fieldwork_demo"


class FakeStripe:
    def __init__(self) -> None:
        self.created: list[tuple[dict[str, str], str]] = []
        self.remote: dict[str, object] = {}

    def create_checkout(self, payload, *, idempotency_key):
        self.created.append((dict(payload), idempotency_key))
        return {"id": "cs_test_fieldwork_1", "url": "https://checkout.stripe.test/c/pay/demo", "status": "open", "payment_status": "unpaid"}

    def retrieve_checkout(self, session_id):
        if session_id != "cs_test_fieldwork_1":
            raise AssertionError(session_id)
        return dict(self.remote)


def proposal(*, complete: bool = True) -> ApprovedFieldworkProposal:
    return ApprovedFieldworkProposal(
        proposal_id="proposal-fieldwork-001",
        workspace_id="narratiive",
        client_id="synthetic-client-001",
        client_name="Synthetic Fieldwork Foods",
        client_contact_name="Alex",
        client_email="client@example.invalid",
        proposal_url="https://drive.example.invalid/proposal-fieldwork-001",
        proposal_checksum="sha256:synthetic-proposal-v1",
        scope_summary="A two-page FIELDWORK strategic growth sprint covering the agreed evidence, diagnosis and action plan.",
        total_amount_minor=600_000,
        deposit_amount_minor=300_000,
        currency="GBP",
        balance_terms="The remaining balance is due on delivery of the agreed FIELDWORK output.",
        service_terms_url="https://narratiive.example.invalid/terms",
        founder_approval_id="approval-matt-synthetic-001",
        founder_approved_at="2026-10-30T09:00:00+00:00",
        parent_workflow_run_id="proposal-run-synthetic-001",
        commercial_record_id="notion-synthetic-record-001",
        required_inputs=("approved brief", "source pack"),
        received_inputs=("approved brief", "source pack") if complete else ("approved brief",),
        workflow_inputs={
            "approved_growth_sprint_scope": {"scope": "synthetic FIELDWORK scope"},
            "research_requirements": ["synthetic category evidence"],
            "research_sources": [],
            "client_context": {"company": "Synthetic Fieldwork Foods"},
        },
    )


def session_object(*, amount: int = 300_000, payment_intent: str = "pi_test_fieldwork_1", status: str = "paid") -> dict[str, object]:
    item = proposal()
    return {
        "id": "cs_test_fieldwork_1",
        "mode": "payment",
        "payment_status": status,
        "amount_total": amount,
        "currency": "gbp",
        "client_reference_id": item.client_id,
        "payment_intent": payment_intent,
        "invoice": "in_test_fieldwork_1",
        "consent": {"terms_of_service": "accepted"},
        "metadata": {
            "proposal_id": item.proposal_id,
            "workspace_id": item.workspace_id,
            "client_id": item.client_id,
            "proposal_checksum": item.proposal_checksum,
        },
    }


def event(event_id: str, event_type: str, obj: dict[str, object]) -> bytes:
    return json.dumps({"id": event_id, "type": event_type, "livemode": False, "data": {"object": obj}}, separators=(",", ":")).encode()


class FieldworkPaymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stripe = FakeStripe()
        self.calls: dict[str, list[dict]] = {"crm": [], "notify": [], "workflow": [], "confirmation": []}

        def action(name):
            def run(context):
                self.calls[name].append(dict(context))
                identity = "commissioned-run-001" if name == "workflow" else f"{name}-receipt-001"
                return {"verified": True, "status": "verified", "receipt_id": identity}
            return run

        def verify(context):
            item = context["proposal"]
            return {
                "verified": True,
                "proposal_id": item["proposal_id"],
                "proposal_checksum": item["proposal_checksum"],
                "founder_approval_id": item["founder_approval_id"],
            }

        self.service = FieldworkPaymentService(
            FieldworkPaymentStore(Path(self.temp.name)),
            self.stripe,
            webhook_secret=WEBHOOK_SECRET,
            success_url="https://example.invalid/fieldwork/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://example.invalid/fieldwork/cancel",
            crm_update=action("crm"),
            founder_notification=action("notify"),
            workflow_authorisation=action("workflow"),
            client_confirmation=action("confirmation"),
            proposal_verifier=verify,
            clock=lambda: NOW,
        )

    def send_event(self, event_id: str, event_type: str, obj: dict[str, object]):
        raw = event(event_id, event_type, obj)
        return self.service.handle_webhook(raw, stripe_signature(raw, WEBHOOK_SECRET, NOW))

    def test_complete_test_mode_journey_reuses_downstream_boundaries(self):
        created = self.service.create_checkout(proposal())
        proposal_sends = []

        def fake_gmail(contract):
            proposal_sends.append(contract)
            return {"verified": True, "sent": True, "message_id": "gmail-test-proposal-1", "mutation_count": 1}

        delivery = gmail_proposal_delivery(fake_gmail, self.service.proposal_verifier)(proposal(), checkout_url=created["checkout"]["url"])
        self.assertTrue(delivery["verified"])
        self.assertEqual(len(proposal_sends), 1)
        payload, key = self.stripe.created[0]
        self.assertFalse(created["replay"])
        self.assertEqual(payload["line_items[0][price_data][unit_amount]"], "300000")
        self.assertIn("Total investment: £6,000.00", payload["line_items[0][price_data][product_data][description]"])
        self.assertIn("Remaining balance: £3,000.00", payload["line_items[0][price_data][product_data][description]"])
        self.assertEqual(payload["consent_collection[terms_of_service]"], "required")
        self.assertRegex(payload["integration_identifier"], r"^fieldwork_[a-z]{8}$")
        self.assertIn("applicable service terms", payload["custom_text[terms_of_service_acceptance][message]"])
        self.assertEqual(payload["invoice_creation[enabled]"], "true")
        self.assertIn("proposal-fieldwork-001", key)
        self.assertIn("Let’s get started", created["email"]["body"])
        self.assertIn("Hello Alex", created["email"]["body"])
        self.assertIn(">Let’s get started</a>", created["email"]["html_body"])
        self.assertIn("border-radius:999px", created["email"]["html_body"])

        result = self.send_event("evt_test_success_1", "checkout.session.completed", session_object())
        self.assertEqual(result["status"], "payment_verified")
        self.assertTrue(result["work_authorised"])
        self.assertEqual(result["payment"]["amount_minor"], 300_000)
        self.assertEqual(result["payment"]["currency"], "gbp")
        self.assertEqual([len(self.calls[name]) for name in self.calls], [1, 1, 1, 1])
        self.assertTrue(result["actions"]["crm"]["verified"])
        self.assertTrue(result["actions"]["workflow"]["verified"])

        journal = (Path(self.temp.name) / "fieldwork-payment-events.jsonl").read_text().splitlines()
        kinds = [json.loads(line)["kind"] for line in journal]
        self.assertEqual(kinds, ["checkout_created", "payment_verified", "payment_follow_through_recorded"])
        records = [json.loads(line) for line in journal]
        self.assertEqual(records[1]["previous_checksum"], records[0]["checksum"])
        self.assertEqual(records[2]["previous_checksum"], records[1]["checksum"])
        self.assertEqual(stat.S_IMODE((Path(self.temp.name) / "fieldwork-payment-events.jsonl").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((Path(self.temp.name) / "fieldwork-payments.json").stat().st_mode), 0o600)

    def test_duplicate_webhook_is_idempotent_and_does_not_repeat_actions(self):
        self.service.create_checkout(proposal())
        first = self.send_event("evt_test_success_1", "checkout.session.completed", session_object())
        second = self.send_event("evt_test_success_1", "checkout.session.completed", session_object())
        self.assertFalse(first["replay"])
        self.assertTrue(second["replay"])
        self.assertEqual([len(self.calls[name]) for name in self.calls], [1, 1, 1, 1])

    def test_signature_verification_rejects_tampering_and_stale_timestamp(self):
        raw = event("evt_bad_sig", "checkout.session.completed", session_object())
        with self.assertRaises(StripeSignatureError):
            self.service.handle_webhook(raw + b" ", stripe_signature(raw, WEBHOOK_SECRET, NOW))
        with self.assertRaises(StripeSignatureError):
            self.service.handle_webhook(raw, stripe_signature(raw, WEBHOOK_SECRET, NOW - 301))

    def test_wrong_amount_is_rejected_without_downstream_actions(self):
        self.service.create_checkout(proposal())
        result = self.send_event("evt_wrong_amount", "checkout.session.completed", session_object(amount=299_999))
        self.assertEqual(result["status"], "rejected")
        self.assertIn("amount", result["reason"])
        self.assertFalse(result["work_authorised"])
        self.assertEqual([len(self.calls[name]) for name in self.calls], [0, 0, 0, 0])

    def test_second_payment_for_same_proposal_is_blocked(self):
        self.service.create_checkout(proposal())
        self.send_event("evt_paid_1", "checkout.session.completed", session_object(payment_intent="pi_test_first"))
        result = self.send_event("evt_paid_2", "checkout.session.completed", session_object(payment_intent="pi_test_second"))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "duplicate_payment_conflict")
        self.assertEqual([len(self.calls[name]) for name in self.calls], [1, 1, 1, 1])

    def test_second_success_event_for_same_payment_does_not_repeat_verified_actions(self):
        self.service.create_checkout(proposal())
        self.send_event("evt_completed", "checkout.session.completed", session_object())
        result = self.send_event("evt_async_succeeded", "checkout.session.async_payment_succeeded", session_object())
        self.assertTrue(result["payment_replay"])
        self.assertTrue(result["work_authorised"])
        self.assertEqual([len(self.calls[name]) for name in self.calls], [1, 1, 1, 1])

    def test_failed_and_abandoned_checkout_never_authorise_work(self):
        self.service.create_checkout(proposal())
        failed = self.send_event("evt_failed", "checkout.session.async_payment_failed", session_object(status="unpaid"))
        abandoned = self.send_event("evt_expired", "checkout.session.expired", session_object(status="unpaid"))
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(abandoned["status"], "abandoned")
        self.assertFalse(failed["work_authorised"])
        self.assertFalse(abandoned["work_authorised"])
        self.assertEqual([len(self.calls[name]) for name in self.calls], [0, 0, 0, 0])

    def test_missing_client_input_records_payment_but_does_not_start_work(self):
        self.service.create_checkout(proposal(complete=False))
        result = self.send_event("evt_waiting_input", "checkout.session.completed", session_object())
        self.assertEqual(result["status"], "payment_verified")
        self.assertFalse(result["work_authorised"])
        self.assertEqual(result["outstanding_inputs"], ["source pack"])
        self.assertEqual(len(self.calls["crm"]), 1)
        self.assertEqual(len(self.calls["notify"]), 1)
        self.assertEqual(len(self.calls["workflow"]), 0)
        self.assertEqual(len(self.calls["confirmation"]), 1)
        self.assertFalse(self.calls["confirmation"][0]["delivery_clock_started"])

    def test_reconciliation_reads_stripe_and_recovers_missing_success_event(self):
        self.service.create_checkout(proposal())
        self.stripe.remote = session_object()
        result = self.service.reconcile("proposal-fieldwork-001")
        self.assertEqual(result["status"], "payment_verified")
        self.assertTrue(result["work_authorised"])
        self.assertTrue(result["event_id"].startswith("reconcile:cs_test_fieldwork_1"))

    def test_reconciliation_retries_only_unverified_follow_through(self):
        attempts = []

        def workflow(context):
            attempts.append(dict(context))
            if len(attempts) == 1:
                raise RuntimeError("synthetic transient commission failure")
            return {"verified": True, "status": "commissioned", "run_id": "synthetic-run-1"}

        service = FieldworkPaymentService(
            FieldworkPaymentStore(Path(self.temp.name) / "retry"),
            self.stripe,
            webhook_secret=WEBHOOK_SECRET,
            success_url="https://example.invalid/success",
            cancel_url="https://example.invalid/cancel",
            crm_update=lambda _context: {"verified": True, "record_id": "crm-1"},
            founder_notification=lambda _context: {"verified": True, "message_id": "telegram-1"},
            workflow_authorisation=workflow,
            client_confirmation=lambda _context: {"verified": True, "message_id": "gmail-1"},
            proposal_verifier=self.service.proposal_verifier,
            clock=lambda: NOW,
        )
        service.create_checkout(proposal())
        raw = event("evt_retry_first", "checkout.session.completed", session_object())
        first = service.handle_webhook(raw, stripe_signature(raw, WEBHOOK_SECRET, NOW))
        self.assertFalse(first["work_authorised"])
        self.stripe.remote = session_object()
        recovered = service.reconcile("proposal-fieldwork-001")
        self.assertTrue(recovered["work_authorised"])
        self.assertEqual(len(attempts), 2)

    def test_checkout_registration_is_immutable_and_idempotent(self):
        first = self.service.create_checkout(proposal())
        second = self.service.create_checkout(proposal())
        self.assertFalse(first["replay"])
        self.assertTrue(second["replay"])
        self.assertEqual(len(self.stripe.created), 1)

    def test_checkout_fails_closed_without_exact_proposal_verification(self):
        service = FieldworkPaymentService(
            FieldworkPaymentStore(Path(self.temp.name) / "unverified"), self.stripe,
            webhook_secret=WEBHOOK_SECRET, success_url="https://example.invalid/success", cancel_url="https://example.invalid/cancel",
        )
        with self.assertRaisesRegex(RuntimeError, "approved proposal verification failed"):
            service.create_checkout(proposal())
        self.assertEqual(self.stripe.created, [])

    def test_corrupt_payment_journal_fails_before_state_is_used(self):
        self.service.create_checkout(proposal())
        journal = Path(self.temp.name) / "fieldwork-payment-events.jsonl"
        lines = journal.read_text().splitlines()
        record = json.loads(lines[0])
        record["proposal_id"] = "tampered"
        journal.write_text(json.dumps(record) + "\n")
        with self.assertRaisesRegex(RuntimeError, "integrity check failed"):
            self.service.create_checkout(proposal())


class FieldworkIntegrationAdapterTests(unittest.TestCase):
    def test_notion_payment_projection_is_exact_and_idempotent(self):
        calls = []

        def notion(contract):
            calls.append(contract)
            return {"verified": True, "record_id": contract["target"]["record_id"], "mutation_count": 1}

        action = notion_payment_recorder(notion)
        result = action({"proposal": FieldworkPaymentService._proposal_record(proposal()), "payment": {"payment_intent": "pi_test_1", "stripe_event_id": "evt_1"}})
        self.assertTrue(result["verified"])
        self.assertEqual(calls[0]["target"]["record_id"], "notion-synthetic-record-001")
        self.assertEqual(calls[0]["payload"]["kind"], "fieldwork_verified_acceptance_payment")
        self.assertTrue(calls[0]["approval_granted"])

    def test_gmail_adapters_bind_exact_messages_to_idempotency_keys(self):
        calls = []

        def gmail(contract):
            calls.append(contract)
            return {"verified": True, "message_id": f"gmail-{len(calls)}", "mutation_count": 1}

        item = proposal()
        proposal_action = gmail_proposal_delivery(
            gmail,
            lambda context: {"verified": True, "proposal_id": context["proposal"]["proposal_id"], "proposal_checksum": context["proposal"]["proposal_checksum"], "founder_approval_id": context["proposal"]["founder_approval_id"]},
        )
        proposal_result = proposal_action(item, checkout_url="https://checkout.example.invalid/test")
        confirm_action = gmail_client_confirmation(gmail)
        confirm_result = confirm_action(
            {
                "proposal": FieldworkPaymentService._proposal_record(proposal()),
                "payment": {"payment_intent": "pi_test_1"},
                "outstanding_inputs": [],
                "delivery_clock_started": True,
                "invoice_id": "in_test_1",
            }
        )
        self.assertTrue(proposal_result["verified"])
        self.assertTrue(confirm_result["verified"])
        self.assertIn("checkout.example.invalid", calls[0]["payload"]["html_body"])
        self.assertNotEqual(calls[0]["idempotency_key"], calls[1]["idempotency_key"])
        self.assertIn("seven-day FIELDWORK delivery window is now under way", calls[1]["payload"]["body"])

    def test_tony_authoriser_binds_payment_to_exact_approved_proposal_artifact(self):
        approved_at = "2026-10-30T09:00:00+00:00"
        parent = SimpleNamespace(
            run_id="proposal-run-synthetic-001", client_id="synthetic-client-001", workspace_id="narratiive",
            approval_status="approved", approval_history=[{"approved_at": approved_at}],
            stages=[SimpleNamespace(revision_count=0, output_artifacts=[SimpleNamespace(checksum="synthetic-proposal-v1")])],
        )
        commissioned = SimpleNamespace(
            run_id="research-run-001", workflow_id="growth_sprint_to_research_engine",
            workspace_id="narratiive", client_id="synthetic-client-001",
        )
        backend = mock.Mock()
        backend.list_states.return_value = (parent,)
        backend.commission.return_value = (commissioned, False)
        proposal_record = FieldworkPaymentService._proposal_record(proposal())
        proposal_record["founder_approval_id"] = "approval-proposal-run-synthetic-001-0"
        proposal_record["founder_approved_at"] = approved_at
        context = {"proposal": proposal_record, "payment": {"payment_intent": "pi_test_1"}, "acceptance": {"accepted": True}}

        with mock.patch("runtime.tony_workflow_commands.FileWorkflowCommandBackend", return_value=backend):
            result = tony_workflow_authoriser(Path("/synthetic"), workspace_id="narratiive")(context)
        self.assertTrue(result["verified"])
        self.assertEqual(result["run_id"], "research-run-001")
        self.assertEqual(backend.commission.call_args.kwargs["commitment_id"], "fieldwork-payment:proposal-fieldwork-001:pi_test_1")

        proposal_record["proposal_checksum"] = "sha256:wrong"
        with mock.patch("runtime.tony_workflow_commands.FileWorkflowCommandBackend", return_value=backend):
            with self.assertRaisesRegex(RuntimeError, "checksum"):
                tony_workflow_authoriser(Path("/synthetic"), workspace_id="narratiive")(context)


class FieldworkPaymentApplicationTests(unittest.TestCase):
    def test_checkout_requires_bridge_auth_and_webhook_requires_stripe_signature(self):
        with tempfile.TemporaryDirectory() as temporary:
            stripe = FakeStripe()
            service = FieldworkPaymentService(
                FieldworkPaymentStore(Path(temporary)), stripe,
                webhook_secret=WEBHOOK_SECRET,
                success_url="https://example.invalid/success",
                cancel_url="https://example.invalid/cancel",
                proposal_verifier=lambda context: {"verified": True, "proposal_id": context["proposal"]["proposal_id"], "proposal_checksum": context["proposal"]["proposal_checksum"], "founder_approval_id": context["proposal"]["founder_approval_id"]},
                clock=lambda: NOW,
            )
            app = FieldworkPaymentApplication(service, bridge_token="safe-token", proposal_loader=lambda _proposal_id: proposal())

            status, payload = self._request(app, "/fieldwork/checkout", {"proposal_id": "proposal-fieldwork-001"})
            self.assertEqual(status, 401)
            self.assertFalse(payload["ok"])

            status, payload = self._request(
                app,
                "/fieldwork/checkout",
                {"proposal_id": "proposal-fieldwork-001"},
                headers={"HTTP_AUTHORIZATION": "Bearer safe-token"},
            )
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])

            raw = event("evt_app_success", "checkout.session.completed", session_object())
            status, payload = self._request(app, "/fieldwork/stripe/webhook", raw=raw)
            self.assertEqual(status, 400)
            self.assertFalse(payload["ok"])
            status, payload = self._request(
                app,
                "/fieldwork/stripe/webhook",
                raw=raw,
                headers={"HTTP_STRIPE_SIGNATURE": stripe_signature(raw, WEBHOOK_SECRET, NOW)},
            )
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["work_authorised"])

    @staticmethod
    def _request(app, path, payload=None, *, raw=None, headers=None):
        body = raw if raw is not None else json.dumps(payload or {}).encode()
        captured = {}

        def start_response(status, _headers):
            captured["status"] = int(status.split()[0])

        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            **dict(headers or {}),
        }
        response = b"".join(app(environ, start_response))
        return captured["status"], json.loads(response)


if __name__ == "__main__":
    unittest.main()
