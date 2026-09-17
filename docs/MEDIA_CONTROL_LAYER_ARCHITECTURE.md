# Narratiive Media Control Layer — architecture and Phase 1

## 1. Current architecture

Narratiive OS already has the control plane that media must extend:

```text
Matt
  -> Tony conversation and deterministic commands
  -> authenticated OpenClaw / Telegram / n8n bridge
  -> canonical workflow and Campaign Engine state
  -> specialist workers and verified business adapters
  -> Notion operational projection + Drive artefacts
  -> append-only execution evidence
```

The canonical implementations found during discovery are:

| Concern | Canonical implementation | Relevance to media |
|---|---|---|
| Tony runtime and command entry | `openclaw/tony_live_bridge.py`, `openclaw/tony_http_bridge.py`, `runtime/tony_command_service.py` | Media queries are another composable Tony command service. |
| Workflow/gate registry | `runtime/workflow_registry.py` | Existing lead-to-delivery workflow remains unchanged. |
| Campaign workflow | `runtime/campaign_engine.py` | Owns `CampaignIdentity`, approved Blueprint, Campaign World, Creative Director's Bible, production plan, asset versions and human gates. |
| Runtime state | `runtime/workspace_state.py`, workflow runtime stores | Existing operational state and replay patterns; no media database is introduced. |
| Audit/provenance | `runtime/execution_journal.py` | Hash-chained append-only record for every provider interaction and denied write. |
| Dispatcher and workers | `runtime/tony_dispatch_adapters.py`, `runtime/worker_registry.py` | Media capability can commission workers; adapters remain provider-specific. |
| HTTP/public boundary | `runtime/public_gateway.py`, `openclaw/tony_http_bridge.py` | Authenticated command/action boundary; media does not open a second service. |
| n8n | managed workflows documented under `docs/operations/` | Future scheduled reads should enter through an authenticated media-ingest command or job, not become a new source of truth. |
| Notion | `runtime/notion_leads.py`, workflow projection adapters | Human-facing operational source for ownership, status and next action. Runtime execution evidence is projected explicitly; Notion changes are not inferred as execution. |
| Drive | verified Drive business adapter and Campaign Engine Drive URIs | Asset/deliverable repository; media stores IDs and performance, not binary creative. |
| Telegram | n8n trigger → authenticated Tony bridge | Interface only; never source of approval or state truth. |
| Approval | Campaign Engine `HumanApproval`, workflow approval queue, exact artefact checksums | Media launch/spend approvals must be explicit, persisted, exact-scope records. |
| Configuration/secrets | process environment plus adapter validation; deployment tooling avoids committed secrets | Provider tokens and account IDs remain outside repository and audit payloads. |
| Services | `scripts/install_launch_agents.py`, `scripts/service_doctor.py`, `scripts/service_supervisor.py`, `docs/operations/launchd.md` | No new daemon is required in Phase 1. |
| Tests | `tests/` plus isolated `.runtime`/temporary stores | Northstar fixtures exercise the complete read-only boundary without production records. |

The current canonical Campaign Engine ends at `asset_suite_approved`. Its state always keeps `publication_authorised=false` and `media_spend_authorised=false`. Phase 1 attaches a read-only media projection to that same `CampaignIdentity`; it does not append unsafe launch transitions to the production workflow.

## 2. Relevant existing components reused

- `CampaignIdentity` supplies workspace, client, brand, markets, products and campaign IDs.
- existing `ProducedAssetVersion.asset_id` remains the Narratiive creative key. The media layer adds provider creative/ad mappings without replacing it.
- the Campaign Engine's Blueprint → Campaign World → Creative Director's Bible → Production Pack → Asset Manifest lineage is verified before the certification harness admits a campaign to media monitoring.
- `ExecutionJournal` is the authoritative media audit/replay source. Canonical snapshots are stored inside completed read events and reconstructed after restart.
- Tony's decorator-style command composition now exposes `/media` and `/media-integrations` without changing existing commands.
- existing n8n, Notion and Drive roles are preserved. Phase 1 does not add another scheduler, CRM or file store.

