# Executable Fieldwork proposal v4.1 — Pass 1

This is the approved 4 November v4 production kit brought into Narratiive OS.
The authorising task is Matt's 5 November 2026 handover, Pass 1. It approves
implementing the supplied two-page Fieldwork reference, not a new design,
commercial approval, client release, or alteration of the canonical Origin run.

`approved_layout_source.py` is the unchanged supplied source for audit only;
do not import/run it (it contains the original standalone output path).
`layout.py` preserves its drawing geometry, hierarchy, fonts and image treatment
with input-bound text, palette, imagery and overflow callbacks. `reference.pdf`
is the approved reference with SHA-256
`3dc801365e80af0261d93b26721dfbc3deaa634a3676d5a219ab66c8b8a0d504`.
The original specifications and approval records are historical reference
material: their relative links/standalone paths describe the original kit.
This README describes the executable integration state.

## API and input

`runtime.fieldwork_proposal.render_fieldwork_proposal(data, *, asset_root,
font_dir=...)` returns `RenderedFieldworkProposal` containing PDF bytes,
SHA-256, template version and validation/lineage manifest. It performs no
workflow writes, communications, approvals or paid calls. Pass 1 produces only
internal review candidates. No proposed fee is approved by rendering.

`origin-fictional.json` is the complete input shape and fictional example,
not default text for another client. All fields are explicit. Supply client and
workspace identities, narrative copy, three evidence title/body pairs and source
notes, three output title/body pairs, palette and five image records. Existing
copy keys name their section, not their position in a generic page builder.
Client name placeholders are `{client_name}`, `{client_short}`, `{client_upper}`.
Only `<br/>` markup is accepted. Copy exceeding the reference text boxes is
rejected; no automatic font shrinking or new pages are allowed.

Image keys are stable slot IDs inherited from the reference filenames, not a
requirement to use Origin images for another client. Each record supplies a
path relative to the explicitly bounded `asset_root`, crop anchor, provenance
and status. Distinct decoded images are required; near-duplicate crops, rights,
relevance and strategic quality still require visual/human review.

The central opportunity, sensitivity, formula and limitations are derived from
`commercial_model` (conservative/central/upside account counts and year-one ramp,
whole-pound annual account revenue). Ramp uses whole percentages. The five
corresponding `copy.model_*` display fields are reference documentation and
are always replaced by these calculated values. This initial renderer supports
the supplied illustrative account-revenue mechanism, not arbitrary financial
models. The proposed GBP fee excluding VAT similarly determines `fee_display`;
its supplied display text cannot override the structured amount. `approved`
must be false. Real release, supported-model alternatives, terms/approval
binding and workflow quality checks belong to Pass 2.

The exact Baskerville/Arial font files are required and verified against
`font-checksums.json`. Mac defaults use `/System/Library/Fonts/Supplemental`;
other hosts must provide authorised identical files using `font_dir`.
Fonts are not redistributed, and there is no substitute-font fallback.
Existing ReportLab/Pillow/pypdf dependencies are sufficient. The manifest records
font, image, input and template-file hashes, page count, measured paragraph
boxes, notices and explicit `release_authorised: false`. Its validation does
not claim source verification, commercial approval or image-rights approval.

## Reproduce the internal example

From the repository, using a new output directory:

```bash
.venv/bin/python scripts/render_fieldwork_proposal.py \
  --input templates/fieldwork/v4/origin-fictional.json \
  --asset-root templates/fieldwork/v4 \
  --output /tmp/fieldwork-origin-review
```

The output bundle contains `proposal.pdf`, `input.json`, and `manifest.json`.
Existing output directories are refused. Identical inputs/fonts/assets produce
identical PDF bytes. The PDF checksum differs from the reference because its
metadata is deterministic; the approved appearance is preserved.

Focused verification:

```bash
.venv/bin/python -m unittest tests.test_fieldwork_proposal tests.test_human_review_artifacts -q
```

Font-dependent render tests skip explicitly on hosts without the approved Mac
fonts; validation/path/isolation tests still run. Local Mac visual comparison
is required in addition to CI.

## Workflow integration

Pass 2 connects this unchanged rendering API to the existing Proposal workflow,
quality checks, immutable review store, email draft and separate approval gates.
See `docs/operations/fieldwork-proposal-review.md` for the executable contract.
The renderer itself remains pure authoring: no approval, communication or
workflow persistence occurs inside it.

Owning stream: Worker Infrastructure. Affected stream: Delivery Engine
(`templates/fieldwork/v4`). Legacy workflow IDs are preserved.
