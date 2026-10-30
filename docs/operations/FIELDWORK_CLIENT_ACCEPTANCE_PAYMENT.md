# FIELDWORK client acceptance and payment

Status: Stripe test-mode implementation and operational audit
Date: 30 October 2026

## Outcome

Narratiive OS now has a narrow Stripe Checkout boundary for a founder-approved
FIELDWORK proposal. It does not introduce a second workflow engine. Verified
payment is projected into the existing Notion commercial record and commissions
Tony's existing registered workflow only after exact commercial and prerequisite
checks pass.

The implementation is test-mode only. It does not enable live cards, send a real
client email, mutate the live Notion workspace, notify the live Telegram chat or
commission paid specialist work during acceptance testing.

## Audit: what already existed

| Capability | Existing operational evidence | Reuse decision |
| --- | --- | --- |
| Proposal production | `discovery_evidence_to_growth_sprint_proposal` produces a governed Growth Sprint proposal with evidence lineage and commercial inputs. | Reuse. |
| Founder review | Workflow approval binds the decision to the exact artefact checksum and approval token. | Reuse; checkout registration requires the recorded founder approval ID and proposal checksum. |
| Proposal email | Gmail has an approval-gated, idempotent send adapter with verified message IDs. The current post-Discovery service separately gates proposal send and Notion stage sync. | Reuse through the narrow FIELDWORK proposal delivery adapter. |
| Proposal outcome | Tony already monitors the exact Gmail thread and distinguishes acceptance intent, objection, decline and silence. | Retain for non-Checkout replies; Stripe becomes the payment proof. |
| Commercial lifecycle | Notion is authoritative for live lead/commercial state. The repository also exposes `ClientLifecycleRecord` and Mission Control projections. | Reuse the exact existing Notion record; do not create a duplicate client. |
| Commercial close | Tony can request a scoped commercial-close attestation and onboarding approval. | Payment automation replaces only the human claim that payment requirements are satisfied; it does not weaken other gates. |
| Invoicing | The canonical lifecycle includes `INVOICE`, but there was no executable invoice/payment service. | Stripe Checkout requests invoice creation and retains the returned invoice ID. |
| Tony orchestration | `FileWorkflowCommandBackend.commission` creates an idempotent downstream run through the registered workflow runtime. | Reuse exactly. |
| FIELDWORK execution | The existing Growth Sprint → Research Engine → strategic synthesis → Growth Blueprint sequence and specialist quality gates are registered. | Reuse exactly. |
| Founder notification | Telegram outbound transport and authenticated Tony conversation already exist. | Reuse the outbound sender; Tony's conversational infrastructure is unchanged. |
| n8n | Live-local n8n has active lead intake, campaign learning and media workflows. | No payment workflow was found; n8n is not needed in the critical payment proof path. |
| Stripe/payment service | No Stripe source, dependency, CLI, environment key, n8n credential or Stripe/payment workflow was found in the feature checkout, canonical checkout or live-local n8n metadata. A subsequently connected Stripe account is a non-live `Narratiive sandbox`; read-only inspection found no Checkout Sessions, webhook endpoints, products or PaymentIntents. | Reuse the clean sandbox for acceptance testing and build only the missing boundary. |

The live-local integration inventory was read-only. Configured reusable workers
were Claude, Client Delivery, Creative Production, Fireflies, Gmail, Google
Calendar, Google Drive, GitHub, Notion and n8n. No credential values were printed
or persisted.

## What was built

### Checkout

`runtime.fieldwork_payments` registers immutable approved proposal terms and
creates one Stripe Checkout session using a deterministic idempotency key. It
requires a Stripe test secret key and rejects live keys.

The client pins Stripe API `2026-09-30.endive` and supplies a stable
`integration_identifier` for the FIELDWORK flow. Payment method types are not
hard-coded, leaving Stripe's sandbox-configured dynamic payment methods in
control.

Checkout presents:

- the agreed FIELDWORK scope summary;
- total investment;
- deposit due now;
- remaining balance and balance terms;
- a required Stripe terms-of-service consent;
- a link to the applicable service terms;
- Stripe invoice creation.

Only the agreed commercial terms are sent to Stripe. Internal pricing method,
margin, capacity and pricing rationale are excluded.

The client email is produced from the exact approved proposal URL and Checkout
URL. The existing Gmail adapter supplies idempotent send and returned message
evidence when production sending is later enabled.

### Payment proof and evidence

The webhook boundary:

- verifies Stripe's HMAC-SHA256 `v1` signature against the raw body;
- enforces the timestamp tolerance;
- rejects live-mode events;
- matches Checkout session, workspace, client, proposal ID and proposal checksum;
- validates deposit amount and currency exactly;
- requires `payment_status=paid`, payment mode and accepted service terms;
- processes Stripe event IDs idempotently;
- blocks a second payment intent for the same proposal;
- stores a SHA-256 digest of the raw event rather than raw client/payment data;
- keeps atomic current state plus a hash-chained append-only JSONL evidence log.

Browser success redirects are never read as payment proof.

### Reconciliation and downstream effects