## 3. Proposed extension

`runtime/media_control.py` adds four separations:

```text
Tony
  -> TonyMediaCommandService (query, exception surfacing, human decision requests)
  -> MediaControlService (canonical model, policy, validation, normalisation, audit)
  -> ReadOnlyProviderAdapter contract
  -> Meta / TikTok / Google transport
```

The Media Agent is a capability role, not an independent authority. In Phase 1 its deterministic implementation analyses canonical snapshots and emits recommendations. It cannot call an adapter write method.

The canonical model includes:

- the existing `CampaignIdentity`;
- native provider account/campaign/ad-group/ad/creative IDs;
- persistent Narratiive asset → provider creative/ad mappings;
- period, currency, timezone, provider status, review and tracking state;
- a metric value plus provider, definition, period, currency, attribution context and explicit availability state;
- creative-learning dimensions: Campaign World, territory, format, hook, message, audience, platform and placement;
- recommendations that are advisory and human-approval-required.

The conceptual future media lifecycle is represented by `MediaLifecycleStage`:

```text
media_plan -> media_review -> human_approval -> trafficking
-> pre_launch_validation -> human_launch_approval -> launch
-> monitor -> optimise -> learn
```

Phase 1 implements schema and policy support only. It does not transition a real campaign through trafficking or launch.

## 4. Data flow

1. An approved Campaign Engine record supplies the canonical identity and approved creative IDs.
2. A provider mapping resolves that identity to one explicit native account and campaign. Names are never keys.
3. n8n or an operator may request a scheduled/on-demand read with a stable request ID.
4. The policy engine authorises `READ` before provider dispatch.
5. A provider adapter retrieves a native response. Missing adapter, credential, mapping, API response or malformed data fails closed.
6. The normaliser emits provider-aware canonical metrics. Missing metrics become `available=false` and `value=null`, never zero.
7. The service appends a hash-chained audit event containing request/result metadata and the canonical snapshot, without credentials.
8. Tony reconstructs the latest provider snapshots from the journal, analyses exceptions and surfaces recommendations.
9. Recommendations remain pending human decisions; they do not call platform APIs.
10. Future creative-learning projections may feed approved observations back to the existing performance-feedback layer.

Cross-provider totals are produced only when currencies match. Attribution contexts always remain visible. A numerically similar conversion, CPA or ROAS from two providers is not asserted to be measurement-equivalent.

## 5. Authentication requirements

Credentials are validated at adapter construction and are never serialised to canonical state or audit events.

- Meta: Meta app with Marketing API, authorised Business Portfolio/ad account, a server-side user or system-user access token, and read permission (`ads_read`; any broader permission requires separate justification). Required local values: `META_ACCESS_TOKEN`, `META_ACCOUNT_ID`, `META_TIMEZONE`, `META_CURRENCY`, and an explicit reviewed `META_GRAPH_API_VERSION`.
- TikTok: approved TikTok API for Business app, app/secret used in the external OAuth exchange, advertiser authorisation, resulting server-side access token and explicit advertiser ID. Required runtime values: `TIKTOK_ACCESS_TOKEN`, `TIKTOK_ACCOUNT_ID`, `TIKTOK_TIMEZONE`, `TIKTOK_CURRENCY`.
- Google Ads: Google Cloud project/API access, OAuth client ID/secret, refresh token for a user with access, target customer ID, and manager/login customer ID when access is indirect. Required values: `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`, `GOOGLE_ADS_ACCOUNT_ID`, optional `GOOGLE_ADS_MANAGER_ACCOUNT_ID`, `GOOGLE_ADS_TIMEZONE`, `GOOGLE_ADS_CURRENCY`, and an explicit reviewed `GOOGLE_ADS_API_VERSION`. Google sunset developer tokens on 9 September 2026; `GOOGLE_ADS_DEVELOPER_TOKEN` may remain for backwards compatibility but is not a new Phase 1 prerequisite.

