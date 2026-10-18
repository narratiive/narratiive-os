# FIELDWORK calibration validation evidence

## Live specialist execution

| Business | Run | Provider message | Quality | Workflow state | External action |
|---|---|---|---|---|---|
| Rave Coffee | `rave-fieldwork-calibration-20261018-v3` | `msg_011CgAPgTC7bhHffZS1e61yy` | passed | awaiting approval | none |
| KatKin | `katkin-fieldwork-calibration-20261018-v1` | `msg_011CgAPmtqcDQewkBmvd2ZKh` | passed | awaiting approval | none |
| The Yardstick Agency | `yardstick-fieldwork-calibration-20261018-v1` | `msg_011CgAPra1AchtFmGkSzvecn` | passed | awaiting approval | none |

Each case retains the accepted founder argument, quality result, execution receipt and public research ledger. The runtime reported `presentation_production_triggered=false` and `external_action_taken=false` for all three commissions.

## Rave fail-closed audit

- `v1` reached the independent gate but was rejected. The specialist returned two collection fields as strings, and the currency-token parser treated punctuation as part of a supported price. The rejected runtime artefact remains in the local immutable runtime store and was not promoted.
- The candidate response contract now explicitly requires lists for growth levers, known inputs and missing inputs.
- The financial parser now recognises supported currency values adjacent to punctuation without swallowing that punctuation.
- Regression tests cover both behaviours.
- `v2` stopped before dispatch with `worker_unavailable:strategic_reasoning` because the protected runtime environment had not been loaded. No provider call or artefact occurred.
- `v3` loaded the protected runtime environment, passed every strict check and stopped at human approval.

## Presentation validation

- Three editable PowerPoint files were finalised with five slides each.
- Package integrity, declared 16:9 slide size, font policy and Artifact Tool re-import checks passed.
- All 15 authored slides were visually inspected from the render set.
- All three PDFs contain five 16:9 pages and were rasterised and visually inspected after conversion.
- Speaker notes retain evidence IDs, classifications and public source URLs.
- No native chart or table was required; the commercial mechanisms are editable text and shapes rather than invented quantitative graphics.

## Regression validation

- Focused workflow suite: 64 tests passed.
- Full repository suite: 1,781 tests passed.
- Presentation overflow check: passed for all three editable decks.
- Repository diff whitespace check: passed.

## Remaining human validation

Matt must decide whether each argument is commercially strong enough to advance, whether the Rave design continuity is correct, and whether the opt-in contract should be used in a supervised paying-client rehearsal. No recommendation has been approved for external use.
