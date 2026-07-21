# ADR 0001: Narrow service recovery policy

## Status

Accepted.

## Decision

Narratiive OS will recover runtime services by interpreting the stable exit codes emitted by `scripts/service_doctor.py` and restarting only the component reported unhealthy.

The supervisor will:

- execute restart commands as argument arrays without a shell;
- reject unknown doctor exit codes;
- treat missing or failed restart commands as recovery failures;
- emit structured JSON suitable for logs and automation;
- preserve an append-only event history when configured.

The supervisor will not:

- restart every service after a single-component failure;
- embed machine-specific paths or user IDs in application code;
- retry indefinitely inside one invocation;
- conceal failed recovery behind a successful exit status.

## Consequences

Repository-managed launchd manifests can invoke this supervisor safely. Installation tooling remains responsible for rendering machine-specific labels, paths and user domains into local configuration.
