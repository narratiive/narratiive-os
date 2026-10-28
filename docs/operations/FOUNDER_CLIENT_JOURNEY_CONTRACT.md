# Narratiive founder-facing client journey — implementation contract (draft)

Status: proposed product contract, **not** deployed or certified. Keep existing canonical workflow identifiers, evidence, quality gates, and audit trail. No real outreach in synthetic tests.

## Founder-facing stages
1. **GROUNDWORK** — initial diagnostic, triage and short review card. No fabricated prospect identity.
2. **Discovery** — internal preparation (not evidence that a call occurred), then a real 20-minute call where authorised; record actual transcript/notes, attendees, source and unanswered questions. A synthetic test may use explicitly labelled simulation evidence, never misrepresented as a real call.
3. **Proposal** — within 30 minutes of completed call, generate a standard, branded, editable scope proposal with personalised evidence summary, workstreams, deliverables, timing, price, assumptions and dependencies. The 30-minute target is a service-level objective, not a guarantee. Send only to verified prospect after founder-approved external action.
4. **FIELDWORK** — only after verifiable commercial acceptance; orchestrate specialist research, synthesis, strategy and source verification internally, produce substantive editable presentation and review PDF, stop for founder quality approval.
5. **SKETCHBOOK** — from approved FIELDWORK, run creative-world and creative-bible work internally and generate visual editable creative presentation, stop for founder quality approval.
6. **LAUNCHPAD** — execute only separately authorised external creative/media actions with spend, publishing and delivery controls.

## Gates: only three founder-facing decisions where possible
- Approve internal qualification/discovery readiness (one compact card, not a four-page signoff).
- Approve commercial proposal and **external send**; client acceptance must be evidenced before FIELDWORK.
- Approve FIELDWORK and SKETCHBOOK deliverables before consequential use. These are distinct creative/strategy quality gates, presented together where safely possible.

Internal machine transitions should not require repeated founder commands. Never collapse externally consequential approvals or manufacture call, contract, payment, or acceptance evidence.

## Discovery review card
One screen: company, status (test/verified), diagnostic score with transparent dimensions and **calibrated** suggested threshold (no arbitrary automatic accept/reject), three key strengths, three growth challenges, up to five call questions, evidence gaps, recommended next action and one approval control. Full evidence remains accessible as an appendix, not mandatory founder reading.

## Real-world sequence and integrations
- Inbound lead -> qualified/verified identity -> scheduling invitation with available slots based on calendar availability; do not imply a meeting exists until calendar booking is confirmed.
- Call -> Fireflies transcript when available and consent/permissions appropriate; otherwise sourced meeting notes. No call evidence means proposal can be prepared as a draft only, not asserted as post-call.
- Proposal: render templated scope with personalised call summary, internal PDF/PPTX preview and **configurable private internal-review email**; never hard-code a founder's personal address in this public repository.
- Founder approval -> send from explicitly selected authorised Gmail account to verified prospect, with idempotent send receipt and failure reporting. **Internal review email is not prospect email.**
- Prospect reply -> ingest via Gmail thread/message identifiers; classify accept/decline/question/ambiguous; require verifiable acceptance of exact version/scope/price. Ambiguous reply stays human-review. Don't infer acceptance from silence or booking.
- Accepted proposal -> FIELDWORK orchestrator with quality, provenance, native presentation import and visual QA, then founder review; approved FIELDWORK -> SKETCHBOOK.

## Acceptance criteria
1. Synthetic Loom Loft can progress from approved Discovery preparation to a **draft** proposal without inventing a completed call, contacting a real company, or bypassing required discovery evidence.
2. A separate consented real-world fixture proves booking, meeting evidence ingestion, proposal rendering, internal review delivery, approved external send, reply correlation and acceptance detection.
3. Approved scope starts FIELDWORK specialist execution once, preserves lineage, and delivers a substantive editable deck + PDF to a founder gate.
4. Approved FIELDWORK launches SKETCHBOOK generation once, yields an editable visual deck, and stops at its review gate.
5. Every displayed status distinguishes commissioned, queued, executing, blocked, awaiting approval and completed with verified artifact links.
6. Regression and live acceptance checks demonstrate actual provider calls, artefacts, email receipts and failure recovery; fixture-only green tests are not live proof.

## Current observed gaps (2026-10-28)
- Loom Loft Discovery preparation complete, awaiting founder approval; **no actual call**.
- Existing internal-review service restricts recipient to an existing allowlisted agency address; configure and verify a secure private-review recipient separately.
- KatKin Growth Blueprint r8 exists as editable PPTX and PDF, awaiting founder review; not proof of FIELDWORK v7.1 production wiring.
- SKETCHBOOK and native Slides import not live-configured; draft PRs are not production approval.
- Codex is separately working on live runtime: avoid duplicate work or overwriting its worktree.


## Founder interaction contract — short, contextual and unambiguous
- Founder may say **"Loom Loft is approved for Discovery"**, **"Approve that proposal"**, or **"What's next?"**; Tony resolves intent against the current authoritative client/run and pending gate internally. IDs, checksums and approval tokens remain in persisted machine evidence, **never required in normal founder messages**.
- Where exactly one current gate matches, show a one-sentence human summary and execute the correct governed approval. If two gates or versions plausibly match, ask **one short disambiguating question** with plain-English choices. Never guess or bypass cryptographic approval binding.
- If a gate requires a formal token, Tony retrieves/binds it internally; no founder copy-paste. Preserve actor identity and an auditable record of the exact approved version.
- Responses default to: **what changed / what matters / what happens next**. Maximum ~3 short sentences for routine updates. Technical details and IDs only on explicit request or in expandable diagnostics.
- Morning/evening briefs: max three genuinely material items, ordered by founder action or delivery risk; omit low-priority stage chatter, repeated statuses, irrelevant run IDs and generic "operational" reassurance. Zero-material-update brief is one sentence. Include a real deliverable link only when relevant.
- Email summaries: 2–4 lines, not a copy of the attachment. Keep full reasoning in the review artefact.

## Synthetic end-to-end prospect rehearsal — distinct from production
- Test prospect **mattfranks@outlook.com** is an explicitly designated *external correspondence test recipient only*, never an internal-review, approvals or alert inbox. Store in private test configuration, not public fixtures or defaults.
- Founder authorises a bounded test email from the real Narratiive Gmail account to this address; invitation contains a short explanation, live bookable options or scheduling link backed by Google Calendar availability, and a clear synthetic-test marker.
- Prospect books an actual 10–20 minute meeting. Confirm event/calendar invite, organiser/attendee and joining link; verify scheduling conflict handling.
- Run a **real recorded simulation call** with consenting test participants and Fireflies where available. No invented transcript. Verify the recording/transcript is attached to the correct client and event. Check provider permissions, consent, and ingestion lag; **3–4 minute turnaround is a performance target, not guaranteed**.
- Generate proposal with a reusable core and call-derived, source-labelled personalisation. Aim to send within 30 minutes of the call; first send needs founder approval and external-action authorisation.
- Prospect receives proposal, replies from Outlook, Gmail thread is ingested, exact version and scope are correlated; test acceptance and ambiguous-response handling. Synthetic acceptance may initiate **internal test FIELDWORK only**, never a real contractual obligation.
- Log timestamps for invite send, booking, call end, transcript availability, proposal generation, email send, inbox receipt, reply ingestion, acceptance and FIELDWORK execution. Each stage must have independent proof.
- Stop on any provider, permission, consent, or real-world send gate; do not silently replace Fireflies or calendar integrations with fixtures and claim success.
