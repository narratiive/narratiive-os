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
