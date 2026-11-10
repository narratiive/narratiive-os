# Sketchbook client email preparation

This bounded adapter prepares a warm client-addressed Sketchbook email draft. It
does not send email, release a protected document, start production or change
payment state.

## Supported boundary

The source run must be the completed, approved
`campaign_world_to_creative_bible` run and must contain Matt's exact
`creative_bible_approval` checksum. This adapter does not reopen that run. The
generic document-handback adapter remains restricted to a blocked final
preparation stage and is not a Sketchbook adoption route.

Use `sketchbook_email_preview` with the exact run plus:

- workspace and client identity;
- Sketchbook title and version;
- the approved Creative Director's Bible checksum;
- a review PDF and native editable PPTX, each supplied as bounded file bytes;
- a passed visual-QA bundle bound to both file checksums, including evidence
  lineage, overflow, legibility and page-count checks;
- the verified intended recipient and recipient evidence reference;
- approved client-facing summary fields, the next step and sender identity;
- the selected engagement's actual release-condition status and evidence;
- optional public HTTPS booking and review links.

The operation writes an immutable, content-addressed presentation candidate and
returns the intended recipient, subject, equivalent HTML/plain-text bodies,
attachment identities, exact action digest and current send blockers. It creates
no Gmail draft.

Use `prepare_sketchbook_email_draft` only after reviewing that exact preview. It
requires Matt's authenticated identity, rationale, the candidate ID, its action
digest and OpenClaw's single-use native approval. It records a separate
`sketchbook_presentation_approval` and asks the existing Gmail adapter to create
one unsent draft addressed to the intended client. Gmail must read the draft
back and verify its recipient, subject, plain text, HTML and attachments before
Tony may call it ready. The idempotency key suppresses duplicates across retries.

## Release and send boundary

Unknown or unsatisfied commercial release conditions do not prevent internal
draft preparation, but they withhold protected review links. This adapter has no
send operation. Changing the recipient, subject, body, document version,
attachment or release evidence changes the digest and invalidates the prior
draft approval.

A real client send remains blocked until a supported Sketchbook client-delivery
operation exists and separately verifies:

1. exact-message approval for the recipient, subject, bodies, links and file
   versions;
2. the selected engagement's applicable commercial release conditions;
3. provider message/thread evidence and restart-safe reconciliation.

Do not substitute the Growth Blueprint client-delivery service or a raw Gmail
write. Do not infer payment terms from Fieldwork or treat content approval as
send, production, publication or media authority.

## Internal verification

Use fictional clients and `.test` recipients with a fake Gmail dispatcher for
engineering tests. Do not create live drafts for Rave or Origin. Inbox rendering
outside the generated desktop/mobile HTML preview remains unverified until a
separate compatibility test is run in supported email clients.
