# Media provider external setup — Matt checklist

This checklist requests only account-owner actions that cannot be completed in the repository. Phase 1 is read-only. Do not grant campaign-management permission where a read-only scope is available, and do not paste credentials into GitHub, Notion, Telegram, email or this document.

## Before starting

- [ ] Confirm the legal Narratiive entity/app owner and the person who can approve platform access.
- [ ] Select one test or low-risk advertiser account per provider.
- [ ] Record the account's native ID, ISO currency and IANA timezone.
- [ ] Decide whether access is direct or through a Business Portfolio/Business Center/manager account.
- [ ] Arrange secure secret entry on the Mac/runtime host. Engineering will validate values without printing them.

## Meta Ads

1. [ ] In Meta for Developers, create/select the Narratiive business app and add the Marketing API product.
2. [ ] In Business Settings, confirm the app/system user is owned by or shared with the correct Business Portfolio.
3. [ ] Assign the exact ad account to the authorised user/system user.
4. [ ] Grant the least-privilege `ads_read` permission for Phase 1. Do not grant `ads_management` merely for this read-only build.
5. [ ] Generate/authorise a server-side access token and note its expiry/renewal policy.
6. [ ] Confirm the ad account ID shown by Ads Manager (the native API form commonly uses `act_<id>`).
7. [ ] Enter these runtime values securely:

   - `META_ACCESS_TOKEN`
   - `META_ACCOUNT_ID`
   - `META_TIMEZONE` (for example `Europe/London`)
   - `META_CURRENCY` (for example `GBP`)

8. [ ] Authorise a read-only smoke test: account list, campaign list, one campaign, creatives, delivery/review status and a seven-day insight query.

Reference: [Meta's official Marketing API collection](https://www.postman.com/meta/facebook-marketing-api/documentation/0zr4mes/facebook-marketing-api-mapi) describes user/system-user tokens, ad-account IDs and `ads_read` access.

## TikTok Ads

1. [ ] Create/select the Narratiive app in TikTok API for Business and submit it for the required review.
2. [ ] Configure the approved callback URL and retain the app ID/secret in the secure credential store.
3. [ ] Have the advertiser authorise the app for the intended read/reporting scope.
4. [ ] Exchange the one-time authorisation code for an access token through the approved server-side flow.
5. [ ] Confirm the returned advertiser ID list contains the exact account Narratiive should read.
6. [ ] Enter these runtime values securely:

   - `TIKTOK_ACCESS_TOKEN`
   - `TIKTOK_ACCOUNT_ID` (advertiser ID)
   - `TIKTOK_TIMEZONE`
   - `TIKTOK_CURRENCY`

7. [ ] Authorise a read-only smoke test: authorised advertiser list, campaigns, ad groups, ads/creatives, review/delivery status and an integrated report query.

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

The live read adapter is not production-accepted until its status is `HEALTHY`, account mapping is explicit and the audit journal contains a successful read. Missing credentials must appear as `NOT_CONFIGURED`, not as a healthy empty account.
