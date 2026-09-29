# Media provider external setup — Matt checklist

This checklist requests only account-owner actions that cannot be completed in the repository. Provider applications may hold approved management capabilities, but Narratiive runtime authority remains read/analyse/recommend only. Do not paste credentials into GitHub, Notion, Telegram, email or this document.

## Before starting

- [ ] Confirm the legal Narratiive entity/app owner and the person who can approve platform access.
- [ ] Select one test or low-risk advertiser account per provider.
- [ ] Record the account's native ID, ISO currency and IANA timezone.
- [ ] Decide whether access is direct or through a Business Portfolio/Business Center/manager account.
- [ ] Arrange secure secret entry on the Mac/runtime host. Engineering will validate values without printing them.

## Meta Ads

1. [ ] In Meta for Developers, create/select the Narratiive business app and add the Marketing API product.
2. [ ] Add the Facebook Login for Business use case and register this exact Valid OAuth Redirect URI:

   `https://lushly-spoof-reheat.ngrok-free.dev/webhook/meta-media-oauth-callback`

3. [ ] In Business Settings, confirm the app user is authorised for the correct Business Portfolio and exact advertising account.
4. [ ] Request `ads_read`, `ads_management` and `business_management` as submitted for the Narratiive Media Control app. Narratiive records the granted provider capabilities, but every campaign, ad-set, ad, creative, audience, budget, bid, status, pixel and event mutation remains independently blocked before provider dispatch.
5. [ ] Enter only the app configuration through the protected local prompt:

   ```bash
   .venv/bin/python scripts/configure_meta_oauth.py
   ```

   The command stores `META_APP_ID`, `META_APP_SECRET` and the explicitly pinned `META_GRAPH_API_VERSION` without displaying the entered values. The current reviewed version is `v26.0`; versions never float silently.
6. [ ] Start the authenticated OAuth flow through Tony's loopback service. The callback exchanges the one-time code server-side, upgrades it to a long-lived user token, verifies the granted permissions, discovers accessible accounts and writes the token atomically to the mode-`0600` runtime environment.
7. [ ] If Meta returns one accessible account, Narratiive also stores its account ID, timezone and currency. If multiple accounts are returned, select the intended account before certification; Narratiive does not guess.
8. [ ] Authorise a read-only smoke test: accessible-account metadata, campaigns, ad sets, ads, creative metadata, delivery/review status and a seven-day Insights query.

The public HTTPS callback terminates at n8n and forwards the one-time values to Tony over authenticated loopback. Successful, failed and manual workflow execution payloads are not persisted. OAuth state is stored only as a short-lived SHA-256 digest and consumed once. Meta tokens are sent only to fixed Meta HTTPS hosts; API reads include `appsecret_proof` when the app secret is configured. Codes, tokens and secrets are never returned by Narratiive's HTTP responses or written to its audit journal.

References: Meta's official [Marketing API authorisation guide](https://developers.facebook.com/documentation/ads-commerce/marketing-api/get-started/authorization), [Ads Insights API guide](https://developers.facebook.com/documentation/ads-commerce/marketing-api/insights), [`ads_read` permission reference](https://developers.facebook.com/docs/permissions/reference/ads_read/) and [Graph/Marketing API v26.0 changelog](https://developers.facebook.com/docs/graph-api/changelog/version26.0/).

## TikTok Ads

1. [ ] Create/select the Narratiive app in TikTok API for Business and submit it for the required review.
2. [ ] Register this exact Advertiser Redirect URL:

   `https://lushly-spoof-reheat.ngrok-free.dev/webhook/tiktok-media-oauth-callback`

3. [ ] Under Scope of permission, select the submitted read and management capabilities:

   - Ad Account Management > Ad Account Information > Read Ad Account Information (scope `100`)
   - Ads Management > Campaign > Read Campaigns (scope `200`)
   - Ads Management > Campaign > Create and Update Campaigns (scope `201`)
   - Ads Management > Ad Group > Read Ad Groups (scope `210`)
   - Ads Management > Ad Group > Create and Update Ad Groups (scope `211`)
   - Ads Management > Ad > Read Ads (scope `220`)
   - Ads Management > Ad > Create and Update Ads (scope `221`)
   - Reporting > Consolidated Report (scope `44`)

   These provider permissions do not grant Tony or the Media Control Layer runtime mutation authority.
4. [ ] Retain the app ID/secret only in the protected runtime environment, then have the advertiser authorise the app.
5. [ ] The local OAuth service validates a one-time state, exchanges the code server-side, requires the five read scopes, accepts only the three configured management scopes in addition, and stores the token plus non-secret capability metadata without displaying credentials.
6. [ ] Confirm the returned advertiser ID list contains the exact account Narratiive should read.
7. [ ] Complete these protected runtime values securely:

   - `TIKTOK_APP_ID`
   - `TIKTOK_APP_SECRET`
   - `TIKTOK_ADVERTISER_AUTH_URL` (generated by the TikTok app portal)
   - `TIKTOK_ACCESS_TOKEN`
   - `TIKTOK_ACCOUNT_ID` (advertiser ID)
   - `TIKTOK_TIMEZONE`
   - `TIKTOK_CURRENCY`

8. [ ] Authorise a read-only smoke test: authorised advertiser list, campaigns, ad groups, ads/creatives, review/delivery status and an integrated report query.

The public HTTPS callback terminates at n8n and forwards the one-time values to Tony over loopback with bridge authentication. The callback workflow disables successful, failed and manual execution-data persistence. OAuth state is stored only as a short-lived SHA-256 digest and consumed once. Tokens are written atomically to the mode-600 runtime environment; neither tokens, app secrets nor authorisation codes are returned or logged by Narratiive code.

