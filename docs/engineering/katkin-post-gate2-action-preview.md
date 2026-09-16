# KatKin post–Gate 2 action-preview repair

Status: deployed and live-preview accepted; simulated send remains human-gated.

Deployed revision: `837ac06afa6e45bb2b85e20f88a32d18d692cdb0`.

## Observed state

The preserved KatKin Growth Sprint proposal run is complete and approved. Its
canonical artefact is `artifact-15216c3acc052e09-911bd5f6a5598755` at version
`v1`, with checksum
`911bd5f6a5598755855ee4e632cb0fdb5ecda4c55ac51d814568e8b007936d81`.
The artefact contains the full `draft_client_communication` and
`commercial_proposal_inputs`. The latter is the governed timeline/investment
input to a proposal; it is not a client-contact directory.

The polished review copy is
`review-e1f07d4e63aea080b2acfdc7`, an eight-page PDF with checksum
`e75d9f98a9c4b40a64e7462b5ec19308c01a1765ee211814bc1311e9ec64626d`.
Its verified internal-review Gmail receipt is `1a0a8c1ea972b72f`.

The live OpenClaw evidence showed three independent failures:

- workflow `latest_artifact` intentionally exposed only field names and an
  excerpt, while the bridge rejected field-selection inputs;
- the lexical action policy included `email ` as a write marker, so read
  requests containing “email address” or “email thread” were promoted to
  writes;
- no authoritative action-preview payload existed. The approval surface could
  not contain recipient, subject, body or attachment data that had never been
  resolved.

The Gmail and Drive adapters also supported only identifier-anchored reads;
Notion returned an unfiltered record when no page ID was supplied. This made
the requested searches structurally impossible even after classification.

## Repair

Narratiive workflow control now exposes:

- `artifact_detail`: a checksum-verified, business-field view of workflow,
  lifecycle, approved artefact/version, review PDF, draft communication,
  commercial inputs, evidence summary, approval and delivery state;
- `action_preview`: a fully resolved simulation email using the approved draft
  and existing polished PDF;
- `execute_action`: an authenticated Telegram decision boundary requiring the
  exact preview `action_digest`.

The digest covers recipient routing, subject, full body, attachment checksum,
source workflow/run and artefact version. Execution recomputes it before send,
uses it as Gmail's idempotency key, records verified evidence on the workflow,
and suppresses retries. For KatKin the routing is explicitly
`simulation_mode=true`, `intended_client=KatKin`, and
`delivery_override=hello@narratiive.com`. The override is not written to client
identity or CRM state.

Safe reads now require an explicit read operation. Bounded Gmail, Drive and
Notion search paths return source evidence with `read_only=true` and
`mutation_count=0`. Mutation-shaped target fields are rejected at the runtime
boundary, and send/create/update/delete/share/move/publish language remains
approval-gated.

## Acceptance matrix

| Capability | Repository evidence | Live status |
| --- | --- | --- |
| Authoritative artefact detail | checksum and lineage tests | resolved against preserved KatKin run |
| Full proposed communication | workflow preview test | resolved from KatKin artefact |
| Gmail/Notion/Drive reads | classification and adapter regression tests | verified read-only; zero mutations |
| Writes remain governed | policy/runtime regression tests | existing gate retained |
| Complete simulation preview | digest-bound preview test | Tony resolved digest `5bc74c0a…89c7a`; not dispatched |
| Correct polished PDF | PDF checksum/attachment test | resolved to eight-page review PDF |
| No CRM contamination | workflow-state assertion | no override recorded as client email |
| Conversational approval | authenticated workflow operation | pending Matt decision |
| Exactly-once Gmail delivery | send/replay regression test | pending Matt decision |
| Proactive completion report | control-plane response contract | pending Matt decision |
| Restart/retry idempotency | persisted receipt replay test | pending Matt decision |

No KatKin person, address or domain has been contacted. The live acceptance
must stop at the resolved preview until Matt explicitly approves that exact
simulation action.

## Live evidence

After deployment, the workflow HTTP control returned the approved artefact and
complete preview from the preserved run. OpenClaw Tony session
`e8ce9a72-f36b-444d-b207-05900de42b7d` independently called workflow control,
reported the recipient override, subject, eight-page PDF, artefact/version,
simulation status and pending digest, and explicitly reported that nothing was
dispatched. All tool calls completed without failure.

Bounded live searches returned verified `read_only=true`, `mutation_count=0`
evidence for Gmail, Notion and Drive. Gmail found the known KatKin internal
review message IDs `1a0a8c1ea972b72f` and `1a0a8a2cf5caa54d`; Notion and Drive
returned valid zero-result searches. No CRM/client record was mutated, and the
simulation override remains absent from KatKin identity data.
