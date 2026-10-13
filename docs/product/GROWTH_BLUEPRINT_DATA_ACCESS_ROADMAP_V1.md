# Data access roadmap — source priority and purchase gates
Status: research-led recommendation; access, prices and licence terms must be reconfirmed before purchase. 2026-10-13.

## Phase 0: use existing access, avoid subscriptions
1. Client consent and read-only exports: ecommerce orders, GA4, Search Console, Google Ads, Meta Ads, CRM, email platform. Highest value for credible revenue and conversion modelling; requires client-granted permissions.
2. UK Companies House API: official company profile and filings, free public API; company filings are not a reliable proxy for current trading or marketing performance. https://developer-specs.company-information.service.gov.uk/guides/gettingStarted
3. Google Search Console Search Analytics API: owned-site query/page/country/device clicks and impressions; top-row limits mean incomplete long-tail coverage. https://developers.google.com/webmaster-tools/v1/searchanalytics/query
4. GA4 Data API: first-party acquisition/conversion/cohort metrics where configured, subject to per-property token quotas. https://developers.google.com/analytics/devguides/reporting/data/v1/quotas
5. Google Ads API: first-party spend/campaign performance for authorised accounts. Explorer production access 2,880 operations/day but keyword planning and audience insights require Basic/Standard. https://developers.google.com/google-ads/api/docs/api-policy/access-levels
6. Public ONS and government datasets for category/region context; assess definitions and age of each series.

## Phase 1: purchase only when a paid project demands it
- Semrush SEO Business plus API units: search/competitive visibility; access requirements confirmed in official documentation, but estimates are directional and do not establish sales. https://developer.semrush.com/api/v4/get-started/api-access/
- Similarweb: traffic and competitive audience estimates; obtain written API/licensing quote and test coverage on 3 SME domains before purchase.
- GWI / YouGov: audience attitudes and category motivations; evaluate sample sizes and representativeness for niche UK founder categories; API/export permissions and quote need verification.
- Brandwatch / Talkwalker: social and conversation evidence; buy only where category volume and research question justify it.
- Companies House accounts bulk datasets: free published extracts for official filing evidence, not live turnover. https://www.gov.uk/guidance/companies-house-data-products

## Phase 2: premium evidence as needed
Nielsen/Kantar/Ipsos category research, retailer panel data, econometric partners or bespoke founder/customer interviews when client budget supports. No default expensive annual contracts before 2–3 paid projects establish recurring need.

## Procurement scorecard
Coverage of £0.5m–£50m SMEs; UK availability; API availability; rate limits; rights to reuse charts in client deliverables; history depth; methodology; identity resolution; cost per Blueprint; licence minimum; data retention; client security. Test one real company and one niche category before committing.

## Immediate blocker
We do not currently have verified client analytics, transaction-level sales, media spend or unit economics for the fictional example. Its £690k is a mathematical scenario, not evidence-based uplift. The highest-value next action is a standardised founder data-request pack, not a paid API subscription.

## Security
Use read-only OAuth, scoped per-client credentials, consent, minimal retention, provenance, and workspace isolation. Do not store tokens in GitHub or presentation artefacts.