References: TikTok's official [API for Business authorisation guide](https://business-api.tiktok.com/gateway/docs/index?doc_id=1738928364967937&identify_key=c0138ffadd90a955c1f0670a56fe348d1d40680b3c89461e09f78ed26785164b&language=ENGLISH) explains the app ID, secret, callback and advertiser authorisation; its [access-token guide](https://ads.tiktok.com/gateway/docs/index?doc_id=1738373164380162&identify_key=c0138ffadd90a955c1f0670a56fe348d1d40680b3c89461e09f78ed26785164b&language=ENGLISH) returns the token, scope and authorised advertiser IDs.

## Google Ads

Google's official documentation records that developer tokens were sunset on 9 September 2026. API access is now associated with the Google Cloud project used for OAuth. Existing developer-token headers may remain but are optional/ignored. We therefore retain `GOOGLE_ADS_DEVELOPER_TOKEN` only as an optional compatibility value.

1. [ ] Select/create the Narratiive Google Cloud project and enable Google Ads API access for it.
2. [ ] Configure an OAuth consent screen and create the server-side OAuth client.
3. [ ] Have a Google user with access to the intended Ads customer grant the `https://www.googleapis.com/auth/adwords` scope.
4. [ ] Securely retain the refresh token, OAuth client ID and client secret.
5. [ ] Confirm the target customer ID without hyphens.
6. [ ] If access is through a manager account, confirm its customer ID without hyphens; this becomes the login customer ID. If access is direct, leave it unset.
7. [ ] Enter these runtime values securely:

   - `GOOGLE_ADS_CLIENT_ID`
   - `GOOGLE_ADS_CLIENT_SECRET`
   - `GOOGLE_ADS_REFRESH_TOKEN`
   - `GOOGLE_ADS_ACCOUNT_ID` (target customer ID)
   - `GOOGLE_ADS_MANAGER_ACCOUNT_ID` (only for indirect manager access)
   - `GOOGLE_ADS_TIMEZONE`
   - `GOOGLE_ADS_CURRENCY`
   - `GOOGLE_ADS_API_VERSION` (an explicitly reviewed supported version, for example `v25`)
   - optional legacy `GOOGLE_ADS_DEVELOPER_TOKEN`

8. [ ] Authorise a read-only smoke test: accessible customers, campaign/ad-group/ad/assets, policy status, delivery status and a seven-day Google Ads Query Language report.

References: Google's official [OAuth overview](https://developers.google.com/google-ads/api/docs/oauth/overview), [access model](https://developers.google.com/google-ads/api/docs/oauth/access-model), [authorisation headers](https://developers.google.com/google-ads/api/rest/auth) and [developer-token sunset notice](https://developers.google.com/google-ads/api/docs/api-policy/developer-token).

## Acceptance after credentials are entered

Engineering—not Matt—will then:

- validate configuration without echoing secrets;
- prove the authenticated identity resolves to exactly one intended account;
- perform read-only smoke tests and capture provider request IDs;
- verify currency, timezone, attribution settings and data freshness;
- run the Northstar contract suite plus provider-specific live-read tests;
- expose status through `/media-integrations`;
- add n8n schedules only for providers that pass;
- leave every write method disabled.

Run a provider certification through the protected environment with:

```bash
.venv/bin/python scripts/run_with_env.py ~/.config/narratiive/runtime.env \
  .venv/bin/python scripts/certify_media_provider.py PROVIDER
```

The command performs account and campaign-list reads, appends success or failure
to the Media Control Layer execution journal, proves all Phase 1 adapter write
methods remain blocked before transport dispatch, and prints only non-secret
status and account-mapping evidence. A successful empty campaign list is a
healthy live result; it must not be converted into a missing-configuration or
provider-error state.

The live read adapter is not production-accepted until its status is `HEALTHY`, account mapping is explicit and the audit journal contains a successful read. Missing credentials must appear as `NOT_CONFIGURED`, not as a healthy empty account.

## n8n read-only ingestion contract

After a provider passes its live smoke test, an n8n schedule may call `POST /media/sync` on the existing Tony bridge. A configured bridge bearer token is mandatory; the route remains unavailable when that token is absent. The request must use that token and a stable, unique `request_id`; an exact-payload retry with the same ID returns the audited result without reading the provider again. Reusing an ID with another client, campaign, period or mapping fails closed.

```json
{
  "request_id": "campaign-123-meta-2026-09-17T10:00:00Z",
  "tony_request": "Scheduled read-only campaign performance sync",
  "identity": {
    "workspace_id": "workspace-id",
    "client_id": "client-id",
    "brand_id": "brand-id",
    "market_ids": ["gb"],
    "product_ids": ["product-id"],
    "campaign_id": "campaign-123"
  },
  "provider_mapping": {
    "provider": "meta",
    "account_id": "configured-native-account-id",
    "campaign_id": "native-campaign-id",
    "ad_group_ids": [],
    "ad_ids": [],
    "creative_ids": []
  },
  "period_start": "2026-09-10T00:00:00Z",
  "period_end": "2026-09-17T00:00:00Z",
  "creative_mappings": []
}
```

The account ID must exactly match the configured adapter account. The route supports reads only and always returns `external_action_taken=false`, `publication_authorised=false`, and `media_spend_authorised=false`. A schedule must not be enabled until the corresponding adapter is live-certified; provider errors remain visible for operational review and never trigger a write or an automatic retry storm.
