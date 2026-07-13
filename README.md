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