Exact external steps and authoritative links are in `docs/MEDIA_EXTERNAL_SETUP.md`.

## 6. Security implications

- Phase 1 allows only `READ`, `ANALYSE` and `RECOMMEND`.
- all write methods exist only as hard-disabled methods that raise before transport dispatch;
- even a supplied Matt approval ID cannot enable a Phase 1 mutation;
- secrets remain environment-only and are excluded from reports, Notion, Telegram and audit metadata;
- ambiguous accounts or mappings block work;
- provider errors do not imply campaign health;
- response schemas are validated before state advances;
- request IDs make successful ingestion idempotent across service restart;
- client/workspace/campaign identity is retained on every snapshot and audit record;
- production client records are not used by the test harness.

## 7. Approval architecture

Media authority is machine-readable:

| Classification | Phase 1 |
|---|---|
| `READ` | Allowed |
| `ANALYSE` | Allowed |
| `RECOMMEND` | Allowed |
| `DRAFT` | Blocked at the provider boundary |
| `EXECUTE_WITHIN_LIMITS` | Blocked |
| `EXECUTE_WITH_APPROVAL` | Blocked |
| `PROHIBITED` | Blocked |

Future writes must follow: approved strategy → policy → deterministic validation → exact persisted human approval → idempotent execution → provider verification → audit. An LLM recommendation, Telegram sentence or Notion status can never substitute for the approval record.

The pre-launch validator already enforces prerequisite evidence, currency/timezone validity and the critical budget invariant:

```text
sum(platform authorised budgets) <= approved client budget
```

This validator is present for design/testing only; no launch path consumes it in Phase 1.

## 8. Implementation phases

1. **Phase 1 (this change):** canonical schema, creative mappings, adapter contract, fixture transports, normalisation, policy, audit/replay, Tony queries, diagnostics and Northstar certification.
2. **Live read onboarding:** implement and certify one production read transport at a time after credentials exist; then add bounded n8n schedules for exceptions/daily/weekly reads.
3. **Media planning:** create an approved media-plan artefact from the Growth Blueprint/Campaign World and project its status to Notion.
4. **Draft trafficking:** provider draft creation only, with no launch and exact native-ID receipts.
5. **Human-approved activation:** separate approval state and pre-launch verification; no approval inference.
6. **Bounded optimisation:** only explicitly authorised actions within deterministic limits; total authorised spend can never increase autonomously.
7. **Cross-client learning:** anonymised/permissioned learning with strict client isolation.

## 9. Known blockers and limitations

- No production Meta, TikTok or Google credentials were available to this repository run, so real account reads are **not certified**.
- Fixed-host read-only HTTP transports now exist for Meta Marketing API, TikTok API for Business and Google Ads SearchStream/OAuth. Their request construction and native-to-canonical translation are fixture-tested, but each remains `DEGRADED` until its first successful audited live read.
- Provider attribution models are not harmonised. Canonical output preserves context but does not claim direct comparability.
- Provider breakdown availability varies and must stay provider-specific.
- Tony's natural-language interpretation is future work; deterministic `/media` commands are implemented.
- n8n schedules are not installed until a live read-only provider smoke test passes.
- `MediaLifecycleStage` is a future lifecycle vocabulary, not an enabled live-buying state machine.

## 10. Required external setup from Matt

Matt's required actions are limited to account ownership and consent:

1. choose the exact Business Portfolio/advertiser/customer accounts Narratiive may read;
2. create or approve the platform applications and grant least-privilege read access;
3. complete each OAuth/advertiser authorisation flow;
4. confirm account currency, timezone and any manager-account relationship;
5. provide the credentials through the existing secure runtime environment—not chat, Git, Notion or Telegram;
6. authorise a read-only smoke test against a non-critical/test campaign where available.

Codex/n8n engineering should perform configuration wiring, validation, smoke tests and scheduler setup after those external steps. No platform write permission is requested for Phase 1.
