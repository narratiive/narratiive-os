# Gmail draft OAuth reauthorisation

## Approval and remaining interactive step

Matt approved the minimum restricted-scope expansion in Issue #477 on
16 October 2026. Reauthorisation still requires the Narratiive mailbox holder to
complete Google's interactive password/MFA challenge and consent screen; the
credential must not be supplied to Codex or recorded in repository evidence.

The live Google grant was audited on 16 October 2026. It currently contains:

- `calendar.calendars.readonly`
- `calendar.events`
- `calendar.events.freebusy`
- `drive.file`
- `gmail.readonly`
- `gmail.send`

The minimum additional scope that permits `users.drafts.create` is:

```text
https://www.googleapis.com/auth/gmail.compose
```

Google also permits draft creation with `gmail.modify` or the full
`mail.google.com` scope. Narratiive must not request either broader alternative.
`gmail.compose` can create, read, update and delete drafts and can send messages
and drafts. Google classifies it as a restricted scope. The application approval
gate remains authoritative: obtaining provider capability does not permit Tony to
create or send a draft without the existing exact-recipient, subject, body,
idempotency and human-approval controls.

Official references:

- <https://developers.google.com/workspace/gmail/api/auth/scopes>
- <https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/create>
- <https://support.google.com/cloud/answer/13464325>

## Reauthorisation procedure

1. Confirm whether the Google Cloud OAuth app is internal-only. If it is external,
   review the app's current verification status before requesting the new
   restricted scope. Matt's scope approval is already recorded in Issue #477.
2. In the existing Google Cloud project, add only
   `https://www.googleapis.com/auth/gmail.compose` to the OAuth consent screen.
   Do not remove the six currently granted scopes.
3. Run a new consent flow for the existing OAuth client with the seven scopes,
   `access_type=offline`, `include_granted_scopes=true` and `prompt=consent`.
   Authenticate only the Narratiive-owned mailbox. Verify the redirect URI against
   the existing OAuth client before opening the consent URL.
4. Exchange the one-time authorisation code server-side. Store only the returned
   refresh token as `TONY_GOOGLE_REFRESH_TOKEN` in
   `~/.config/narratiive/runtime.env`, preserving mode `0600`. Never paste the
   code, access token, client secret or refresh token into GitHub, Notion, logs or
   chat.
5. Refresh an access token and inspect token metadata. The grant must contain the
   original six scopes plus `gmail.compose`; any broader Gmail scope is a failure.
6. Restart only the processes that cache the Google dispatcher after separate
   production approval. The scheduled watcher is a fresh process and reads the
   environment file on every run.
7. Create one controlled draft addressed to the authorised Narratiive-owned test
   mailbox through the native adapter. Verify a Gmail draft ID and `DRAFT` label,
   verify absence of `SENT`, replay the same idempotency key, and confirm that no
   second draft is created.

## Security boundary

- `gmail.compose` is materially more powerful than `gmail.send` because it can
  inspect and modify the mailbox's drafts. If tokens are stored or transmitted
  server-side for an external app, Google's restricted-scope verification and
  security-assessment rules may apply.
- Provider capability does not change Narratiive authority. Draft creation remains
  an approval-gated mailbox mutation; sending remains a separate approval-gated
  mutation.
- Revoke the old refresh token after the replacement grant is verified and the
  rollback window has closed.
