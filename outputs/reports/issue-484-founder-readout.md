# Issue #484 — founder readout

Status: internal review complete; draft PRs only. Nothing merged, deployed, sent to a client or activated.

## What changed

FIELDWORK v4 now has a typed five-move opening, cohort-revenue model, evidence/assumption validation, rendered-pixel QA and a fail-closed native Google Slides handoff in Tony's deliverable path. SKETCHBOOK v2 now has a typed client-independent population contract, registered Tony workflow/capability, exact FIELDWORK lineage, client design manifests, a reusable editable renderer, native Slides/PDF delivery and a human approval stop.

## What the products show

FIELDWORK opens with: commercial position today; 12-month opportunity; sources of gain; audience opportunity; strategic direction. The KatKin example then extends the same argument through the 30-slide master.

SKETCHBOOK shows: creative proposition; audience portrait; visual world; campaign territory; executions/applications. Rave and KatKin use the same typed page system but have different strategy, copy, palettes, imagery, territories and applications.

## Commercial and evidence integrity

The KatKin model is an explicitly illustrative index because first-party baselines were unavailable: 1.10 qualified visits × 1.10 first-purchase conversion × 1.10 realised revenue per acquired customer = 1.331, or index 133 / +33.1%, for the modelled new-customer cohort only. Existing-customer revenue is excluded. It is not a total-company forecast and does not claim contribution or profit.

FIELDWORK citations resolve to the governed K1–K9/T1 register. SKETCHBOOK audience statements and concepts are labelled as hypotheses or illustrations; no customer quote, live interaction, operational timestamp or performance result is asserted.

## Execution proof

- FIELDWORK: 30 rendered pages inspected; package/layout/OCR QA passed; native Slides import verified at 30 pages.
- SKETCHBOOK: all 10 rendered pages inspected at 1280×720; both five-page PDFs assembled; native Slides imports verified at five pages each.
- Test suite: 1,792 tests passed. The three initially failing lifecycle tests used retired FIELDWORK v3 fixtures; those fixtures were migrated to v4 and the suite reran green.
- Actual: repository generation, PPTX/PDF rendering, AI concept image generation, Google Drive conversion and Slides outline verification.
- Simulated: provider callbacks inside unit/e2e tests. No Mac Mini deployment or live Tony process mutation was attempted.

## Founder decisions

1. Approve or revise the KatKin FIELDWORK commercial argument and indexed model boundary.
2. Approve or revise the Rave and KatKin SKETCHBOOK creative territories and image direction.
3. Approve the stacked branch strategy and runtime importer wiring before merge/deployment.
4. Decide whether to commission first-party KatKin baselines and audience validation before any client-facing release.
