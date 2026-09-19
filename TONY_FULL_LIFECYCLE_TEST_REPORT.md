# Tony Full Lifecycle Test Report

Test client: **Northstar Test Co**

Scope: isolated synthetic workspace `northstar-test-workspace-e2e` and client `northstar-test-co-e2e`

Repository architecture source: `runtime/workflow_registry.py` and the existing workflow runtime, state machine, repositories, worker registry, quality validators and Tony runtime application service

Production records modified: **none**

## Executive result

**Overall: PASS — the native continuous lifecycle reaches the terminal delivery/next-action gate.**

All 11 registered gates pass contract/state-machine conformance with isolated run IDs and deterministic synthetic workers. The native handoff chain now uses bounded deterministic downstream identities and reaches `delivery_to_follow_up_next_action`. Campaign World, Creative Bible, Production Pack, creative production, exact asset-suite approval, delivery packaging, receipted client delivery and bounded performance follow-up are exercised through their production validators.

Default live operation remains deliberately fail-closed where an external provider is absent: creative production and client delivery require configured adapters plus explicit external-write approval. Local Production Pack and delivery-package preparation remain available without external writes.

## Canonical gate architecture discovered

1. `growth_diagnostic_to_blueprint_lite`
2. `blueprint_lite_to_discovery_preparation`
3. `discovery_evidence_to_growth_sprint_proposal`
4. `growth_sprint_to_research_engine`
5. `research_to_growth_blueprint`
6. `growth_blueprint_deliverable_production`
7. `growth_blueprint_to_campaign_world`
8. `campaign_world_to_creative_bible`
9. `creative_bible_to_asset_production`
10. `asset_review_to_delivery_preparation`
11. `delivery_to_follow_up_next_action`

The chain was read from each workflow's existing `next_workflow_id`; no parallel workflow was invented.

## Per-gate result

| # | Gate | Contract/state test | Current default operational readiness | Elapsed | Resulting state | Worker / artefact |
|---:|---|---|---|---:|---|---|
| 1 | `growth_diagnostic_to_blueprint_lite` | PASS | PASS when Claude is configured | 3.574 ms | `awaiting_approval` / `pending` | `northstar-test-fixture-worker`; `artifact-3c5ca75cfc0e9bc0-78bd272963ee5819` |
| 2 | `blueprint_lite_to_discovery_preparation` | PASS | PASS when Claude is configured | 4.674 ms | `awaiting_approval` / `pending` | `northstar-test-fixture-worker`; `artifact-4e6c24e78bca5785-eb2c1d85d517ca90` |
| 3 | `discovery_evidence_to_growth_sprint_proposal` | PASS | PASS when Claude is configured | 5.101 ms | `awaiting_approval` / `pending` | `northstar-test-fixture-worker`; `artifact-c07129c3b50f6fb2-337af6082c7a632f` |
| 4 | `growth_sprint_to_research_engine` | PASS | PASS for approved readable sources | 4.804 ms | `complete` / `not_required` | `northstar-test-fixture-worker`; `artifact-47460bebb1cc26ca-7a71ac6e4af35d8a` |
| 5 | `research_to_growth_blueprint` | PASS | PASS when Claude is configured | 6.021 ms | `awaiting_approval` / `pending` | `northstar-test-fixture-worker`; `artifact-b618c71759b0450c-ba13080bc261e590` |
| 6 | `growth_blueprint_deliverable_production` | PASS | PASS with local renderer dependencies; human release approval required | 6.975 ms | `awaiting_approval` / `pending` | `northstar-test-fixture-worker`; `artifact-7bb9e3fcb74ad983-57bbad91f90268d8` |
| 7 | `growth_blueprint_to_campaign_world` | PASS | PASS with configured Claude; exact Matt selection required | 30–40 ms | `awaiting_approval` / `pending` | generation + Tony triage; immutable candidate artefacts |
| 8 | `campaign_world_to_creative_bible` | PASS | PASS with configured Claude; exact Matt Bible approval required | 30–40 ms | `awaiting_approval` / `pending` | generation + Tony triage; immutable Bible artefacts |
| 9 | `creative_bible_to_asset_production` | PASS | Local planning PASS; provider execution blocks safely when unconfigured | 30–45 ms | `awaiting_approval` / `pending` | `northstar-test-production-planner`; Production Pack + 18-version suite evidence |
| 10 | `asset_review_to_delivery_preparation` | PASS | Local packaging PASS; delivery blocks safely when provider unconfigured | 35–50 ms | `awaiting_approval` / `pending` | `northstar-test-delivery-preparer`; exact delivery package + receipt evidence |
| 11 | `delivery_to_follow_up_next_action` | PASS | PASS — local read-only performance/iteration plan; human strategy authority retained | 35–50 ms | `awaiting_approval` / `pending` | `northstar-test-follow-up-planner`; immutable next-action artefact |

