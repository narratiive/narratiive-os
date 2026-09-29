# Google Ads Phase 1 read certification

Status: `HEALTHY / LIVE`

Certification date: 28 September 2026

## Certified mapping

- Provider: Google Ads API `v25`
- Advertiser customer: `9780735754`
- Manager/login customer: `7620152450`
- Account timezone: `Europe/London`
- Account currency: `GBP`
- Secure configuration: `~/.config/narratiive/runtime.env` (mode `0600`)

## Evidence

The protected provider-certification command completed both read operations:

- accessible-customer query: passed, one customer returned;
- customer-scoped campaign-list query: passed, zero campaigns returned.

Zero campaigns is a valid healthy empty result. Health is based on the
successful customer-scoped provider response, not on the presence of campaign
objects. The append-only Media Control Layer execution journal recorded the
successful read as `exec-e20dab73550d4be5afb6bd9f8c6662a2` at
`2026-09-28T19:51:13.864463Z`.

The resulting Google diagnostic is:

- health: `healthy`;
- connection status: `live`;
- credential health: `configured_verified_by_successful_read`;
- campaigns returned: `0`;
- mapped campaigns: `0`.

## Phase 1 safety

The certification performs reads only. It separately proved that
`create_campaign`, `create_ad_group`, `create_ad`, `upload_creative`,
`update_budget`, `pause_ad`, `resume_ad`, and `activate_campaign` all raise
`MediaMutationDisabled` before provider transport dispatch.

No external write was performed. Publication and media spend remain
unauthorised. Credentials were not printed, persisted to the repository,
rotated, deleted, or overwritten.

## Verification

- Focused Media Control Layer, provider transport, sync bridge and Northstar
  certification tests: `39` passed.
- Full repository suite: `1,657` passed.
- Python compilation: passed.
- Diff whitespace and credential scan: passed; no credential values were added.

## Operator command

Use the repository virtual environment and protected environment loader:

```bash
.venv/bin/python scripts/run_with_env.py ~/.config/narratiive/runtime.env \
  .venv/bin/python scripts/certify_media_provider.py google
```

The command writes operational evidence to `TONY_MEDIA_CONTROL_STATE_ROOT`, or
to `.runtime/media-control` when that variable is not configured. Tony's
`/media-integrations` and `/health` projections read that same journal. A later
failed provider read supersedes the healthy observation and fails closed.
