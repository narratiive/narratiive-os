# Growth Blueprint evidence architecture — implementation proposal
Status: proposed; no runtime or locked-canon changes. 2026-10-13.

## Principle
Every significant commercial claim, chart, audience insight and recommendation must be reconstructable from source records, transformations, assumptions and review decisions. A model response is not a source. Third-party estimates are not first-party performance data.

## Required typed objects
**Source**: source_id, publisher, source_url/document_id, retrieved_at, observed_period, geography, population, access_rights, reliability_notes, original_excerpt_or_table_checksum, client_id, workspace_id.
**Observation**: observation_id, source_id, metric, value, unit, numerator, denominator, time_period, sample, segmentation, method, coverage, caveats.
**Assumption**: assumption_id, metric, value, range, rationale, owner, date, validation_method, confidence, expiry.
**Calculation**: calculation_id, formula, version, input_ids, outputs, unit, rounding, checksum, validation_result.
**Claim**: claim_id, exact_text, claim_type (verified_client|verified_external|modelled|assumption|hypothesis|creative_illustration), linked_ids, confidence, limitations, review_state.
**Visual**: visual_id, claim_ids, calculation_ids, chart_type, axis_definition, base_population, source_caption, generated_at, editable_asset_ref.
**Decision**: decision_id, thesis, alternatives, supporting_claim_ids, disconfirming_claim_ids, expected_business_levers, owner, review.
Use existing Growth Object lineage and artefact catalog; do not create an ungoverned parallel datastore.

## Evidence pipeline
Intake and consent -> source acquisition -> immutable capture/checksum -> normalization -> entity and time-period resolution -> contradiction/coverage check -> commercial calculation -> claim register -> visual spec -> specialist peer review -> Matt's approval -> governed export.
No external send or publication without human approval. Persist source licence/redistribution restrictions.

## Evidence ladder
Tier 1: Client-owned CRM, analytics, ad platforms, transaction data (access and attribution validated).
Tier 2: Official registers, regulator/industry statistics, company disclosures.
Tier 3: Reputable panel/survey and licensed market intelligence (representativeness assessed).
Tier 4: Directional digital proxies: search, SEO visibility, estimated traffic, social listening, review mining.
Tier 5: Explicit modelling assumptions / strategic hypotheses.
Never silently promote Tier 4 estimates into verified revenue or customer counts.

## Required validations
- Currency, tax, gross/net revenue and periods consistent.
- Visits/sessions vs users distinguished; orders vs customers distinguished.
- Revenue bridge reconciles to known total; unknown channels called out.
- Conversion, AOV, CAC, ROAS and MER denominators explicit.
- Growth attribution separates independent levers and interaction effects.
- Baseline vs forecast vs ambition clearly separated.
- Scenarios specify downside/base/upside, costs, operational capacity and margin.
- Each chart can be regenerated from linked table/calculation.
- Every decisive insight includes at least one possible disconfirming test.
- No invented market size, audience survey, customer quote or causal lift.

## Delivery artifacts
research/source-register.csv; research/observations.csv; research/assumptions.csv; research/claim-register.csv; models/opportunity-model.xlsx; presentation/deck.pptx; presentation/review.pdf; quality/independent-review.md. Paths are illustrative desired deliverables, not a claim they exist in runtime.

## Acceptance
No unsourced hard numbers in the opening five slides; scenario arithmetic passes; clear confidence markers; founder can understand what data must be supplied next; reviewer can reproduce every displayed number.