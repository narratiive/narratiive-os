# Native business adapters

Tony can use native provider APIs for bounded Gmail, Google Calendar, Google
Drive, Notion workflow-projection and Fireflies operations. HTTP dispatch URLs
remain supported and take precedence, so existing deployments are backward
compatible.

Configuration is opt-in. A mode without its credential is reported as
unconfigured and no dispatcher is registered.

## Runtime configuration

Google uses one OAuth grant shared by the three Google adapters:

```text
TONY_DISPATCH_GMAIL_MODE=google_api
TONY_DISPATCH_GOOGLE_CALENDAR_MODE=google_api
TONY_DISPATCH_GOOGLE_DRIVE_MODE=google_api
TONY_GOOGLE_CLIENT_ID
TONY_GOOGLE_CLIENT_SECRET
TONY_GOOGLE_REFRESH_TOKEN
TONY_GOOGLE_CALENDAR_ID=primary
```

`TONY_GOOGLE_ACCESS_TOKEN` may be used for a short-lived test instead of the
three refresh-token fields. Do not persist access or refresh tokens in this
repository. Grant only the Gmail read/send, Calendar availability/event and
Drive file scopes required by the enabled operations, using the canonical
Narratiive Google Workspace account.

Notion workflow projection uses:

```text
TONY_DISPATCH_NOTION_MODE=notion_api
NARRATIIVE_NOTION_TOKEN
NARRATIIVE_NOTION_LEADS_DATA_SOURCE_ID
```

The data-source identifier defaults to the canonical Leads data source. The
integration must be explicitly connected to that data source. Projection is
limited to the canonical business fields and uses a persisted projection marker
to suppress replay.

Fireflies transcript retrieval uses:

```text
TONY_DISPATCH_FIREFLIES_MODE=fireflies_api
TONY_FIREFLIES_API_KEY
```

Fireflies access is read-only in Tony. A transcript may be anchored by its exact
Fireflies transcript ID or resolved from the exact Google Calendar event ID.
Ambiguous or missing matches fail closed.

## Safety and supported operations

Read-only probes and anchored reads may run autonomously. Gmail sends, Calendar
event creation, Drive workspace/file creation and Notion projection require the
existing exact approval evidence in the dispatch contract. Provider responses
must include decision-grade identifiers before Tony accepts execution.

Drive client sharing/delivery is deliberately not implemented by the native
adapter. It remains unavailable until an approved sharing policy defines the
recipient, permission role, notification behaviour and revocation/reconciliation
rules. The adapter must not substitute public-link sharing.

## Independent validation

Load the canonical runtime environment without printing it, then run:

```bash
.venv/bin/python scripts/validate_business_adapters.py
```

The command performs provider-specific read-only probes and emits only status,
missing variable names and non-secret source identifiers. It exits non-zero if
any required adapter is absent or unverified. During incremental setup, require
one or more named surfaces explicitly:

```bash
.venv/bin/python scripts/validate_business_adapters.py --require Notion
```

An unconfigured adapter may never be described as connected merely because a
desktop application, browser session or unrelated n8n credential exists.
