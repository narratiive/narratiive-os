# Issue #477 live customer-journey rehearsal

The auditable result is in `outputs/rehearsals/issue-477/`.

## Reproduce the safe connector audit

Run from the canonical Narratiive OS checkout with the repository virtual environment and the protected runtime environment loader:

```bash
.venv/bin/python "$HOME/Library/Application Support/Narratiive/run_with_env.py" \
  "$HOME/.config/narratiive/runtime.env" \
  .venv/bin/python scripts/run_issue_477_live_integration_audit.py \
  --audit-date 2026-10-16 \
  --output outputs/rehearsals/issue-477/live-integration-audit.json
```

This command performs read-only health and provider probes. It does not send email or Telegram messages, write Notion or Drive, create meetings, publish campaigns, spend money, or mutate media accounts. Provider record identifiers are hashed before persistence.

## Interpretation

`VERIFIED LIVE` proves the named read occurred against the provider. It does not prove a downstream lifecycle event that was not generated. `VERIFIED SANDBOX` proves isolated local execution. `SIMULATED`, `NOT WORKING` and `NOT TESTED` must remain explicit.

The current result is **NO-GO**. See `outputs/rehearsals/issue-477/customer-journey-trace.md` and `go-no-go.md` for the evidence and exit criteria.
