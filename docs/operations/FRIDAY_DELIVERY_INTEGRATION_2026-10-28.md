# Friday delivery integration — 28 October 2026

Target: Friday 30 October 2026, close of business, Europe/London.
Status: integration rehearsal; not deployed or approved for client use.

## Founder decision and product compatibility

In the current engineering chat Matt confirmed: **“Use v7.1 for Friday;
preserve v4 history.”** The source is the [FIELDWORK v7 master with v7.1
amendment](https://docs.google.com/document/d/1KmY6uMSbdhGbl730bdXOPJh53nfhYjve6AVzexkXM1I/edit),
dated 22 October. This records the decision; it does not silently replace the
checksum-locked production bundle or approve any existing deck.

The v4 implementation's five-move opening and illustrative repeated 10% cohort
model are historical candidates. They cannot be presented as compliance with
v7.1. v7.1 requires the three-part market/brand/audience thesis, six-act depth,
four-to-five marketing levers, independently justified model inputs, actual
competitive advertising scrutiny and a concrete media/communications plan.
Missing first-party inputs must remain missing, not an invented forecast.

`runtime/fieldwork_v71_readiness.py` audits the structural review inputs only.
It never verifies a source, judges strategy, approves images, validates a final
render or releases work. It is an explicit operator preflight, not yet wired
into Tony's production quality gate. Older packages fail it. The production
contract/importer and specialist execution still need v7.1 adoption and review.

```bash
.venv/bin/python scripts/audit_fieldwork_v71_readiness.py <immutable-review-package.json>
```

## Branch integration

PR #497 preserves the existing branch history and combines the SKETCHBOOK v2 /
FIELDWORK v4 stack (#486/#485 and its earlier dependencies), Tony briefing and
journey naming/certification (#487/#492), inbound service routing (#493),
truthful execution status (#495), and queue fairness (#496).
These merged locally without textual conflicts. A clean Git merge is not
semantic compatibility, product acceptance or deployment evidence.
Mission Control UI work #494 remains separate from this delivery integration.

PR #492 was merged into `feat/tony-briefing-intelligence`, not `main`.
The inspected production branch was `412bbfd470bd233fc48697dc7d995392d384df44`.
Do not equate a merged stacked PR with production adoption.

## Governed demo journey

| Customer stage | Existing executable boundary | Evidence needed for demo |
| --- | --- | --- |
| GROUNDWORK | `growth_diagnostic_to_blueprint_lite` | One scoped intake, source-backed preparation, exact-version review gate |
| Discovery | `blueprint_lite_to_discovery_preparation` | Existing commissioned run attempts and substantive preparation; genuine notes for synthesis |
| Proposal | `discovery_evidence_to_growth_sprint_proposal` | Immutable proposal and founder scope/commercial decision; no automatic prospect send |
| FIELDWORK | Research → Strategic Synthesis → Strategy Thesis → Growth Blueprint → deliverable production | Approved thesis; fresh v7.1 specialist package, source/challenge register, model and visual review; exact-version founder decision |
| SKETCHBOOK | `sketchbook_v2_production`; existing Campaign World / Creative Director's Bible boundaries retained | Real renderer/importer configured; approved FIELDWORK ID/checksum; client manifest and specialist-authored pages; fresh quality and human review |
| LAUNCHPAD | Existing creative production planning, Production Pack, Asset Manifest and media gates | Approved creative direction and production plan, genuine provider receipts; publication/spend separately approved |

Do not invent a new LAUNCHPAD state machine or collapse the existing objects.
The SKETCHBOOK adapter is injected into the runtime but its availability in the
live process is unverified. Its example handoff label is not founder approval.
The existing golden-path certification uses synthetic callbacks and synthetic
test approvals; it explicitly does not certify Creative, Media, Measurement or
Client Operations. Never present that test as a live client journey.

## Retrieved KatKin work

The named live-brief run is
`katkin-growth-blueprint-deliverable-v5-canonical-handoff-r8`.
Its checked-in review material is under `outputs/katkin/production-v5/`.
The PPTX has 30 slides and 505 native text runs; the review PDF has 30 raster
pages. Both binary checksums and all twelve lineage entries match Git object
bytes. Windows checkout line-ending conversion changes JSON working-file
checksums; compare canonical Git bytes, never rewrite the historical manifest.
The recorded state is `awaiting_approval`; it was not reread from the Mac.
This is an older Growth Blueprint v5, distinct from the FIELDWORK contract v4
and the Friday v7.1 target.

Separate editable internal candidates exist in Drive:

- [FIELDWORK v4 — KatKin — 30 pages](https://docs.google.com/presentation/d/1qe5fQ88JmREI8Kpd7VppCYk28ZOnmQuWlLdlwTfMHDQ/edit)
- [SKETCHBOOK v2 — KatKin — five pages](https://docs.google.com/presentation/d/1XjD49DRZRNWSuIcV-SYKKoYwpUI19Y4kcMi4xZBi3Uw/edit)

Both were read back and have substantive content. They are internal candidates,
not approved v7.1 deliverables. Do not restart the older blocked KatKin strategy
run until its supersession/current-dependency relationship is read live.

## Mac execution handoff

No Mac host or live runtime connection was accessible from this Windows chat.
Matt is away from the Mac and could not identify the other Codex chat. No
runtime records were changed, no scheduler restarted and no client contacted.

On `~/Documents/narratiive-os`, the existing Mac session should first inspect
its branch, uncommitted changes, deployment receipt and ongoing workers. Do not
overwrite that session's work or deploy this draft integration branch.

1. Read the existing Loom Loft run
   `inbound-d1b96a67-blueprint_lite_to_discovery_preparation` through the public
   workflow boundary. If ready, use its governed continue operation, not a new
   commission. If already running, inspect ownership/failure evidence before
   recovery. Preserve history and tenant scope.
2. Inspect `com.narratiive.tony-conversation-worker` separately from bridge
   health. Compare workflow runtime root and resolved workspace tenant between
   bridge and worker without printing secrets. The installer already defines
   continuous KeepAlive worker execution and eight LaunchAgents; do not add a
   second scheduler. Queue fairness does not explain every unstarted run.
3. Verify Loom Loft reaches an immutable substantive document and human gate.
   Record path/checksum and attempt evidence. Do not contact Loom Loft.
4. Read the actual KatKin gate and exact current artefact checksum. Provide it
   for Matt review without approving it. Check the older blocked run separately.
5. After reviewable v7.1 production adoption, commission fresh internal specialist
   work with a new version and parent references. Advance to SKETCHBOOK only
   after the genuine exact-version human approval. LAUNCHPAD remains internal
   planning until its own creative/production and external-action gates pass.

## Release boundary and remaining decisions

Technical integration must pass Linux CI and independent exact-commit review,
including affected-stream product/architecture review, before merge. The broad
stack is not a substitute for reviewing its earlier constituent PRs.
Matt's v7.1 target decision is recorded; final strategy, creative and client
release approvals remain outstanding. Live importer configuration, actual
provider access and a timed supervised rehearsal are operational work, not
decisions to manufacture or delegate to a fixture.