Elapsed times are from one local isolated deterministic run and are evidence of test execution, not provider-performance benchmarks.

### Inputs, validation and continuation by gate

| Gate | Required input state validated | Validation result | Explicit continuation |
|---|---|---|---|
| `growth_diagnostic_to_blueprint_lite` | `diagnostic_input_package` present | PASS — production Blueprint Lite quality gate | `/approve <run> because <rationale>; then /continue <run>` |
| `blueprint_lite_to_discovery_preparation` | `blueprint_lite`, `diagnostic_evidence`, `company_context` present | PASS — production Discovery preparation quality gate | `/approve <run> because <rationale>; then /continue <run>` |
| `discovery_evidence_to_growth_sprint_proposal` | `discovery_evidence`, `blueprint_lite`, `commercial_context` present | PASS — production Growth Sprint proposal quality gate | `/approve <run> because <rationale>; then /continue <run>` |
| `growth_sprint_to_research_engine` | approved scope, research requirements, approved sources and client context present | PASS — production research-evidence quality gate | `/continue <run>` |
| `research_to_growth_blueprint` | evidence pack, approved scope and client context present | PASS — production Growth Blueprint quality gate | `/approve <run> because <rationale>; then /continue <run>` |
| `growth_blueprint_deliverable_production` | quality-accepted Blueprint, evidence lineage and canon bundle present | PASS — production deliverable quality gate | `/approve <run> because <rationale>; then /continue <run>` |
| `growth_blueprint_to_campaign_world` | canonical campaign identity, approved Growth Blueprint, evidence lineage and activation implications | PASS — candidate generation plus Tony taste-triage production validators | `/worlds <run>; /select-world <run> because <reason>; /continue <run>` |
| `campaign_world_to_creative_bible` | exact selected Campaign World, Growth Blueprint and production context | PASS — Bible generation plus Tony taste/producibility validators | `/bible <run>; /approve-bible <run> because <reason>; /continue <run>` |
| `creative_bible_to_asset_production` | exact approved Creative Bible and production constraints | PASS — Production Pack planning and creative-output validators; two stage approvals plus `/assets` and `/approve-assets` | `/approve <run>...; /continue <run>; /assets <run>; /approve-assets <run> because <reason>` |
| `asset_review_to_delivery_preparation` | exact Matt-approved versions, authoritative Asset Manifest and delivery requirements | PASS — package/action-preview validator and receipt-backed delivery validator; delivery is a separate external-write approval | `/approve <run> because <reason>; /continue <run>` for package, then repeat for exact client delivery |
| `delivery_to_follow_up_next_action` | receipt-backed delivery evidence, client context and measurement context | PASS — production validator enforces read-only normalised ingestion, exact asset IDs and human strategy/iteration control | `/approve <run> because <rationale>; terminal next-action state` |

After the final synthetic approval, the terminal run is `complete` / `approved`. Before that decision it remains `awaiting_approval` / `pending`, as recorded in the primary table.

## Gate evidence

Every gate recorded the following evidence in its isolated run:

- input snapshot and required input field list;
- missing-field validation (empty for the passing gate run);
- selected worker identity and attempt record;
- immutable JSON artefact ID, checksum, location and parent artefact IDs;
- quality-gate result and failed checks;
- resulting workflow and approval state;
- append-only workflow events;
- elapsed execution time;
- explicit approval/continuation command.

The common successful audit sequence was:

`workflow.created → stage.started → stage.attempt_recorded → stage.quality_recorded → workflow.outputs_promoted → stage.completed`

