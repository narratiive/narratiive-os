# Issue #477 — Rave FIELDWORK quality pass

This evidence pack replaces fictional LOA as the strategic-quality benchmark. It is an internal, unsolicited Rave Coffee exercise and is not approved for external release.

## Review first

- `prompt-chain-audit.md` — where quality deteriorates and the smallest proposed repair.
- `side-by-side-quality-assessment.md` — historic Claude benchmark vs controlled direct Claude vs current Tony route.
- `five-slide-opening/FIELDWORK-Rave-five-slide-opening-v3.pdf` — designed review opening.
- `five-slide-opening/FIELDWORK-Rave-five-slide-opening-v3.pptx` — editable review opening.
- `five-slide-opening-storyboard.md` — plain-text opening and evidence boundary.

## Reproducible evidence

- `identical-rave-research-pack.json` — frozen input used in both controlled calls.
- `direct-claude-five-slide-opening.json` — raw direct commission.
- `tony-pipeline-strategic-draft.json` — raw current Tony commission.
- `comparison-execution.json` — model, message IDs, input hash and no-external-action record.
- `source-provenance.json` — Drive source IDs and hashes.
- `quality-test-plan.md` — proposed acceptance tests for the argument gate.
- `duplicate-cleanup-audit.json` — reversible duplicate-test cleanup result.

## Verification

- Full repository suite: 1,793 tests passed on 17 October 2026.
- Focused workflow suite: 78 tests passed.
- Both Python operator scripts compile.
- Presentation finalisation: five slides; package integrity, layout, font policy and first-party import passed with no findings.

## Remaining blocker

The two duplicate Notion pages were archived and the corrected page was preserved. Three Gmail duplicate test messages were safety-matched but could not be moved to Trash: the current OAuth grant has read, compose and send, but not `https://www.googleapis.com/auth/gmail.modify`. No message was changed or sent. Adding that restricted scope requires Matt's explicit approval and Google reauthorisation; the alternative is a separately confirmed manual UI trash action.
