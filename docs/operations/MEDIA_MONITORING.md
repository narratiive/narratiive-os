# Read-only media monitoring

Narratiive produces internal daily and weekly media reports from verified Media Control Layer snapshots. The monitor never contacts a provider itself: provider reads enter through the existing authenticated ingestion boundary, and the monitor analyses only the resulting append-only evidence.

## Schedules

- Daily: 07:15 Europe/London.
- Weekly: Monday 07:30 Europe/London.
- n8n calls Tony over authenticated loopback at `POST /media/monitor`.
- Request IDs are deterministic by local date or ISO week, so retries are idempotent.
- n8n does not persist successful, failed or manual execution payloads for this workflow. The canonical report is stored in Narratiive's hash-chained execution journal.

Install or update the local workflow:

```bash
.venv/bin/python scripts/install_n8n_media_monitor.py
```

The installer backs up the n8n database before an idempotent update and restarts n8n unless `--no-restart` is supplied.

## Tony commands

```text
/media <client-or-campaign> daily
/media <client-or-campaign> weekly
/media exceptions
```

The result explicitly separates:

- `facts`: current provider observations and measurement context;
- `trends`: numeric changes between equal-duration, equal-currency windows;
- `exceptions`: deterministic stale-data, evidence-conflict and material-change signals;
- `recommendations`: rule-based interpretations requiring human review;
- `creative_diagnostics`: creative-level evidence when available, otherwise an explicit limitation.

Thirty per cent is the default material-change threshold. This is an attention rule, not a claim about cause. Cross-provider definitions and attribution remain non-equivalent.

## Safety properties

- only read/analyse authority is used;
- every provider mutation remains hard-disabled before dispatch;
- scheduled reports cannot approve spend, publication or delivery;
- report retries cannot create multiple records for the same request ID;
- a reused request ID with a different cadence or query fails closed;
- stale snapshots and spend-with-zero-impression conflicts surface as exceptions;
- campaign-level results are not assigned to individual creative assets without creative-level provider evidence.