Human-gated workflows then recorded `approval.requested`. Gate 4, the read-only Research Engine gate, completed without human approval. The other ten gates halted at `awaiting_approval` before continuation.

Example continuation exposed at a human gate:

`/approve northstar-test-lifecycle-gate-08 because Northstar Test Co gate reviewed; then /continue northstar-test-lifecycle-gate-08`

The test invokes runtime approvals only with synthetic exact-artefact checksum bindings. Its isolated client-delivery fixture records a synthetic external-write receipt after the dedicated approval boundary. It performs no real client contact, publication or spend action.

## Prerequisite and validation coverage

All 11 gates use production validators currently composed by `build_tony_workflow_runtime`, including the following post-Blueprint controls:

- Blueprint Lite quality;
- Discovery preparation quality;
- Growth Sprint proposal quality;
- research evidence quality;
- Growth Blueprint quality;
- Growth Blueprint deliverable quality;
- Campaign World generation and Tony triage;
- Creative Bible generation and Tony triage;
- Production Pack planning and generated asset-version validation;
- deterministic delivery preparation and receipt-backed client delivery;
- bounded read-only performance follow-up with human-owned strategy and creative iteration.

## Adversarial results

| Scenario | Result | Evidence |
|---|---|---|
| Duplicate intake | PASS | Same run and inputs create one `workflow.created` event; conflicting replay is rejected as different input. |
| Missing required data | PASS | Missing `diagnostic_input_package` produces `blocked` / `missing_required_inputs`; worker is not called. |
| Worker failure | PASS | Two bounded timeout attempts are retained; state blocks with `worker_retry_policy_exhausted`. |
| Malformed output | PASS | Non-object worker output blocks with `worker_output_rejected:MalformedWorkerOutput`; no external action occurs. |
| Rejected approval | PASS | Rejection reopens the producing stage, increments revision, preserves the original artefact and writes a distinct revised artefact. |
| Premature dispatch | PASS | Handoff before completed human approval is rejected; approval remains pending and no downstream run is dispatched. |
| Service restart | PASS | Pending approval survives runtime reconstruction; recovery creates no duplicate execution or artefact. |
| Native full-chain handoff | PASS | Bounded deterministic run IDs preserve readable target context and source lineage through all 11 gates. |

## Failure reasons and state inconsistencies

1. **Duplicate approval-request events.** Human-gated runs contain two `approval.requested` events: one from stage completion and another from the explicit pause. The snapshot remains consistent, but audit consumers may count two requests for one gate.
2. **Provider gaps remain fail-closed.** Creative production and client delivery require configured providers; this is correct safety behaviour and prevents false live completion.
3. **Input payload expansion.** The handoff builder carries most upstream fields into every downstream run. It preserves evidence but creates very large snapshots and increases the chance of field-name collisions. Output fields not required as next inputs are filtered, but the payload remains broader than each specialist's declared input contract.

## Orphaned artefacts

- No orphaned artefacts were created by the isolated conformance run.
- The native chain completes without leaving a partial downstream run or orphaned artefact.
- Rejected-approval artefacts are intentionally retained immutable history and are not orphans.
- Failed worker attempts retain their attempt evidence as required; they are not represented as accepted outputs.

## Recommended fixes

1. Keep bounded downstream-run identity regression coverage in the full lifecycle suite.
2. Make approval-request creation idempotent for one run, stage, revision and exact artefact checksum.
3. Persist Media Control recommendations as versioned Campaign Engine Insight and creative-iteration proposal records.
4. Configure real creative-production and client-delivery adapters only after credentials, Drive writes, exact-version receipts and retry/reconciliation contracts pass live acceptance.
5. Narrow cross-workflow handoff payloads to declared inputs plus explicit `_lineage`, while preserving required evidence references and backward compatibility.

## Test location and command

- Primary test: `tests/e2e/tony_full_lifecycle_test.py`
- Discovery entry point: `tests/test_tony_full_lifecycle_e2e.py`
- Focused command: `.venv/bin/python -m unittest tests.test_tony_full_lifecycle_e2e -v`

The harness uses only temporary directories, synthetic `.invalid` email data and `northstar-test-*` identifiers. It does not read or modify production client records.
