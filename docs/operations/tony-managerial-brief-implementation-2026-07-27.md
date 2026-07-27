# Tony managerial brief implementation — 2026-07-27

## Objective

Make `/morning` and `/evening` useful as a 30-second Chief of Staff view without inventing work that Mission Control has not recorded.

## Implemented

- Replaced diagnostic-first brief rendering with period-specific managerial sections.
- Morning now projects: Today's focus, What changed, Tony is handling, Approvals needed, Blockers, Watch-outs.
- Evening now projects: Completed, Progressed, Remaining, Carry into tomorrow, Decisions, Blockers, Watch-outs.
- Added evidence-backed projections from existing Mission Control fields and GitHub change snapshots.
- Added dedicated `system_watchouts` in the executive brief so routine connection/repository warnings do not dominate operational work.
- Suppressed pseudo-strategic recommendations when Mission Control has no recorded operational content.
- Preserved existing serialised/archive fields and added only backward-compatible fields.

## Evidence

- Branch: `agent/managerial-executive-briefs`
- Pull request: #96
- Runtime change: `runtime/executive_brief.py`
- Regression coverage: `tests/test_executive_brief.py`

## Validation status

- Static implementation review completed through the pull-request patch.
- The repository currently exposes no pull-request workflow run for the branch, so automated test execution is not yet evidenced by GitHub Actions.

## Remaining work

1. Run the repository test suite in an execution environment with the project dependencies.
2. Validate live `/morning`, `/evening`, `/status`, and `/client` responses through the Tony bridge.
3. Improve Mission Control ingestion where live workstreams, completions, approvals, and owner actions are still absent from the snapshot.
4. Merge PR #96 once executable validation is green.

## Blockers

No product decision is blocked. The only current limitation is the absence of an available repository execution environment or GitHub Actions run for automated validation.

## Next action

Use the existing runtime environment to execute the tests and command acceptance checks, then merge the implementation if green.
