# Issue 477 — founder review report

Date: 19 October 2026

Status: internal candidate work; nothing merged, deployed, sent or published.

## Review first

Private Drive folder (owner-only permission verified):
[INTERNAL REVIEW — FIELDWORK + SKETCHBOOK — 2026-10-19](https://drive.google.com/drive/folders/1o3q4sezkdLRxlElHqWgD7eIvAdAbEG_U)

### SKETCHBOOK

- [Rave SKETCHBOOK — Google Slides](https://docs.google.com/presentation/d/1CK-KCl7slXQtC41XaWxsQOLMXk9qRB5FNPI3H-g-OJI/edit)
- [Rave SKETCHBOOK — review PDF](https://drive.google.com/file/d/10OMCoqnaV20Jy0p1HKdy2-5KoRzWXv6n/view)
- [Rave SKETCHBOOK — editable PowerPoint](https://docs.google.com/presentation/d/1DqOUvZGdg-DrFOqUCyxicXb9hyzVtsd7/edit)
- [Machine-readable template specification](https://drive.google.com/file/d/1w22C6hQlRN6rgBUAStfNSToM-778nox4/view)
- [Visual QA report](https://drive.google.com/file/d/1FnU6l7_xCfBG0pROAd0Vl2VlAz6iJOSU/view)

### FIELDWORK

- Rave: [Google Slides](https://docs.google.com/presentation/d/1hTBhC4mWvwsHRPbUw5ijL7RvB5RPQawddPauehUou2c/edit) · [PDF](https://drive.google.com/file/d/1R6KsdMbXN77yyUo89g79KCupMwb1Q3r6/view) · [PowerPoint](https://docs.google.com/presentation/d/12PWuMt4xUBGCY5XdeON-x8HZXRsbCC-o/edit)
- KatKin: [Google Slides](https://docs.google.com/presentation/d/1zUH0sMu3OApt8XKFP1fcY9S_lPNAMxeQqCXwnrT--lo/edit) · [PDF](https://drive.google.com/file/d/1KfowYbqI55BqvwC1suyA-zslJZGri_WT/view) · [PowerPoint](https://docs.google.com/presentation/d/1nHc1lFbXdCUYyGSGD8_1tRFdYIf4of95/edit)
- The Yardstick Agency: [Google Slides](https://docs.google.com/presentation/d/1Fkebr7FMGZiAdTBKhthCwWBOg7sEGyG5qy8MJTyJRRU/edit) · [PDF](https://drive.google.com/file/d/1MK-ttyDSyZB9C3i724rKilyLl27Hvta-/view) · [PowerPoint](https://docs.google.com/presentation/d/1UE1tr9IlhFqKCaisnTR4G9gQvYUuRFPP/edit)
- [Three-business comparison](https://drive.google.com/file/d/1VnhQ7UDPdYKdM-J30Qgi_TMS6PkYTKDb/view)
- [Editorial and visual scorecard](https://drive.google.com/file/d/10WVyvkK39Rl0o7O03iZ1RAz-GJ3dPfQU/view)
- [Candidate production contract](https://drive.google.com/file/d/1VGeibitZKg1pG9lQ_lLmqoYW5p8sPIqF/view)
- [Client design-system specification](https://drive.google.com/file/d/1sHlS-8-bAcK2pSUsTX8zD2IF2jD_9fd_/view)

## What was completed

1. Built the five-page Rave SKETCHBOOK candidate as finished examples: creative
   proposition, audience profile, visual world, campaign territory and campaign
   applications.
2. Preserved the original Campaign World V3 content boundary. The Upgrader,
   creative copy, delivery timestamp and quiz behaviour remain hypotheses or
   creative illustrations rather than current verified claims.
3. Defined a deterministic template contract: exact geometry, fields, type
   hierarchy, copy limits, image/crop rules, variants, overflow, missing-content
   behaviour and visual checks. Tony can populate it without redesigning it.
4. Completed FIELDWORK calibration across Rave, KatKin and The Yardstick Agency
   with explicit evidence/assumption registers and comparable editorial/visual
   scores. All three remain at the human gate; no full presentations were made.
5. Split the work into focused draft PRs while retaining #478 as the audit record.
6. Delivered editable sources, fixed PDFs and native Slides to a restricted Drive
   folder. The first attempted product-folder location inherited link-readable
   access; the folder was moved to an owner-only parent and permission readback
   now reports `shared=false` with only `hello@narratiive.com` as owner.

## What was tested and verified

- Rave SKETCHBOOK package integrity, slide size, layout, heading fit and Arial
  font policy: pass with zero findings.
- Five of five SKETCHBOOK PDF pages visually inspected.
- Native Slides conversion: all four decks contain five slides and preserve the
  expected titles, text, evidence labels and approval gates.
- Template regression tests: 4 passed.
- Repository suite on the SKETCHBOOK branch: 1,785 passed.
- FIELDWORK focused workflow tests after the register/score update: 53 passed.
- GitHub CI: #478, #479, #480 and #481 all pass `validate-runtime`; every PR is
  still draft and unmerged.

## Three-business result

| Business | Clarity | Commercial usefulness | Distinctiveness | Presentation | Central decision |
| --- | ---: | ---: | ---: | ---: | --- |
| Rave | 5/5 | 4/5 | 4/5 | 4/5 | Prove one progression from first choice to repeat and discovery. |
| KatKin | 5/5 | 4/5 | 4/5 | 4/5 | Build a trial/transition/early-feeding decision system before scaling spend. |
| Yardstick | 4/5 | 4/5 | 4/5 | 4/5 | Validate a change-point diagnostic entry route against pipeline and account data. |

The candidate consistently protects one coherent argument, evidence boundaries
and a founder decision. It does not yet prove willingness to pay, equivalence to
the original Rave benchmark's creative surprise, or effectiveness with real
first-party commercial data.

## Design-system finding

The recognisable Narratiive layer should be structural: sharp editorial hierarchy,
one claim per page, visible evidence status and a repeated path motif. The client
layer should control colour, photography, cultural codes, metaphors and execution
style. For Rave, the successful bridge is warm domestic morning photography,
black/cream fields, Rave Yellow and plain direct language. SKETCHBOOK can use the
same tokens more expressively without becoming a FIELDWORK template clone.

## Focused draft PRs

- [#479 — operational reliability and idempotency](https://github.com/narratiive/narratiive-os/pull/479): green, mergeable, unmerged.
- [#480 — FIELDWORK founder-argument candidate](https://github.com/narratiive/narratiive-os/pull/480): green, mergeable, unmerged. Latest commit adds evidence registers and scoring.
- [#481 — SKETCHBOOK canonical template candidate](https://github.com/narratiive/narratiive-os/pull/481): green, mergeable, stacked on #480, unmerged.
- [#478 — complete audit record](https://github.com/narratiive/narratiive-os/pull/478): retain as audit history; do not merge as one release.

Proposed review order is #479, #480, then #481. Deployment, if later approved,
is a separate action. Rollback instructions are recorded in the focused release
sequence; none of these candidates changes a production default.

## Human judgement and decisions required

1. Approve, revise or reject each FIELDWORK founder argument. Do not commission a
   full deck until the corresponding five-slide opening is strong enough.
2. Decide whether the founder-argument contract should proceed to one supervised
   paying-client rehearsal; keep it opt-in until then.
3. Approve or revise the Rave SKETCHBOOK creative north star and the five canonical
   page types. Comparative copy still requires product/legal review before use.
4. Confirm whether repository retention of editable decks and PDFs is desired
   before considering #480 or #481 for merge.
5. Obtain exact-commit independent review for each focused PR. Passing CI is not
   a substitute for review.
6. Separately decide any production deployment. No deployment, client contact,
   media activation, spend or release was attempted.

## Remaining blockers

- First-party commercial/customer data is unavailable for all three exercises;
  opportunity mechanisms remain scenarios, not forecasts.
- No eligible independent reviewer has yet approved the exact focused commits.
- Client-facing use remains blocked by the exact-version human approval gate.
- The broader Issue #477 commercial-close and activation integrations retain the
  blockers already recorded in #478; this development pass did not claim them as
  live or resolved.
