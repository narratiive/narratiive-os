# Meta Ads Phase 1 read-only onboarding

Status: backend ready; external app credentials and advertiser consent required

## Fixed values

- App name: `Narratiive Media Control`
- Valid OAuth Redirect URI: `https://lushly-spoof-reheat.ngrok-free.dev/webhook/meta-media-oauth-callback`
- Reviewed API version: `v26.0`
- Requested permission: `ads_read`
- Prohibited permissions: `ads_management`, `business_management`

Accessible advertising accounts are discovered through the user's `ads_read` grant. Phase 1 does not request the broader Business Manager or advertising-management permissions. The application contains no Meta mutation transport: campaign, ad-set, ad, creative, budget, bid, activation, audience, pixel and event mutations all raise before provider dispatch.

## Engineering installation

Install the credential-safe callback workflow and restart n8n:

```bash
.venv/bin/python scripts/install_n8n_meta_oauth_callback.py
```

Configure app values through hidden prompts:

```bash
.venv/bin/python scripts/configure_meta_oauth.py --graph-version v26.0
```

With the Tony bridge running and its bearer token loaded, call authenticated `POST /oauth/meta/start`. Open only the returned official `facebook.com` authorisation URL. The callback performs the token exchanges and permission/account verification without returning secrets.

After exactly one intended account is configured, restart the Tony runtime so it reloads the protected environment, then certify:

```bash
.venv/bin/python scripts/run_with_env.py ~/.config/narratiive/runtime.env \
  .venv/bin/python scripts/certify_media_provider.py meta --include-inventory
```

The integration becomes `HEALTHY / LIVE` only after Meta successfully returns the accessible-account list and the configured account's campaign list. A successful empty campaign list is healthy. A token, callback or API failure is audited as offline and never inferred to be healthy.

The optional inventory pass reads and normalises account, campaign, ad-set, ad
and creative metadata. Tony can then report the verified hierarchy with
`/media inventory meta`; that command reads the append-only journal and does
not contact Meta or trigger any external action.

## Security and recovery

- OAuth state is a single-use, expiring SHA-256 digest in a mode-`0600` file.
- App secret, code and tokens remain outside Git and do not appear in HTTP responses or execution evidence.
- Tokens are written atomically to the protected runtime environment.
- Meta API reads use `appsecret_proof` when the app secret is configured.
- n8n does not persist callback execution payloads.
- Re-running `/oauth/meta/start` creates a new state; a consumed or expired callback fails closed.
- Credential rotation repeats configuration and OAuth, then certification. Existing audit history is retained.

Official references: [authorisation](https://developers.facebook.com/documentation/ads-commerce/marketing-api/get-started/authorization), [Ads Insights](https://developers.facebook.com/documentation/ads-commerce/marketing-api/insights), [`ads_read`](https://developers.facebook.com/docs/permissions/reference/ads_read/), [v26.0 changelog](https://developers.facebook.com/docs/graph-api/changelog/version26.0/).