The authenticated reconciliation endpoint retrieves the Checkout session from
Stripe. It recovers a missing success webhook and retries only downstream steps
that lack verified evidence. A second Stripe success event for the same payment
does not repeat already verified actions.

After verified payment:

1. the exact existing Notion commercial record is marked Active / Growth Sprint,
   with the proposal and payment evidence marker;
2. Tony receives a concise Telegram notification;
3. the existing workflow backend commissions the registered downstream workflow
   with the approved proposal inputs, verified acceptance and verified payment;
4. the client receives payment confirmation and invoice/receipt status through
   the existing Gmail adapter.

Workflow commission occurs only when the Notion projection is verified and all
recorded required client inputs are present. If inputs are missing, payment and
acceptance remain recorded, Tony and the client are informed, and specialist work
does not start.

The client wording commits to seven days but starts that window only after the
recorded prerequisites are complete. No calendar delivery date is invented.

## Isolated HTTP boundary

`openclaw.fieldwork_payment_bridge.FieldworkPaymentApplication` exposes:

- `GET /health`;
- authenticated `POST /fieldwork/checkout`;
- public `POST /fieldwork/stripe/webhook`, authenticated by Stripe signature;
- authenticated `POST /fieldwork/reconcile`.

It is deliberately separate from `tony_live_bridge.py`; Tony's working Telegram
and conversational routes were not changed.

The safe local entry point is `scripts/run_fieldwork_payment_bridge.py`. Its
required runtime-only settings are:

```text
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
FIELDWORK_PAYMENT_BRIDGE_TOKEN=<random bearer token>
FIELDWORK_APPROVED_PROPOSALS_PATH=<protected JSON registry>
FIELDWORK_PAYMENT_RUNTIME_ROOT=<protected runtime directory>
FIELDWORK_WORKFLOW_RUNTIME_ROOT=<authoritative workflow runtime directory>
FIELDWORK_WORKSPACE_ID=<exact approved-proposal workspace>
FIELDWORK_CHECKOUT_SUCCESS_URL=<non-authoritative confirmation page>
FIELDWORK_CHECKOUT_CANCEL_URL=<return-to-proposal page>
FIELDWORK_PAYMENT_HOST=127.0.0.1
FIELDWORK_PAYMENT_PORT=8794
```

Secret values and the approved-proposal registry remain outside Git.

## Test-mode demonstration

`scripts/demo_fieldwork_payment_journey.py` performs a fully synthetic run with
no network or external writes:

```text
approved proposal
→ Stripe test Checkout created
→ signed checkout.session.completed
→ exact deposit and terms verified
→ synthetic canonical CRM receipt
→ synthetic Tony Telegram receipt
→ synthetic existing-workflow commission receipt
→ synthetic client confirmation/invoice receipt
```

The demonstration result is `work_authorised=true` only after every required
gate returns verified evidence.

Automated coverage also proves:

- exact event replay does not repeat any action;
- a second success event for the same payment does not repeat any action;
- a second payment intent is rejected;
- wrong amount is rejected;
- invalid or stale signature is rejected;
- failed payment does not start work;
- abandoned Checkout does not start work;
- missing client input does not start work;
- reconciliation recovers a missed webhook and an incomplete downstream action;
- Notion and Gmail adapters use stable idempotency keys.

## What remains before production activation

Production activation is intentionally blocked until all of the following are
complete:

1. Matt approves the exact two-page client proposal format, client email copy,
   service terms, deposit/balance policy and automated post-payment communication.
   The existing internal Growth Sprint review PDF is governed and polished, but
   the repository does not currently guarantee that it is a two-page client
   document.
2. The connected `Narratiive sandbox` configuration is completed: business profile, public
   service-terms URL, branding, receipt/invoice settings, webhook endpoint and
   test signing secret.
3. A protected approved-proposal registry is populated from the exact approved
   workflow artefact and Notion record. Its founder approval identifier is the
   generated canonical commercial approval-record ID (not the approval-token
   digest). The append-only binding records the exact proposal checksum,
   version, recipient email, proposal URL, fixed investment, deposit and
   currency. No hand-entered amount, recipient or URL can bypass that binding.
4. The test bridge is deployed behind the existing secure ingress/tunnel and its
   webhook endpoint is registered in Stripe test mode, with TLS 1.2+ and Stripe
   source-IP filtering in addition to mandatory signature verification.
5. A live-local synthetic acceptance run exercises the real test-mode Stripe
   API only with `FIELDWORK_PAYMENT_DOWNSTREAM_MODE=sandbox_isolated`, explicit
   synthetic proposal IDs and an exact internal test recipient. Notion, Telegram
   and workflow effects are rejected for any other proposal or recipient; client
   confirmation email is disabled pending its own exact delivery approval.
6. Independent review is recorded against the exact commit, all repository checks
   pass, and the production wiring receives the required commercial, legal,
   security and client-facing approvals.
7. Only after those gates should a separate production change permit `sk_live_`
   credentials and enable real downstream writes. This implementation cannot
   accept a live Stripe secret key.

No real card was charged, no client communication was sent, no live Notion record
was changed, no Telegram message was sent and no paid specialist service was
started during this work.
