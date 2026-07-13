# Narratiive OS

## Deterministic Growth Blueprint run

Run the five specialist stages against the synthetic RAVE fixture:

Python 3.10 or newer is required.

```bash
python3 scripts/run_pipeline.py \
  --fixture tests/fixtures/rave_pipeline.json \
  --runtime-root .runtime/pipeline
```

Run the command again with the same runtime root and run ID to load the completed
run without regenerating artifacts. A retryable provider failure leaves completed
stages persisted so the same command can resume from the interrupted stage.

Fixture memory is persisted in append-only client journals under the runtime root.
Client and run scope plus specialist selection rules determine which records enter
each execution package.

The Quality Reviewer may also receive a deterministic confidence scorecard. Its
recommendation is advisory; the reviewer continues to apply the stricter artifact
and evidence policy in its agent contract.

Machine-readable revision issues resolve to one specialist owner and invalidate
only that stage and its downstream dependants. Each invalidation is event logged;
immutable artifact-catalog versions are never deleted.

Client-ready workflow definitions declare `approval_required`. Their final quality
stage enters an event-sourced approval queue instead of completing. Tony and n8n
can use the existing command gateway with `approvals.list`, `approvals.get`,
`approvals.approve`, `approvals.revise`, `approvals.comment`, and
`approvals.block`; every reviewer comment and decision is append-only and duplicate
command IDs replay without creating a second audit event.
