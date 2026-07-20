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

The command gateway also supports isolated client workspaces. Create identities with
`workspaces.create`, then include `workspace_id` on run, dispatch, job, and approval
commands. Each workspace has separate run, event, job, memory, prompt, artifact, and
approval stores; mismatched client or run references are rejected. Requests without
a workspace remain on the compatible `legacy` runtime. `workspaces.migrate_legacy`
copies existing unscoped data into a named workspace without deleting its source.

## Live Growth Blueprint run

Use `scripts/run_live_pipeline.py` to run the same five specialist stages against an
OpenAI-compatible model endpoint. Always use a new `--run-id`; completed runs are
loaded rather than regenerated.

For a local Ollama server:

```bash
export NARRATIIVE_LIVE_ENDPOINT="http://127.0.0.1:11434/v1/chat/completions"
export NARRATIIVE_LIVE_API_KEY="local-ollama"

python3 scripts/run_live_pipeline.py \
  --fixture tests/fixtures/rave_pipeline.json \
  --runtime-root .runtime/live-pipeline \
  --run-id rave-live-1 \
  --model qwen3.5:latest
```

The API-key value is required by the adapter but Ollama does not use it for local
authentication. It is read only at request time and is not persisted. The live
runner defaults to a 300-second request timeout because local reasoning models can
be substantially slower than hosted APIs.

The included RAVE fixture contains synthetic context and is suitable only for proving
live model execution. A client-ready run requires a real input fixture or workspace
memory containing the client brief, source material and evidence.

## Live provider routing

Production workers can wrap provider clients with `ModelRouter` and
`RoutedProviderClient`, or use `RuntimeComponents.routed_worker`. Routing policies
select an explicit primary and ordered fallback chain by workspace, stage and
specialist. A provider/model must be declared in `ProviderCapabilityRegistry`,
configured on the worker and marked `available` or `degraded` in
`ProviderHealthRegistry` before it can be selected; unreported health fails closed.

`EnvironmentTextProviderClient` is the built-in OpenAI-compatible live text
adapter. Its `LiveTextProviderConfig` names the environment variables that contain
the endpoint and API key (for example `NARRATIIVE_LIVE_ENDPOINT` and
`NARRATIIVE_LIVE_API_KEY`). Credential values are read only when a request is made
and are never added to routing policies, events, artifacts or provider metadata.
The existing `DeterministicProvider` remains available for fixtures and local dry
runs.

## Blueprint canon registry

The canonical Blueprint source assets live in `knowledge/blueprint/` and are
locked by `knowledge/blueprint/manifest.json`. The registry validates the imported
Google Drive source documents by checksum before the Blueprint orchestrator uses
them, so the production prompt, schema and visual framework stay versioned and
immutable.
