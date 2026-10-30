# Supervised Growth Blueprint delivery runbook

This runbook operates the Issue #471 fictional demonstration profile. It does not deploy a service or release a client artefact.

## Inputs

Start from `tests/fixtures/fieldwork_supervised_blueprint.json` or a workspace-scoped copy with:

- an explicit workspace, client and run identity;
- `fictional: true` for a demonstration;
- a structured evidence ledger;
- an ecommerce baseline and three named scenarios;
- a falsifiable constraint, proposed advantage and three prioritised recommendations;
- one creative territory, growth engine and 12-month roadmap.

The accepted evidence classes are exactly:

- VERIFIED CLIENT
- VERIFIED EXTERNAL
- MODELLED
- ASSUMPTION
- CREATIVE ILLUSTRATION

A fictional fixture cannot use either VERIFIED class. A real run must supply the source document identity for VERIFIED CLIENT or publisher and URL for VERIFIED EXTERNAL.

## Deterministic smoke test

From the canonical checkout, using Python 3.10 or newer:

```bash
.venv/bin/python scripts/run_supervised_blueprint_delivery.py \
  --intake tests/fixtures/fieldwork_supervised_blueprint.json \
  --runtime-root .runtime/issue-471-fieldwork \
  --output-dir outputs/demos/fieldwork-issue-471
```

The command must finish with `PASS_FOR_HUMAN_REVIEW`, `approval_status: pending` and `external_action_taken: false`.

## Rendered PPTX and PDF

Configure the existing local presentation worker paths. Names only:

- `NARRATIIVE_PRESENTATION_NODE`
- `NARRATIIVE_PRESENTATION_NODE_MODULES`
- `NARRATIIVE_PRESENTATION_SKILL_DIR`
- `NARRATIIVE_PRESENTATION_PYTHON`

Then rerun the command with `--render`. The existing renderer creates an editable PPTX, a 20-page review PDF, rendered slide images, package validation and OCR-backed visual QA. Use a fresh runtime root or run identity when the source changes because artefacts and deliverable records are immutable.

## Expected output package

- structured client intake;
- evidence and assumptions ledger in JSON and CSV;
- commercial opportunity model;
- seven-chapter Blueprint in JSON and Markdown;
- 20-slide presentation specification, including the five-slide executive opening;
- editable PPTX and review PDF when rendering is enabled;
- independent QA in JSON and Markdown;
- checksum-bound human approval checkpoint;
- lineage manifest.

## Approval checkpoint

QA can only recommend `PASS_FOR_HUMAN_REVIEW`. Before external release, Matt must record approve, request revision or block against the exact Blueprint, presentation specification and QA checksums. A revised artefact requires a new version and a new decision. Do not change `release_authorised`, send the deck, publish it or present it to a client from this demonstration command.

## Regression checks

Run the focused Issue #471 tests and the existing Blueprint/KatKin delivery tests:

```bash
.venv/bin/python -m unittest tests.test_supervised_blueprint_delivery -v
.venv/bin/python -m unittest \
  tests.test_deliverable_production \
  tests.test_growth_blueprint_deliverable_worker \
  tests.test_rendered_blueprint_review \
  tests.test_blueprint_orchestrator \
  tests.test_blueprint_visual_mapper -v
```

Then run the repository suite before merge:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The KatKin workflow is regression evidence only. Do not regenerate, modify, approve or release real KatKin deliverables during this run.
