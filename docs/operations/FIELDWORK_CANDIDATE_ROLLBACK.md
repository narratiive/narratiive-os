# FIELDWORK candidate rollback

The founder-argument workflow is opt-in. It is not the production default and no deployment is included in this branch.

## Disable the candidate

Stop enqueueing workflow ID `fieldwork_founder_argument_experiment`. Existing production workflow IDs and locked specifications remain unchanged.

## Revert the branch

Revert the FIELDWORK-quality branch commit(s) without touching the reliability branch or PR #479. The candidate additions are isolated to the experimental workflow definition, instruction, strict quality checks, regression tests, calibration runner and internal outputs.

## Preserve evidence

Do not delete accepted or rejected execution receipts when rolling back. They are audit evidence, not production dependencies. Keep the preserved original Rave benchmark unchanged.

