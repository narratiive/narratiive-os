# LOA advertising activation preflight

Observed: 2026-10-16 16:53:25 UTC  
Decision: **BLOCKED — no campaign may be created, published or funded.**

| Platform | Auth/read evidence | Activation state | Required next action |
|---|---|---|---|
| Google Ads | Authenticated; one account; zero campaigns; read-only probe passed | Account is readable but no LOA campaign, conversion mapping or approved budget exists | Matt identifies the authorised account and approves conversion definitions, naming, budget and a non-publishing build test |
| Meta | Authenticated; ten permissions; zero businesses and ad accounts; campaign read HTTP 400 | Not usable | Connect the intended Business Manager/ad account and diagnose campaign-read 400 before any build |
| TikTok | Not configured | Blocked | Configure advertiser OAuth and confirm read-only account access |
| CTV / The Trade Desk | No adapter or authorised account identified | Untested | Decide whether this channel is in scope, then provide an authorised sandbox/account and measurement requirements |

Creative readiness is also conditional: source provenance, asset rights and product accuracy, claims review, real commercial inputs, a named owner, a capped budget and Matt’s exact approval are all required. This preflight created no campaign, published nothing and spent no money.
